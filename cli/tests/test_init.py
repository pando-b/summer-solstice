"""`solstice init` scaffolds a workspace; `solstice hooks install` arms the
plugin checkout's pre-push guard (KTD3, KTD13). All paths are synthetic."""

import json
import subprocess
from importlib import resources
from pathlib import Path

import pytest
import yaml

from conftest import OTHER_REMOTE, PLUGIN_REMOTE_HTTPS
from solstice.__main__ import main
from solstice.state import ENTITIES, launch_spend_limit
from solstice.workspace import resolve_workspace

REPO_ROOT = Path(__file__).resolve().parents[2]
ADAPTERS = {"dataforseo", "trustmrr", "scrapecreators", "freemius", "polar"}


def _git_config(repo: Path, key: str) -> str | None:
    out = subprocess.run(["git", "config", "--get", key], cwd=repo,
                         capture_output=True, text=True)
    return out.stdout.strip() if out.returncode == 0 else None


def _plugin_checkout(make_checkout, path: Path, remote: str = PLUGIN_REMOTE_HTTPS) -> Path:
    co = make_checkout(path, remote)
    (co / ".githooks").mkdir()
    hook = co / ".githooks" / "pre-push"
    hook.write_text("#!/bin/sh\nexit 1\n")
    hook.chmod(0o755)
    (co / ".claude-plugin").mkdir()
    (co / ".claude-plugin" / "plugin.json").write_text('{"name": "example", "version": "2.0.0-dev"}')
    return co


# --- init -------------------------------------------------------------------


def test_init_on_new_path_creates_full_scaffold(tmp_path, capsys):
    ws = tmp_path / "my-workspace"
    assert main(["init", str(ws)]) == 0

    cfg = yaml.safe_load((ws / ".solstice" / "config.yaml").read_text())
    assert cfg["workspace_root"] == "."
    assert cfg["budgets"] == {
        "factory_monthly_cap_usd": 50,
        "per_run_cap_usd": 5,
        "launch_spend_limit_usd": 50,
        "owner_hourly_rate_usd": 100,
    }
    assert cfg["adapters"] == {} and cfg["schedule"] == {}

    rubric = json.loads((ws / "rubric.json").read_text())
    assert rubric["version"].startswith("4")
    weights = {c["id"]: c["weight"] for c in rubric["components"]}
    assert weights == {"volume": 0.30, "trend": 0.15, "spend": 0.30,
                       "channel_reach": 0.15, "gap": 0.10}

    for plural in ENTITIES.values():
        assert (ws / "records" / plural).is_dir()

    manifest = yaml.safe_load((ws / "secrets-manifest.yaml").read_text())
    assert {s["adapter"] for s in manifest["secrets"]} == ADAPTERS
    assert (ws / "denylist.txt").is_file()
    ignore = (ws / ".gitignore").read_text().splitlines()
    for line in (".solstice/write.lock", ".solstice/write.lock.guard", ".solstice/rate/",
                 "*.tmp", ".env*"):
        assert line in ignore

    # The scaffold is immediately usable by the rest of the CLI.
    assert resolve_workspace(cwd=ws, env={}) == ws.resolve()
    assert launch_spend_limit(ws) == 50.0
    assert str(ws.resolve()) in capsys.readouterr().out


def test_init_on_empty_existing_dir_succeeds(tmp_path):
    ws = tmp_path / "empty"
    ws.mkdir()
    assert main(["init", str(ws)]) == 0
    assert (ws / ".solstice" / "config.yaml").is_file()


def test_init_allows_dir_holding_only_git(tmp_path):
    ws = tmp_path / "gitonly"
    ws.mkdir()
    subprocess.run(["git", "init", "-q"], cwd=ws, check=True)
    assert main(["init", str(ws)]) == 0


def test_init_refuses_non_empty_dir(tmp_path, capsys):
    ws = tmp_path / "busy"
    ws.mkdir()
    (ws / "notes.txt").write_text("synthetic")
    assert main(["init", str(ws)]) == 2
    assert "not empty" in capsys.readouterr().err
    assert not (ws / ".solstice").exists()


def test_init_refuses_file_path(tmp_path):
    f = tmp_path / "file"
    f.write_text("x")
    assert main(["init", str(f)]) == 2


def test_init_inside_plugin_checkout_is_refused(tmp_path, make_checkout, capsys):
    co = make_checkout(tmp_path / "plugin", PLUGIN_REMOTE_HTTPS)
    target = co / "nested" / "ws"
    assert main(["init", str(target)]) == 2
    assert "inside the public plugin repo" in capsys.readouterr().err
    assert not target.exists()


def test_init_inside_other_repo_is_allowed(tmp_path, make_checkout):
    co = make_checkout(tmp_path / "private", OTHER_REMOTE)
    assert main(["init", str(co / "ws")]) == 0


def test_template_is_package_data_and_repo_copy_is_the_same_tree():
    pkg = Path(str(resources.files("solstice") / "templates" / "workspace"))
    assert (pkg / "rubric.json").is_file()
    repo_copy = REPO_ROOT / "templates" / "workspace"
    assert repo_copy.resolve() == pkg.resolve()


def test_template_carries_no_paths_the_structural_check_forbids():
    from solstice.leakscan import scan_tree

    pkg = Path(str(resources.files("solstice") / "templates" / "workspace"))
    assert scan_tree(pkg) == []


# --- hooks install ---------------------------------------------------------


def test_hooks_install_sets_hooks_path(tmp_path, make_checkout):
    co = _plugin_checkout(make_checkout, tmp_path / "plugin")
    assert main(["hooks", "install", str(co)]) == 0
    assert _git_config(co, "core.hooksPath") == ".githooks"


def test_hooks_install_records_workspace_for_the_hook(tmp_path, make_checkout):
    co = _plugin_checkout(make_checkout, tmp_path / "plugin")
    ws = tmp_path / "ws"
    assert main(["init", str(ws)]) == 0
    assert main(["hooks", "install", str(co), "--workspace", str(ws)]) == 0
    assert _git_config(co, "solstice.workspace") == str(ws.resolve())


def test_hooks_install_refuses_workspace_inside_plugin(tmp_path, make_checkout):
    co = _plugin_checkout(make_checkout, tmp_path / "plugin")
    inner = co / "inner"
    inner.mkdir()
    assert main(["hooks", "install", str(co), "--workspace", str(inner)]) == 2
    assert _git_config(co, "solstice.workspace") is None


def test_hooks_install_refuses_dir_without_hook(tmp_path, make_checkout):
    co = make_checkout(tmp_path / "plain", PLUGIN_REMOTE_HTTPS)
    assert main(["hooks", "install", str(co)]) == 2
    assert _git_config(co, "core.hooksPath") is None


def test_init_with_plugin_checkout_arms_the_hook(tmp_path, make_checkout):
    co = _plugin_checkout(make_checkout, tmp_path / "plugin")
    ws = tmp_path / "ws"
    assert main(["init", str(ws), "--plugin-checkout", str(co)]) == 0
    assert _git_config(co, "core.hooksPath") == ".githooks"
    assert _git_config(co, "solstice.workspace") == str(ws.resolve())


@pytest.mark.parametrize("name", ["pre-push"])
def test_real_hook_is_executable(name):
    hook = REPO_ROOT / ".githooks" / name
    assert hook.is_file()
    assert hook.stat().st_mode & 0o111
