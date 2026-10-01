"""Shared fixtures. All paths and names here are synthetic."""

import shutil
import subprocess
from pathlib import Path

import pytest

PLUGIN_REMOTE_HTTPS = "https://github.com/pando-b/summer-solstice.git"
PLUGIN_REMOTE_SSH = "git@github.com:pando-b/summer-solstice.git"
OTHER_REMOTE = "https://github.com/example-owner/example-workspace.git"


def _git(*args: str, cwd: Path) -> None:
    subprocess.run(["git", *args], cwd=cwd, check=True, capture_output=True)


@pytest.fixture
def make_checkout():
    """Create a git repo at `path` with `origin` set to `remote`."""
    if shutil.which("git") is None:
        pytest.skip("git not installed")

    def _make(path: Path, remote: str) -> Path:
        path.mkdir(parents=True, exist_ok=True)
        _git("init", "-q", cwd=path)
        _git("remote", "add", "origin", remote, cwd=path)
        return path

    return _make


@pytest.fixture
def write_config():
    """Write `.solstice/config.yaml` under `root` with the given body."""

    def _write(root: Path, body: str) -> Path:
        cfg_dir = root / ".solstice"
        cfg_dir.mkdir(parents=True, exist_ok=True)
        cfg = cfg_dir / "config.yaml"
        cfg.write_text(body)
        return cfg

    return _write


@pytest.fixture
def clock():
    from factories import Clock

    return Clock()


@pytest.fixture
def ws(tmp_path):
    path = tmp_path / "ws"
    path.mkdir()
    return path


@pytest.fixture
def store(ws, clock):
    from solstice.state import Store

    return Store(ws, now=clock, lock_wait=0)
