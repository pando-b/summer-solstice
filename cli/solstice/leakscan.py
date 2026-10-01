"""Leak guard for the public plugin repo (KTD13).

Two entry points:

- ``scan_tree(root)``: the CI structural check. No ``records/`` directory, no
  ``*.events.jsonl``, no ``.solstice/config.yaml``, nothing tracked under
  ``.ce-artifacts/``, every file under ``cli/tests/fixtures/`` carries
  ``FIXTURE_MARKER``, and no file matches a secret pattern.
- ``scan_push(repo, lines, terms)``: the pre-push range scan. For every commit
  being pushed it checks the commit message, added lines, and added paths
  against the private term list and the secret patterns.

The term list comes from the private workspace: ``denylist.txt`` plus the
name, slug, and domain fields of every ``records/products/*.json`` and the
candidate names in every ``products/*/name-candidates.md``. If it cannot be
loaded the push is blocked (fail closed).

Reports name the rule, the commit or file, and the term. Matched secrets are
redacted.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from collections.abc import Iterable
from dataclasses import dataclass
from pathlib import Path

FIXTURE_MARKER = "solstice-fixture: synthetic"
FIXTURE_PREFIX = "cli/tests/fixtures/"
MIN_TERM_LEN = 3
MAX_SCAN_BYTES = 5 * 1024 * 1024
_SKIP_DIRS = {".git", ".venv", "node_modules", "__pycache__", ".pytest_cache", ".ruff_cache"}

_T = r"[A-Za-z0-9!#$%&()*+,.:;<=>?@\[\]^_{|}~-]"  # Freemius secret-key alphabet, minus quotes
SECRET_RULES: list[tuple[str, re.Pattern[str]]] = [
    ("stripe-key", re.compile(r"\b(?:sk|rk)_(?:live|test)_[A-Za-z0-9]{16,}")),
    ("stripe-webhook-secret", re.compile(r"\bwhsec_[A-Za-z0-9+/=]{20,}")),
    # Freemius secret keys: sk_ + a long mixed token. Public keys (pk_) are public by design.
    ("freemius-secret-key", re.compile(
        rf"\bsk_(?!live_|test_)(?={_T}*\d)(?={_T}*[A-Z])(?={_T}*[a-z]){_T}{{24,}}")),
    ("polar-token", re.compile(r"\bpolar_[a-z]{2,4}_[A-Za-z0-9]{20,}")),
    ("private-key", re.compile(r"-----BEGIN [A-Z0-9 ]*PRIVATE KEY-----")),
    ("aws-access-key-id", re.compile(r"\bAKIA[0-9A-Z]{16}\b")),
    ("github-token", re.compile(r"\bgh[pousr]_[A-Za-z0-9]{36,}")),
    ("credential-assignment", re.compile(
        r"(?i)(?:api[_-]?key|secret|token|password)[\"']?\s*[:=]\s*[\"'][A-Za-z0-9_\-]{20,}[\"']")),
]


class LeakscanError(Exception):
    """The scan could not run; callers treat this as a block."""


@dataclass(frozen=True)
class Finding:
    rule: str
    where: str
    detail: str = ""

    def __str__(self) -> str:
        return f"{self.rule}: {self.where}" + (f": {self.detail}" if self.detail else "")


# --- secrets ----------------------------------------------------------------


def _redact(s: str) -> str:
    return f"{s[:4]}... ({len(s)} chars, redacted)"


def scan_secrets(text: str) -> list[tuple[str, str]]:
    hits: list[tuple[str, str]] = []
    taken: list[tuple[int, int]] = []
    for rule, rx in SECRET_RULES:
        for m in rx.finditer(text):
            if any(m.start() < e and s < m.end() for s, e in taken):
                continue
            taken.append(m.span())
            hits.append((rule, _redact(m.group(0))))
    return hits


# --- structural tree check --------------------------------------------------


def path_findings(rel: str) -> list[Finding]:
    parts = rel.split("/")
    out = []
    if "records" in parts[:-1]:
        out.append(Finding("records-dir", rel, "workspace records never enter this repo"))
    if parts[-1].endswith(".events.jsonl"):
        out.append(Finding("event-file", rel, "record event files never enter this repo"))
    if rel == ".solstice/config.yaml" or rel.endswith("/.solstice/config.yaml"):
        out.append(Finding("workspace-config", rel, "workspace config never enters this repo"))
    if ".ce-artifacts" in parts[:-1]:
        out.append(Finding("ce-artifacts", rel, ".ce-artifacts/ is session scratch and must stay untracked"))
    return out


def _list_files(root: Path) -> tuple[list[str], list[str]]:
    """(files, dirs) relative to root. In a git checkout: tracked plus
    untracked-not-ignored files. Elsewhere: a plain walk."""
    git = shutil.which("git")
    if git and (root / ".git").exists():
        out = subprocess.run(
            [git, "ls-files", "-z", "--cached", "--others", "--exclude-standard"],
            cwd=root, capture_output=True, text=True, env=_git_env())
        if out.returncode != 0:
            raise LeakscanError(f"git ls-files failed in {root}: {out.stderr.strip()}")
        return sorted({p for p in out.stdout.split("\0") if p}), []
    files, dirs = [], []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS]
        base = Path(dirpath).relative_to(root)
        dirs += [(base / d).as_posix() for d in dirnames]
        files += [(base / f).as_posix() for f in filenames]
    return sorted(files), sorted(dirs)


def _read_text(path: Path) -> str | None:
    try:
        if path.is_symlink() or not path.is_file() or path.stat().st_size > MAX_SCAN_BYTES:
            return None
        data = path.read_bytes()
    except OSError:
        return None
    return data.decode("utf-8", errors="replace")


def scan_tree(root: Path | str) -> list[Finding]:
    root = Path(root)
    files, dirs = _list_files(root)
    findings: list[Finding] = []
    for d in dirs:
        if d.split("/")[-1] == "records":
            findings.append(Finding("records-dir", d + "/", "workspace records never enter this repo"))
    for rel in files:
        findings += path_findings(rel)
        text = _read_text(root / rel)
        if rel.startswith(FIXTURE_PREFIX) and not rel.endswith(".gitkeep") and (
                text is None or FIXTURE_MARKER not in text):
            findings.append(Finding("fixture-marker", rel, f"fixture lacks {FIXTURE_MARKER!r}"))
        if text:
            findings += [Finding(rule, rel, shown) for rule, shown in scan_secrets(text)]
    return findings


# --- private term list ------------------------------------------------------

_BOLD = re.compile(r"\*\*([^*\n]+?)\*\*")
_TICK = re.compile(r"`([^`\n]+)`")
_SLUG = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)+$")
_DOMAIN = re.compile(r"^[a-z0-9][a-z0-9-]*(?:\.[a-z0-9-]+)*\.([a-z]{2,})$")
_FILE_EXTS = {"md", "json", "jsonl", "yaml", "yml", "txt", "py", "php", "js", "ts", "tsx", "html",
              "css", "csv", "xlsx", "pot", "po", "sh", "toml", "lock", "log"}


def candidate_names(text: str) -> list[str]:
    names = []
    for raw in _BOLD.findall(text):
        s = raw.strip()
        if (len(s) >= MIN_TERM_LEN and re.search(r"[A-Za-z]", s)
                and s[-1] not in ":.!?,;" and len(s.split()) <= 5):
            names.append(s)
    for raw in _TICK.findall(text):
        s = raw.strip().lower()
        m = _DOMAIN.match(s)
        if _SLUG.match(s) or (m and m.group(1) not in _FILE_EXTS):
            names.append(s)
    return names


def load_terms(workspace: Path) -> list[str]:
    workspace = Path(workspace)
    deny = workspace / "denylist.txt"
    if not deny.is_file():
        raise LeakscanError(f"no denylist.txt in workspace {workspace}; failing closed")
    terms = [ln.strip() for ln in deny.read_text().splitlines()
             if ln.strip() and not ln.strip().startswith("#")]

    for rec in sorted((workspace / "records" / "products").glob("*.json")):
        try:
            data = json.loads(rec.read_text())
        except (OSError, ValueError) as exc:
            raise LeakscanError(f"cannot read product record {rec.name}: {exc}") from exc
        for field in ("name", "slug", "domain"):
            if isinstance(data.get(field), str):
                terms.append(data[field])
        if isinstance(data.get("domains"), list):
            terms += [d for d in data["domains"] if isinstance(d, str)]

    for cand in sorted((workspace / "products").glob("*/name-candidates.md")):
        terms += candidate_names(cand.read_text())
        if _SLUG.match(cand.parent.name):
            terms.append(cand.parent.name)

    seen, out = set(), []
    for t in terms:
        key = t.strip().lower()
        if len(key) >= MIN_TERM_LEN and key not in seen:
            seen.add(key)
            out.append(t.strip())
    return out


def _variants(term: str) -> set[str]:
    words = [w for w in re.split(r"[\s_-]+", term.lower()) if w]
    out = {term.lower()}
    if len(words) > 1:
        out |= {" ".join(words), "-".join(words), "_".join(words), "".join(words)}
    return out


def compile_terms(terms: Iterable[str]) -> tuple[re.Pattern[str] | None, dict[str, str]]:
    lookup: dict[str, str] = {}
    for t in terms:
        for v in _variants(t):
            lookup.setdefault(v, t)
    if not lookup:
        return None, lookup
    alts = "|".join(re.escape(v) for v in sorted(lookup, key=len, reverse=True))
    return re.compile(rf"(?<![A-Za-z0-9])(?:{alts})(?![A-Za-z0-9])", re.IGNORECASE), lookup


def match_terms(compiled: tuple[re.Pattern[str] | None, dict[str, str]], text: str) -> list[str]:
    rx, lookup = compiled
    if rx is None:
        return []
    found = []
    for m in rx.finditer(text):
        hit = m.group(0)
        t = lookup[hit.lower()]
        label = t if hit.lower() == t.lower() else f'{t} (as "{hit}")'
        if label not in found:
            found.append(label)
    return found


# --- pre-push range scan ----------------------------------------------------


def _git_env() -> dict[str, str]:
    return {k: v for k, v in os.environ.items()
            if k not in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE")}


def _git(repo: Path, *args: str) -> str:
    git = shutil.which("git")
    if git is None:
        raise LeakscanError("git is not installed")
    out = subprocess.run([git, *args], cwd=repo, capture_output=True, env=_git_env())
    if out.returncode != 0:
        raise LeakscanError(f"git {' '.join(args)} failed: "
                            f"{out.stderr.decode('utf-8', 'replace').strip()}")
    return out.stdout.decode("utf-8", errors="replace")


def _is_zero(sha: str) -> bool:
    return set(sha) == {"0"}


def _has_commit(repo: Path, sha: str) -> bool:
    try:
        _git(repo, "cat-file", "-e", f"{sha}^{{commit}}")
        return True
    except LeakscanError:
        return False


def commits_in_push(repo: Path, lines: Iterable[str]) -> list[str]:
    commits: list[str] = []
    for line in lines:
        if not line.strip():
            continue
        parts = line.split()
        if len(parts) != 4 or not all(re.fullmatch(r"[0-9a-f]{40}|[0-9a-f]{64}", p) for p in parts[1::2]):
            raise LeakscanError(f"unexpected pre-push input line: {line.strip()!r}")
        _, local_sha, _, remote_sha = parts
        if _is_zero(local_sha):
            continue  # branch deletion: nothing new leaves this machine
        if _is_zero(remote_sha) or not _has_commit(repo, remote_sha):
            spec = [local_sha, "--not", "--remotes"]
        else:
            spec = [f"{remote_sha}..{local_sha}"]
        for sha in _git(repo, "rev-list", *spec).split():
            if sha not in commits:
                commits.append(sha)
    return commits


def _added(repo: Path, sha: str) -> tuple[list[str], list[tuple[str, str]]]:
    """(added paths, [(path, added line)]) for a commit against its first parent."""
    diff = _git(repo, "show", "--format=", "-p", "-U0", "--no-color", "--no-ext-diff",
                "--no-renames", "--text", "--diff-merges=first-parent", sha)
    paths: list[str] = []
    lines: list[tuple[str, str]] = []
    current = ""
    for ln in diff.splitlines():
        if ln.startswith("+++ "):
            current = ln[4:]
            current = current[2:] if current.startswith("b/") else current
            if current != "/dev/null":
                paths.append(current)
        elif ln.startswith("+") and current:
            lines.append((current, ln[1:]))
    return paths, lines


def scan_push(repo: Path, lines: Iterable[str], terms: list[str]) -> list[Finding]:
    compiled = compile_terms(terms)
    findings: list[Finding] = []
    for sha in commits_in_push(repo, lines):
        short = sha[:12]
        message = _git(repo, "log", "-1", "--format=%B", sha)
        for t in match_terms(compiled, message):
            findings.append(Finding("denylist-term", f"commit {short} message", t))
        for rule, shown in scan_secrets(message):
            findings.append(Finding(rule, f"commit {short} message", shown))

        paths, added = _added(repo, sha)
        for p in paths:
            findings += [Finding(f.rule, f"commit {short} {p}", f.detail) for f in path_findings(p)]
            for t in match_terms(compiled, p):
                findings.append(Finding("denylist-term", f"commit {short} path {p}", t))
        by_path: dict[str, list[str]] = {}
        for p, text in added:
            by_path.setdefault(p, []).append(text)
        for p, chunk in by_path.items():
            text = "\n".join(chunk)
            for t in match_terms(compiled, text):
                findings.append(Finding("denylist-term", f"commit {short} {p}", t))
            for rule, shown in scan_secrets(text):
                findings.append(Finding(rule, f"commit {short} {p}", shown))
    return findings
