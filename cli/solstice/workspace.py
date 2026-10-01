"""Resolve the private workspace, failing closed (KTD3).

Resolution order:
1. ``SOLSTICE_WORKSPACE`` (must be an existing directory).
2. The nearest ``.solstice/config.yaml`` walking up from the cwd; its
   ``workspace_root`` (default ``.``) resolves against the directory that
   contains ``.solstice/``.

There is no fallback to the cwd. Whatever path resolves is refused if it sits
inside any git checkout whose remote is the public plugin repo.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from collections.abc import Mapping
from pathlib import Path

import yaml

from solstice.errors import SolsticeError

ENV_VAR = "SOLSTICE_WORKSPACE"
CONFIG_DIR = ".solstice"
CONFIG_FILE = "config.yaml"

PLUGIN_REPO = "pando-b/summer-solstice"
_PLUGIN_REMOTE_RE = re.compile(
    r"^(?:https?://(?:[^@/]+@)?github\.com/"
    r"|ssh://git@github\.com/"
    r"|git@github\.com:)"
    r"pando-b/summer-solstice(?:\.git)?/?$",
    re.IGNORECASE,
)

# Git variables that would redirect `git` away from the path we ask about.
_GIT_ENV_OVERRIDES = ("GIT_DIR", "GIT_WORK_TREE", "GIT_CEILING_DIRECTORIES")


class WorkspaceError(SolsticeError):
    """The workspace could not be resolved, or resolved somewhere forbidden."""

    kind = "workspace"
    exit_code = 2


def is_plugin_remote(url: str) -> bool:
    return bool(_PLUGIN_REMOTE_RE.match(url.strip()))


def resolve_workspace(
    cwd: Path | str | None = None, env: Mapping[str, str] | None = None
) -> Path:
    env = os.environ if env is None else env
    cwd = Path.cwd() if cwd is None else Path(cwd)

    raw = env.get(ENV_VAR)
    if raw:
        path = _require_dir(Path(raw).expanduser(), f"{ENV_VAR}={raw}")
    else:
        path = _from_config(cwd.resolve())

    refuse_plugin_checkout(path)
    return path


def _require_dir(path: Path, source: str) -> Path:
    if not path.exists():
        raise WorkspaceError(f"workspace path does not exist: {path} (from {source})")
    if not path.is_dir():
        raise WorkspaceError(f"workspace path is not a directory: {path} (from {source})")
    return path.resolve()


def _from_config(cwd: Path) -> Path:
    for base in (cwd, *cwd.parents):
        cfg = base / CONFIG_DIR / CONFIG_FILE
        if cfg.is_file():
            return _read_config(cfg, base)
    raise WorkspaceError(
        f"no workspace found: set {ENV_VAR} or add {CONFIG_DIR}/{CONFIG_FILE} "
        f"with workspace_root in this directory or a parent (searched from {cwd})"
    )


def _read_config(cfg: Path, base: Path) -> Path:
    try:
        data = yaml.safe_load(cfg.read_text()) or {}
    except (OSError, yaml.YAMLError) as exc:
        raise WorkspaceError(f"cannot read workspace config {cfg}: {exc}") from exc
    if not isinstance(data, dict):
        raise WorkspaceError(f"workspace config {cfg} must be a YAML mapping")
    root = data.get("workspace_root", ".")
    if not isinstance(root, str) or not root.strip():
        raise WorkspaceError(f"workspace_root in {cfg} must be a non-empty string")
    path = Path(root).expanduser()
    if not path.is_absolute():
        path = base / path
    return _require_dir(path, str(cfg))


def load_config(workspace: Path) -> dict:
    """The workspace's `.solstice/config.yaml` as a mapping ({} when absent)."""
    from solstice.state import RecordError  # state imports this module

    path = Path(workspace) / CONFIG_DIR / CONFIG_FILE
    if not path.is_file():
        return {}
    try:
        data = yaml.safe_load(path.read_text()) or {}
    except yaml.YAMLError as exc:
        raise RecordError(f"cannot read {path}: {exc}") from exc
    return data if isinstance(data, dict) else {}


def adapter_cfg(cfg: dict, name: str) -> dict:
    section = (cfg.get("adapters") or {}).get(name)
    return section if isinstance(section, dict) else {}


def budget(cfg: dict, key: str, default: float) -> float:
    """`budgets.<key>` as a float, or `default` when unset."""
    value = (cfg.get("budgets") or {}).get(key)
    return default if value is None else float(value)


def refuse_plugin_checkout(path: Path) -> None:
    """Raise if `path` is inside any checkout (including outer, enclosing
    checkouts of a nested repo) whose remote is the plugin repo.

    Fails closed: if git is missing or errors for any reason other than
    "not a git repository", the path is refused."""
    git = shutil.which("git")
    if git is None:
        raise WorkspaceError(
            f"refusing: git is not installed or not on PATH, so workspace path {path} "
            f"cannot be checked against the public plugin repo ({PLUGIN_REPO})"
        )
    git_env = {k: v for k, v in os.environ.items() if k not in _GIT_ENV_OVERRIDES}
    git_env["LC_ALL"] = "C"  # stable error text for the "not a git repository" check

    probe: Path | None = path
    while probe is not None:
        top = _git(git, probe, path, git_env, "rev-parse", "--show-toplevel")
        if top is None:
            return
        toplevel = Path(top).resolve()
        remotes = _git(git, toplevel, path, git_env, "remote", "-v") or ""
        for line in remotes.splitlines():
            parts = line.split()
            if len(parts) >= 2 and is_plugin_remote(parts[1]):
                raise WorkspaceError(
                    f"refusing: workspace resolves inside the public plugin repo "
                    f"({PLUGIN_REPO}) checkout at {toplevel}; workspace path {path}. "
                    f"Point {ENV_VAR} or workspace_root at the private workspace."
                )
        parent = toplevel.parent
        probe = parent if parent != toplevel else None


def _git(git: str, cwd: Path, path: Path, env: dict[str, str], *args: str) -> str | None:
    """stdout of a git command; None only when `cwd` is not in a git repository.
    Any other failure raises, so the boundary check fails closed."""
    try:
        out = subprocess.run(
            [git, *args], cwd=cwd, env=env, capture_output=True, text=True, check=False
        )
    except OSError as exc:
        raise WorkspaceError(
            f"refusing: could not run git to check workspace path {path} "
            f"against the public plugin repo: {exc}"
        ) from exc
    if out.returncode != 0:
        if "not a git repository" in out.stderr.lower():
            return None
        raise WorkspaceError(
            f"refusing: `git {' '.join(args)}` failed in {cwd} while checking workspace path "
            f"{path} against the public plugin repo: {out.stderr.strip() or f'exit {out.returncode}'}"
        )
    return out.stdout.strip()
