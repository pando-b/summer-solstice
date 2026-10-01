"""Leak guard (KTD13): CI structural check, secret patterns, and the
fail-closed pre-push range scan.

Every term here is invented. Secret-shaped strings are assembled at runtime so
this file never contains anything a scanner would flag.
"""

import io
import json
import os
import shutil
import subprocess
from pathlib import Path

import pytest

from solstice import leakscan
from solstice.__main__ import main

REPO_ROOT = Path(__file__).resolve().parents[2]
ZERO = "0" * 40
TERM = "Zephyrquill"  # synthetic denylisted term
MARKER = leakscan.FIXTURE_MARKER


def _tok(n: int, alphabet: str = "Ab3Xy9Qz") -> str:
    return (alphabet * (n // len(alphabet) + 1))[:n]


FAKE = {
    "stripe-key": "sk" + "_live_" + _tok(24),
    "stripe-key-test": "rk" + "_test_" + _tok(24),
    "stripe-webhook-secret": "wh" + "sec_" + _tok(32),
    "freemius-secret-key": "sk" + "_" + _tok(29),
    "polar-token": "po" + "lar_oat_" + _tok(40),
    "private-key": "-----BEGIN RSA " + "PRIVATE KEY-----",
    "aws-access-key-id": "AK" + "IA" + "ABCDEFGHIJ234567",
    "github-token": "gh" + "p_" + _tok(36),
    "credential-assignment": "api_key = '" + _tok(24) + "'",
}
RULE_OF = {k: k.removesuffix("-test") for k in FAKE}


# --- secret patterns --------------------------------------------------------


@pytest.mark.parametrize("name", sorted(FAKE))
def test_each_secret_pattern_fires(name):
    hits = leakscan.scan_secrets(f"prefix {FAKE[name]} suffix")
    assert RULE_OF[name] in {rule for rule, _ in hits}


@pytest.mark.parametrize("text", [
    "pk" + "_" + _tok(29),                     # Freemius public keys are public by design
    "task_runner_for_the_widget_pipeline",     # sk_ inside an identifier
    "sk_and_rk_prefixes_are_documented_here",  # no digits/mixed case token
    "token = os.environ['EXAMPLE_TOKEN']",
    "polar_api",
])
def test_benign_strings_do_not_fire(text):
    assert leakscan.scan_secrets(text) == []


def test_secret_is_redacted_in_report():
    hits = leakscan.scan_secrets(FAKE["stripe-key"])
    shown = hits[0][1]
    assert FAKE["stripe-key"] not in shown
    assert len(shown) < len(FAKE["stripe-key"])


# --- structural tree check --------------------------------------------------


def _rules(findings):
    return {f.rule for f in findings}


def test_clean_tree_passes(tmp_path):
    (tmp_path / "src").mkdir()
    (tmp_path / "src" / "a.py").write_text("print('synthetic')\n")
    assert leakscan.scan_tree(tmp_path) == []


@pytest.mark.parametrize("rel,rule", [
    ("records/products/01HX.json", "records-dir"),
    ("deep/records/x.txt", "records-dir"),
    ("data/01HX.events.jsonl", "event-file"),
    (".solstice/config.yaml", "workspace-config"),
])
def test_forbidden_paths_fail(tmp_path, rel, rule):
    p = tmp_path / rel
    p.parent.mkdir(parents=True)
    p.write_text("{}")
    assert rule in _rules(leakscan.scan_tree(tmp_path))


def test_empty_records_dir_fails(tmp_path):
    (tmp_path / "records").mkdir()
    assert "records-dir" in _rules(leakscan.scan_tree(tmp_path))


def test_fixture_without_marker_fails_and_with_marker_passes(tmp_path):
    fx = tmp_path / "cli" / "tests" / "fixtures"
    fx.mkdir(parents=True)
    (fx / "bad.json").write_text('{"name": "example"}')
    (fx / "good.json").write_text(json.dumps({"_fixture": MARKER, "name": "example"}))
    findings = leakscan.scan_tree(tmp_path)
    assert [(f.rule, f.where) for f in findings] == [("fixture-marker", "cli/tests/fixtures/bad.json")]


def test_fake_stripe_key_in_fixture_fails_ci(tmp_path):
    fx = tmp_path / "cli" / "tests" / "fixtures"
    fx.mkdir(parents=True)
    (fx / "resp.json").write_text(json.dumps({"_fixture": MARKER, "key": FAKE["stripe-key"]}))
    findings = leakscan.scan_tree(tmp_path)
    assert "stripe-key" in _rules(findings)
    assert FAKE["stripe-key"] not in "\n".join(map(str, findings))


def _git(*args, cwd):
    env = {**os.environ, "GIT_AUTHOR_NAME": "Example", "GIT_AUTHOR_EMAIL": "dev@example.com",
           "GIT_COMMITTER_NAME": "Example", "GIT_COMMITTER_EMAIL": "dev@example.com"}
    for k in ("GIT_DIR", "GIT_WORK_TREE", "GIT_INDEX_FILE"):
        env.pop(k, None)
    return subprocess.run(["git", "-c", "core.hooksPath=/dev/null", "-c", "commit.gpgsign=false",
                           *args], cwd=cwd, env=env, check=True, capture_output=True,
                          text=True).stdout.strip()


@pytest.fixture
def repo(tmp_path):
    if shutil.which("git") is None:
        pytest.skip("git not installed")
    r = tmp_path / "repo"
    r.mkdir()
    _git("init", "-q", "-b", "main", cwd=r)
    (r / "README.md").write_text("synthetic\n")
    _git("add", ".", cwd=r)
    _git("commit", "-q", "-m", "init", cwd=r)
    return r


def test_tracked_ce_artifact_fails_but_ignored_one_passes(repo):
    (repo / ".gitignore").write_text(".ce-artifacts/\n")
    art = repo / ".ce-artifacts"
    art.mkdir()
    (art / "plan.md").write_text("synthetic")
    assert leakscan.scan_tree(repo) == []
    _git("add", "-f", ".ce-artifacts/plan.md", cwd=repo)
    assert "ce-artifacts" in _rules(leakscan.scan_tree(repo))


def test_real_repo_tree_passes():
    findings = leakscan.scan_tree(REPO_ROOT)
    assert findings == [], "\n".join(map(str, findings))


def test_cli_tree_exit_codes(tmp_path, capsys):
    assert main(["leakscan", "tree", str(tmp_path)]) == 0
    (tmp_path / "x.events.jsonl").write_text("")
    assert main(["leakscan", "tree", str(tmp_path)]) == 1
    assert "event-file" in capsys.readouterr().err


# --- term list --------------------------------------------------------------


def _ws(tmp_path, deny=f"# synthetic\n{TERM}\n") -> Path:
    ws = tmp_path / "ws"
    ws.mkdir()
    if deny is not None:
        (ws / "denylist.txt").write_text(deny)
    return ws


def test_terms_come_from_denylist_records_and_name_candidates(tmp_path):
    ws = _ws(tmp_path)
    prod = ws / "records" / "products"
    prod.mkdir(parents=True)
    (prod / "01HXEXAMPLE.json").write_text(json.dumps(
        {"name": "Quillmarrow Ledger", "slug": "quillmarrow-ledger", "domain": "quillmarrow.example"}))
    (prod / "01HXEXAMPLE.events.jsonl").write_text('{"type": "created"}\n')
    cand = ws / "products" / "brindlewick-app"
    cand.mkdir(parents=True)
    (cand / "name-candidates.md").write_text(
        "**Rules:** keep it short.\n\n**Pick one.** Then check.\n\n"
        "| 1 | **Fennow for Teams** | `fennow` | `fennow-for-teams` 404 | `fennow.com` |\n"
        "- **Tallowmere Desk** (`tallowmere-desk` 404). See `notes_file.json_path`.\n"
        "**404**\n")
    terms = {t.lower() for t in leakscan.load_terms(ws)}
    assert {TERM.lower(), "quillmarrow ledger", "quillmarrow-ledger", "quillmarrow.example",
            "fennow for teams", "fennow-for-teams", "fennow.com", "tallowmere desk",
            "tallowmere-desk", "brindlewick-app"} <= terms
    assert "rules:" not in terms and "rules" not in terms and "pick one." not in terms
    assert "404" not in terms and "fennow" not in terms


def test_missing_denylist_fails_closed(tmp_path):
    ws = _ws(tmp_path, deny=None)
    with pytest.raises(leakscan.LeakscanError, match="denylist"):
        leakscan.load_terms(ws)


def test_term_variants_match_separators_and_case():
    rx = leakscan.compile_terms(["Fennow for Teams"])
    for text in ("fennow-for-teams", "FENNOW_FOR_TEAMS", "Fennow for teams", "fennowforteams"):
        assert leakscan.match_terms(rx, f"see {text}."), text
    assert not leakscan.match_terms(rx, "fennow for teamster")


# --- pre-push range scan ----------------------------------------------------


def _commit(repo, msg, files=None):
    for rel, body in (files or {}).items():
        p = repo / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(body)
    _git("add", "-A", cwd=repo)
    _git("commit", "-q", "--allow-empty", "-m", msg, cwd=repo)
    return _git("rev-parse", "HEAD", cwd=repo)


def _push_line(repo, local_sha, remote_sha, ref="refs/heads/main"):
    return f"{ref} {local_sha} {ref} {remote_sha}\n"


def _run_hook(monkeypatch, repo, stdin, env_ws):
    monkeypatch.chdir(repo)
    if env_ws is None:
        monkeypatch.delenv("SOLSTICE_WORKSPACE", raising=False)
    else:
        monkeypatch.setenv("SOLSTICE_WORKSPACE", str(env_ws))
    monkeypatch.setattr("sys.stdin", io.StringIO(stdin))
    return main(["leakscan", "pre-push", "origin", "https://example.com/example.git"])


def test_term_in_commit_message_only_is_blocked(repo, tmp_path, monkeypatch, capsys):
    base = _git("rev-parse", "HEAD", cwd=repo)
    sha = _commit(repo, f"tweak copy for {TERM.lower()} launch", {"a.txt": "clean\n"})
    code = _run_hook(monkeypatch, repo, _push_line(repo, sha, base), _ws(tmp_path))
    err = capsys.readouterr().err
    assert code == 1
    assert sha[:12] in err and "message" in err and TERM in err


def test_no_resolvable_workspace_blocks(repo, monkeypatch, capsys):
    base = _git("rev-parse", "HEAD", cwd=repo)
    sha = _commit(repo, "clean change", {"a.txt": "clean\n"})
    assert _run_hook(monkeypatch, repo, _push_line(repo, sha, base), None) != 0
    assert "blocked" in capsys.readouterr().err.lower()


def test_missing_denylist_blocks(repo, tmp_path, monkeypatch):
    base = _git("rev-parse", "HEAD", cwd=repo)
    sha = _commit(repo, "clean change", {"a.txt": "clean\n"})
    assert _run_hook(monkeypatch, repo, _push_line(repo, sha, base), _ws(tmp_path, deny=None)) != 0


def test_name_only_in_product_record_is_blocked(repo, tmp_path, monkeypatch, capsys):
    ws = _ws(tmp_path, deny="# nothing listed by hand\n")
    prod = ws / "records" / "products"
    prod.mkdir(parents=True)
    (prod / "01HXEXAMPLE.json").write_text(json.dumps({"name": "Quillmarrow Ledger",
                                                       "slug": "quillmarrow-ledger"}))
    base = _git("rev-parse", "HEAD", cwd=repo)
    sha = _commit(repo, "add example", {"docs/x.md": "Works with quillmarrow-ledger out of the box.\n"})
    assert _run_hook(monkeypatch, repo, _push_line(repo, sha, base), ws) == 1
    err = capsys.readouterr().err
    assert "docs/x.md" in err and "quillmarrow-ledger" in err.lower()


def test_term_in_file_path_is_blocked(repo, tmp_path, monkeypatch):
    base = _git("rev-parse", "HEAD", cwd=repo)
    sha = _commit(repo, "add page", {f"pages/{TERM.lower()}.md": "clean\n"})
    assert _run_hook(monkeypatch, repo, _push_line(repo, sha, base), _ws(tmp_path)) == 1


def test_fake_stripe_key_in_fixture_is_blocked(repo, tmp_path, monkeypatch, capsys):
    base = _git("rev-parse", "HEAD", cwd=repo)
    body = json.dumps({"_fixture": MARKER, "key": FAKE["stripe-key"]})
    sha = _commit(repo, "add fixture", {"cli/tests/fixtures/resp.json": body})
    assert _run_hook(monkeypatch, repo, _push_line(repo, sha, base), _ws(tmp_path)) == 1
    err = capsys.readouterr().err
    assert "stripe-key" in err and FAKE["stripe-key"] not in err


def test_records_path_in_push_is_blocked(repo, tmp_path, monkeypatch):
    base = _git("rev-parse", "HEAD", cwd=repo)
    sha = _commit(repo, "oops", {"records/problems/01HX.json": "{}"})
    assert _run_hook(monkeypatch, repo, _push_line(repo, sha, base), _ws(tmp_path)) == 1


def test_clean_commit_is_allowed(repo, tmp_path, monkeypatch):
    base = _git("rev-parse", "HEAD", cwd=repo)
    sha = _commit(repo, "clean change", {"a.txt": "nothing to see\n"})
    assert _run_hook(monkeypatch, repo, _push_line(repo, sha, base), _ws(tmp_path)) == 0


def test_every_commit_in_range_is_scanned(repo, tmp_path, monkeypatch):
    base = _git("rev-parse", "HEAD", cwd=repo)
    _commit(repo, "bad middle", {"a.txt": f"{TERM}\n"})
    sha = _commit(repo, "remove it", {"a.txt": "clean\n"})
    assert _run_hook(monkeypatch, repo, _push_line(repo, sha, base), _ws(tmp_path)) == 1


def test_new_branch_scans_only_commits_not_on_a_remote(repo, tmp_path, monkeypatch):
    remote = tmp_path / "remote.git"
    _git("init", "-q", "--bare", str(remote), cwd=tmp_path)
    _git("remote", "add", "origin", str(remote), cwd=repo)
    _commit(repo, f"old history mentions {TERM}")  # already public before the guard
    _git("push", "-q", "origin", "main", cwd=repo)
    _git("checkout", "-q", "-b", "feature", cwd=repo)
    sha = _commit(repo, "clean feature", {"b.txt": "clean\n"})
    ws = _ws(tmp_path)
    line = _push_line(repo, sha, ZERO, ref="refs/heads/feature")
    assert _run_hook(monkeypatch, repo, line, ws) == 0

    bad = _commit(repo, f"feature for {TERM}")
    line = _push_line(repo, bad, ZERO, ref="refs/heads/feature")
    assert _run_hook(monkeypatch, repo, line, ws) == 1


def test_new_branch_with_no_remotes_scans_all_history(repo, tmp_path, monkeypatch):
    _commit(repo, f"mentions {TERM}")
    sha = _commit(repo, "clean tip")
    assert _run_hook(monkeypatch, repo, _push_line(repo, sha, ZERO), _ws(tmp_path)) == 1


def test_deletion_is_allowed(repo, tmp_path, monkeypatch):
    base = _git("rev-parse", "HEAD", cwd=repo)
    line = f"(delete) {ZERO} refs/heads/old {base}\n"
    assert _run_hook(monkeypatch, repo, line, _ws(tmp_path)) == 0


def test_unknown_remote_sha_falls_back_to_remote_exclusion(repo, tmp_path, monkeypatch):
    sha = _commit(repo, f"about {TERM}")
    unknown = "1" * 40
    assert _run_hook(monkeypatch, repo, _push_line(repo, sha, unknown), _ws(tmp_path)) == 1


def test_malformed_stdin_blocks(repo, tmp_path, monkeypatch):
    assert _run_hook(monkeypatch, repo, "garbage\n", _ws(tmp_path)) != 0


# --- the shell hook ---------------------------------------------------------


def test_hook_blocks_when_uv_is_unavailable(tmp_path):
    hook = REPO_ROOT / ".githooks" / "pre-push"
    path = "/usr/bin:/bin"
    if shutil.which("uv", path=path):
        pytest.skip("uv is on the minimal PATH")
    out = subprocess.run(["/bin/sh", str(hook), "origin", "x"], cwd=REPO_ROOT, input="",
                         env={"PATH": path, "HOME": str(tmp_path)}, capture_output=True, text=True)
    assert out.returncode != 0
    assert "blocked" in out.stderr.lower()
