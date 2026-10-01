"""`solstice init` and `solstice hooks install` (KTD3, KTD13).

`init` copies the packaged workspace template to a path the user names. It
refuses a path inside the public plugin repo and a directory that already
holds files. `hooks install` points a plugin checkout's `core.hooksPath` at its
`.githooks/` and can record the workspace the pre-push hook should read.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from importlib import resources
from pathlib import Path

from solstice.state import ENTITIES
from solstice.workspace import ENV_VAR, WorkspaceError, refuse_plugin_checkout, resolve_workspace

# template file -> path inside the new workspace. Stored without leading dots
# so the plugin repo's structural leak check never sees a workspace config.
TEMPLATE_FILES = {
    "config.yaml": ".solstice/config.yaml",
    "gitignore": ".gitignore",
    "rubric.json": "rubric.json",
    "denylist.txt": "denylist.txt",
    "secrets-manifest.yaml": "secrets-manifest.yaml",
}
HOOKS_DIR = ".githooks"
WORKSPACE_GIT_KEY = "solstice.workspace"


def template_dir() -> Path:
    return Path(str(resources.files("solstice") / "templates" / "workspace"))


def init_workspace(path: Path | str) -> tuple[Path, list[str]]:
    target = Path(path).expanduser().absolute()
    if target.exists():
        if not target.is_dir():
            raise WorkspaceError(f"refusing: {target} exists and is not a directory")
        extra = [p.name for p in target.iterdir() if p.name != ".git"]
        if extra:
            raise WorkspaceError(f"refusing: {target} is not empty ({len(extra)} entries); "
                                 f"name a new or empty directory")
    anchor = target
    while not anchor.exists():
        anchor = anchor.parent
    refuse_plugin_checkout(anchor.resolve())

    target.mkdir(parents=True, exist_ok=True)
    src = template_dir()
    created: list[str] = []
    for name, rel in TEMPLATE_FILES.items():
        dest = target / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src / name, dest)
        created.append(rel)
    for plural in ENTITIES.values():
        d = target / "records" / plural
        d.mkdir(parents=True, exist_ok=True)
        (d / ".gitkeep").touch()
        created.append(f"records/{plural}/")
    return target.resolve(), created


def install_hooks(checkout: Path | str, workspace: Path | str | None = None) -> dict:
    """Set `core.hooksPath=.githooks` in a plugin checkout (local git config),
    and optionally record the workspace the hook resolves its denylist from."""
    git = shutil.which("git")
    if git is None:
        raise WorkspaceError("git is not installed")
    checkout = Path(checkout).expanduser().resolve()
    top = _git(git, checkout, "rev-parse", "--show-toplevel")
    if top is None:
        raise WorkspaceError(f"{checkout} is not a git checkout")
    top_path = Path(top).resolve()
    hook = top_path / HOOKS_DIR / "pre-push"
    if not hook.is_file() or not (top_path / ".claude-plugin" / "plugin.json").is_file():
        raise WorkspaceError(f"{top_path} is not a plugin checkout with {HOOKS_DIR}/pre-push")

    result = {"checkout": str(top_path), "core.hooksPath": HOOKS_DIR}
    if workspace is not None:
        ws = resolve_workspace(env={ENV_VAR: str(workspace)})
        if not (ws / "denylist.txt").is_file():
            raise WorkspaceError(f"{ws} has no denylist.txt; the hook would block every push")
        _git(git, top_path, "config", "--local", WORKSPACE_GIT_KEY, str(ws), check=True)
        result[WORKSPACE_GIT_KEY] = str(ws)
    _git(git, top_path, "config", "--local", "core.hooksPath", HOOKS_DIR, check=True)
    return result


def _git(git: str, cwd: Path, *args: str, check: bool = False) -> str | None:
    env = {k: v for k, v in os.environ.items() if k not in ("GIT_DIR", "GIT_WORK_TREE")}
    out = subprocess.run([git, *args], cwd=cwd, env=env, capture_output=True, text=True)
    if out.returncode != 0:
        if check:
            raise WorkspaceError(f"git {' '.join(args)} failed: {out.stderr.strip()}")
        return None
    return out.stdout.strip()
