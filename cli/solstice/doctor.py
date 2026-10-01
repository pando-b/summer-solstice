"""`solstice doctor`: report each dependency as ok, missing-optional, or
missing-required (U3, R16).

Every outside probe (PATH lookups, environment, home directory, plugin root)
comes through `Probes`, so tests can inject them. Key values are never read
beyond a presence check and never printed.
"""

from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path

import yaml

from solstice import __version__
from solstice.init import HOOKS_DIR, WORKSPACE_GIT_KEY, template_dir
from solstice.workspace import ENV_VAR, WorkspaceError, resolve_workspace

OK, OPTIONAL, REQUIRED = "ok", "missing-optional", "missing-required"
INSTALL_HINT = ("uv tool install 'git+https://github.com/pando-b/summer-solstice@v<plugin version>"
                "#subdirectory=cli'")

_PRE = {"a": "a", "alpha": "a", "b": "b", "beta": "b", "c": "rc", "rc": "rc", "pre": "rc",
        "preview": "rc"}
_VERSION = re.compile(
    r"^v?(?P<release>\d+(?:\.\d+)*)"
    r"(?:[-_.]?(?P<pre>alpha|beta|preview|pre|rc|a|b|c)[-_.]?(?P<pren>\d+)?)?"
    r"(?P<postsep>[-_.]?(?:post|rev|r)[-_.]?(?P<post>\d+)?)?"
    r"(?P<devsep>[-_.]?dev[-_.]?(?P<dev>\d+)?)?$",
    re.IGNORECASE,
)


def normalize_version(v: str) -> str:
    """PEP 440 normal form for the spellings plugin manifests use
    (`2.0.0-dev` -> `2.0.0.dev0`). Unparseable input is returned stripped."""
    s = v.strip()
    m = _VERSION.match(s)
    if not m:
        return s
    out = m.group("release")
    if m.group("pre"):
        out += _PRE[m.group("pre").lower()] + str(int(m.group("pren") or 0))
    if m.group("postsep"):
        out += f".post{int(m.group('post') or 0)}"
    if m.group("devsep"):
        out += f".dev{int(m.group('dev') or 0)}"
    return out


@dataclass
class Probes:
    cli_version: str = __version__
    plugin_root: Path | None = None
    env: Mapping[str, str] = field(default_factory=lambda: dict(os.environ))
    cwd: Path = field(default_factory=Path.cwd)
    home: Path = field(default_factory=Path.home)
    which: Callable[[str], str | None] = shutil.which


def find_plugin_root(explicit: Path | str | None, env: Mapping[str, str], cwd: Path) -> Path | None:
    candidates: list[Path] = []
    if explicit:
        return Path(explicit).expanduser().resolve()
    if env.get("CLAUDE_PLUGIN_ROOT"):
        candidates.append(Path(env["CLAUDE_PLUGIN_ROOT"]))
    top = _git(cwd, "rev-parse", "--show-toplevel")
    if top:
        candidates.append(Path(top))
    candidates.append(Path(__file__).resolve().parents[2])  # source checkout / editable install
    for c in candidates:
        if (c / ".claude-plugin" / "plugin.json").is_file():
            return c.resolve()
    return None


def _git(cwd: Path, *args: str) -> str | None:
    git = shutil.which("git")
    if git is None or not cwd.is_dir():
        return None
    env = {k: v for k, v in os.environ.items() if k not in ("GIT_DIR", "GIT_WORK_TREE")}
    out = subprocess.run([git, *args], cwd=cwd, env=env, capture_output=True, text=True)
    return out.stdout.strip() if out.returncode == 0 else None


def _check(name: str, status: str, detail: str) -> dict:
    return {"name": name, "status": status, "detail": detail}


def _installed_plugins(home: Path) -> set[str]:
    f = home / ".claude" / "plugins" / "installed_plugins.json"
    try:
        data = json.loads(f.read_text())
    except (OSError, ValueError):
        return set()
    plugins = data.get("plugins", data) if isinstance(data, dict) else {}
    return {str(k).split("@")[0] for k in plugins}


def _secrets_manifest() -> dict:
    return yaml.safe_load((template_dir() / "secrets-manifest.yaml").read_text())


def _version_check(p: Probes) -> dict:
    name = "solstice version"
    if p.plugin_root is None:
        return _check(name, REQUIRED, "plugin root not found (pass --plugin-root or set "
                                      "CLAUDE_PLUGIN_ROOT); cannot compare versions")
    try:
        plugin_v = json.loads((p.plugin_root / ".claude-plugin" / "plugin.json").read_text())["version"]
    except (OSError, ValueError, KeyError) as exc:
        return _check(name, REQUIRED, f"cannot read plugin.json version: {exc}")
    if normalize_version(plugin_v) == normalize_version(p.cli_version):
        return _check(name, OK, f"CLI {p.cli_version} matches plugin {plugin_v}")
    return _check(name, REQUIRED, f"CLI {p.cli_version} != plugin {plugin_v}; reinstall: {INSTALL_HINT}")


def _hook_check(p: Probes) -> dict:
    name = "pre-push hook"
    root = p.plugin_root
    if root is None or _git(root, "rev-parse", "--show-toplevel") is None:
        return _check(name, OPTIONAL, "no plugin git checkout here; the hook is only needed "
                                      "where you push to the plugin repo")
    hook = root / HOOKS_DIR / "pre-push"
    if not hook.is_file() or not os.access(hook, os.X_OK):
        return _check(name, REQUIRED, f"{HOOKS_DIR}/pre-push missing or not executable")
    configured = _git(root, "config", "--get", "core.hooksPath")
    if not configured:
        return _check(name, REQUIRED, "core.hooksPath is unset; run `solstice hooks install "
                                      f"{root} --workspace <workspace>`")
    effective = Path(configured).expanduser()
    if not effective.is_absolute():
        effective = root / effective
    if effective.resolve() != (root / HOOKS_DIR).resolve():
        return _check(name, REQUIRED, f"core.hooksPath is {configured!r}, not {HOOKS_DIR}")
    hook_ws = p.env.get(ENV_VAR) or _git(root, "config", "--get", WORKSPACE_GIT_KEY)
    if not hook_ws:
        return _check(name, REQUIRED, "hook is armed but no workspace resolves for it, so every "
                                      "push will block; run `solstice hooks install --workspace`")
    try:
        ws = resolve_workspace(env={ENV_VAR: hook_ws})
    except WorkspaceError as exc:
        return _check(name, REQUIRED, f"hook workspace invalid, pushes will block: {exc}")
    if not (ws / "denylist.txt").is_file():
        return _check(name, REQUIRED, f"{ws} has no denylist.txt, so every push will block")
    return _check(name, OK, f"core.hooksPath={HOOKS_DIR}; denylist from {ws}")


def run_checks(p: Probes) -> dict:
    checks = []
    uv = p.which("uv")
    checks.append(_check("uv", OK if uv else REQUIRED,
                         uv or "install uv: https://docs.astral.sh/uv/"))
    checks.append(_version_check(p))
    try:
        ws = resolve_workspace(cwd=p.cwd, env=p.env)
        checks.append(_check("workspace", OK, str(ws)))
    except WorkspaceError as exc:
        checks.append(_check("workspace", REQUIRED, f"{exc}; create one with `solstice init <path>`"))
    checks.append(_hook_check(p))

    inf = p.which("infisical")
    checks.append(_check("infisical", OK if inf else OPTIONAL,
                         inf or "not installed; keys can still come from the environment"))
    plugins = _installed_plugins(p.home)
    checks.append(_check("compound-engineering plugin",
                         OK if "compound-engineering" in plugins else REQUIRED,
                         "installed" if "compound-engineering" in plugins else
                         "not installed; build delegates to it (find and qualify run without it)"))
    if p.which("impeccable"):
        checks.append(_check("impeccable", OK, "installed"))
    elif p.which("npx"):
        checks.append(_check("impeccable", OK, "runs through `npx impeccable`"))
    else:
        checks.append(_check("impeccable", OPTIONAL, "needs npx (Node) for the build design gate"))
    l30 = "last30days" in plugins or (p.home / ".claude" / "skills" / "last30days").is_dir()
    checks.append(_check("last30days", OK if l30 else OPTIONAL,
                         "installed" if l30 else "not installed; Find skips that source"))

    manifest = _secrets_manifest()
    adapters: dict[str, list[str]] = {}
    for s in manifest["secrets"]:
        adapters.setdefault(s["name"], []).append(s["key"])
    ready = []
    for adapter, keys in adapters.items():
        missing = [k for k in keys if not p.env.get(k)]
        if missing:
            checks.append(_check(f"{adapter} keys", OPTIONAL, "unset: " + ", ".join(missing)))
        else:
            ready.append(adapter)
            checks.append(_check(f"{adapter} keys", OK, "set: " + ", ".join(keys)))
    demand = {s["name"] for s in manifest["secrets"] if s["used_for"].startswith("demand")}
    return {
        "ok": all(c["status"] != REQUIRED for c in checks),
        "checks": checks,
        "keyless_sources": list(manifest["keyless_sources"]),
        "paid_sources_ready": [a for a in ready if a in demand],
        "mode": "keyed" if demand & set(ready) else "keyless",
    }


def print_report(report: dict, as_json: bool = False) -> None:
    if as_json:
        print(json.dumps(report, indent=2))
        return
    for c in report["checks"]:
        print(f"{c['status']:<17} {c['name']:<28} {c['detail']}")
    print()
    print(f"Find mode: {report['mode']}. Keyless sources always available: "
          + ", ".join(report["keyless_sources"]) + ".")
    if report["paid_sources_ready"]:
        print("Paid sources ready: " + ", ".join(report["paid_sources_ready"]) + ".")
    print("Healthy." if report["ok"] else "Fix every missing-required item above.")
