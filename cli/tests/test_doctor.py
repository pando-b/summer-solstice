"""`solstice doctor` reports ok / missing-optional / missing-required with
injectable probes. Every key value and path here is synthetic."""

import json
import subprocess
from pathlib import Path

import pytest

from conftest import PLUGIN_REMOTE_HTTPS
from solstice import doctor
from solstice.__main__ import main

OK, OPT, REQ = "ok", "missing-optional", "missing-required"


def _plugin(make_checkout, path: Path, version: str = "2.0.0-dev", hooks: bool = True) -> Path:
    co = make_checkout(path, PLUGIN_REMOTE_HTTPS)
    (co / ".claude-plugin").mkdir()
    (co / ".claude-plugin" / "plugin.json").write_text(
        json.dumps({"name": "example", "version": version}))
    (co / ".githooks").mkdir()
    hook = co / ".githooks" / "pre-push"
    hook.write_text("#!/bin/sh\nexit 1\n")
    hook.chmod(0o755)
    if hooks:
        subprocess.run(["git", "config", "core.hooksPath", ".githooks"], cwd=co, check=True)
    return co


def _workspace(tmp_path: Path) -> Path:
    ws = tmp_path / "ws"
    assert main(["init", str(ws)]) == 0
    return ws


def _probes(tmp_path, plugin_root, *, cli="2.0.0.dev0", env=None, tools=("uv", "infisical", "npx"),
            plugins=("compound-engineering@example-market",)):
    home = tmp_path / "home"
    (home / ".claude" / "plugins").mkdir(parents=True, exist_ok=True)
    (home / ".claude" / "plugins" / "installed_plugins.json").write_text(
        json.dumps({"version": 2, "plugins": {k: [] for k in plugins}}))
    return doctor.Probes(
        cli_version=cli,
        plugin_root=plugin_root,
        env=dict(env or {}),
        cwd=tmp_path,
        home=home,
        which=lambda name: f"/opt/bin/{name}" if name in tools else None,
    )


def _status(report, name):
    for c in report["checks"]:
        if c["name"] == name:
            return c["status"]
    raise AssertionError(f"no check named {name}: {[c['name'] for c in report['checks']]}")


# --- version normalization --------------------------------------------------


@pytest.mark.parametrize("a,b", [
    ("2.0.0-dev", "2.0.0.dev0"),
    ("2.0.0.dev", "2.0.0.dev0"),
    ("v2.0.0", "2.0.0"),
    ("2.0.0-rc.1", "2.0.0rc1"),
    ("2.0.0-alpha", "2.0.0a0"),
    ("2.0.0-beta.2", "2.0.0b2"),
    ("2.0.0.post1", "2.0.0-post1"),
])
def test_versions_normalize_equal(a, b):
    assert doctor.normalize_version(a) == doctor.normalize_version(b)


@pytest.mark.parametrize("a,b", [("2.0.0", "2.0.1"), ("2.0.0", "2.0.0.dev0"), ("2.0.0a1", "2.0.0b1")])
def test_versions_normalize_different(a, b):
    assert doctor.normalize_version(a) != doctor.normalize_version(b)


# --- checks -----------------------------------------------------------------


def test_healthy_setup_is_ok(tmp_path, make_checkout):
    co = _plugin(make_checkout, tmp_path / "plugin")
    ws = _workspace(tmp_path)
    subprocess.run(["git", "config", "solstice.workspace", str(ws)], cwd=co, check=True)
    report = doctor.run_checks(_probes(tmp_path, co, env={"SOLSTICE_WORKSPACE": str(ws)}))
    assert _status(report, "solstice version") == OK
    assert _status(report, "pre-push hook") == OK
    assert _status(report, "workspace") == OK
    assert _status(report, "uv") == OK
    assert _status(report, "compound-engineering plugin") == OK
    assert report["ok"] is True


def test_no_keys_reports_keyless_mode(tmp_path, make_checkout):
    co = _plugin(make_checkout, tmp_path / "plugin")
    report = doctor.run_checks(_probes(tmp_path, co, env={}))
    assert report["mode"] == "keyless"
    assert report["keyless_sources"] == ["WordPress.org", "Hacker News"]
    for adapter in ("DataForSEO", "Apify", "TrustMRR", "Freemius", "Polar"):
        assert _status(report, f"{adapter} keys") == OPT


def test_keys_present_are_ok_and_values_never_printed(tmp_path, make_checkout, capsys):
    co = _plugin(make_checkout, tmp_path / "plugin")
    secret_value = "synthetic-" + "value-" * 4
    env = {"DATAFORSEO_LOGIN": secret_value, "DATAFORSEO_PASSWORD": secret_value}
    report = doctor.run_checks(_probes(tmp_path, co, env=env))
    assert _status(report, "DataForSEO keys") == OK
    assert report["mode"] == "keyed"
    doctor.print_report(report, as_json=True)
    doctor.print_report(report, as_json=False)
    assert secret_value not in capsys.readouterr().out
    assert secret_value not in json.dumps(report)


def test_partial_adapter_keys_are_named_missing(tmp_path, make_checkout):
    co = _plugin(make_checkout, tmp_path / "plugin")
    report = doctor.run_checks(_probes(tmp_path, co, env={"DATAFORSEO_LOGIN": "synthetic"}))
    check = next(c for c in report["checks"] if c["name"] == "DataForSEO keys")
    assert check["status"] == OPT
    assert "DATAFORSEO_PASSWORD" in check["detail"]


def test_version_mismatch_is_missing_required(tmp_path, make_checkout):
    co = _plugin(make_checkout, tmp_path / "plugin", version="2.0.1")
    report = doctor.run_checks(_probes(tmp_path, co, cli="2.0.0"))
    assert _status(report, "solstice version") == REQ
    assert report["ok"] is False


def test_dev_versions_match_after_normalization(tmp_path, make_checkout):
    co = _plugin(make_checkout, tmp_path / "plugin", version="2.0.0-dev")
    report = doctor.run_checks(_probes(tmp_path, co, cli="2.0.0.dev0"))
    assert _status(report, "solstice version") == OK


def test_hooks_path_unset_is_missing_required(tmp_path, make_checkout):
    co = _plugin(make_checkout, tmp_path / "plugin", hooks=False)
    report = doctor.run_checks(_probes(tmp_path, co))
    assert _status(report, "pre-push hook") == REQ


def test_hooks_path_pointing_elsewhere_is_missing_required(tmp_path, make_checkout):
    co = _plugin(make_checkout, tmp_path / "plugin", hooks=False)
    subprocess.run(["git", "config", "core.hooksPath", "/dev/null"], cwd=co, check=True)
    report = doctor.run_checks(_probes(tmp_path, co))
    assert _status(report, "pre-push hook") == REQ


def test_non_executable_hook_is_missing_required(tmp_path, make_checkout):
    co = _plugin(make_checkout, tmp_path / "plugin")
    (co / ".githooks" / "pre-push").chmod(0o644)
    report = doctor.run_checks(_probes(tmp_path, co))
    assert _status(report, "pre-push hook") == REQ


def test_hook_without_resolvable_workspace_warns_pushes_will_block(tmp_path, make_checkout):
    co = _plugin(make_checkout, tmp_path / "plugin")
    report = doctor.run_checks(_probes(tmp_path, co, env={}))
    check = next(c for c in report["checks"] if c["name"] == "pre-push hook")
    assert check["status"] == REQ
    assert "block" in check["detail"]


def test_missing_uv_and_ce_are_required_and_infisical_optional(tmp_path, make_checkout):
    co = _plugin(make_checkout, tmp_path / "plugin")
    report = doctor.run_checks(_probes(tmp_path, co, tools=(), plugins=()))
    assert _status(report, "uv") == REQ
    assert _status(report, "compound-engineering plugin") == REQ
    assert _status(report, "infisical") == OPT
    assert _status(report, "impeccable") == OPT
    assert _status(report, "last30days") == OPT


def test_no_workspace_is_missing_required(tmp_path, make_checkout):
    co = _plugin(make_checkout, tmp_path / "plugin")
    report = doctor.run_checks(_probes(tmp_path, co, env={}))
    assert _status(report, "workspace") == REQ


def test_no_plugin_root_is_missing_required(tmp_path):
    report = doctor.run_checks(_probes(tmp_path, None))
    assert _status(report, "solstice version") == REQ


def test_cli_json_output(tmp_path, make_checkout, capsys, monkeypatch):
    co = _plugin(make_checkout, tmp_path / "plugin")
    monkeypatch.delenv("SOLSTICE_WORKSPACE", raising=False)
    monkeypatch.chdir(tmp_path)
    code = main(["doctor", "--json", "--plugin-root", str(co)])
    report = json.loads(capsys.readouterr().out)
    assert {c["status"] for c in report["checks"]} <= {OK, OPT, REQ}
    assert code == (0 if report["ok"] else 1)
