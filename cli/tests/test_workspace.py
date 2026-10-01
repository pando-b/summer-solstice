"""Workspace resolution fails closed and refuses the public plugin repo (KTD3)."""

from pathlib import Path

import pytest

from conftest import OTHER_REMOTE, PLUGIN_REMOTE_HTTPS, PLUGIN_REMOTE_SSH
from solstice.__main__ import main
from solstice.workspace import WorkspaceError, resolve_workspace

BOUNDARY = "inside the public plugin repo"


# --- SOLSTICE_WORKSPACE ---------------------------------------------------


def test_env_var_valid_workspace_is_returned(tmp_path):
    ws = tmp_path / "ws"
    ws.mkdir()
    got = resolve_workspace(cwd=tmp_path, env={"SOLSTICE_WORKSPACE": str(ws)})
    assert got == ws.resolve()


def test_env_var_wins_over_config(tmp_path, write_config):
    ws = tmp_path / "from-env"
    ws.mkdir()
    write_config(tmp_path, "workspace_root: .\n")
    got = resolve_workspace(cwd=tmp_path, env={"SOLSTICE_WORKSPACE": str(ws)})
    assert got == ws.resolve()


def test_env_var_missing_path_fails_closed(tmp_path):
    with pytest.raises(WorkspaceError, match="does not exist"):
        resolve_workspace(
            cwd=tmp_path, env={"SOLSTICE_WORKSPACE": str(tmp_path / "nope")}
        )


def test_env_var_file_not_directory_fails_closed(tmp_path):
    f = tmp_path / "file.txt"
    f.write_text("x")
    with pytest.raises(WorkspaceError, match="not a directory"):
        resolve_workspace(cwd=tmp_path, env={"SOLSTICE_WORKSPACE": str(f)})


@pytest.mark.parametrize("remote", [PLUGIN_REMOTE_HTTPS, PLUGIN_REMOTE_SSH])
def test_env_var_inside_plugin_checkout_is_refused(tmp_path, make_checkout, remote):
    checkout = make_checkout(tmp_path / "plugin", remote)
    inner = checkout / "sub"
    inner.mkdir()
    with pytest.raises(WorkspaceError, match=BOUNDARY):
        resolve_workspace(cwd=tmp_path, env={"SOLSTICE_WORKSPACE": str(inner)})


def test_env_var_symlink_into_plugin_checkout_is_refused(tmp_path, make_checkout):
    checkout = make_checkout(tmp_path / "plugin", PLUGIN_REMOTE_HTTPS)
    link = tmp_path / "innocent-link"
    link.symlink_to(checkout, target_is_directory=True)
    with pytest.raises(WorkspaceError, match=BOUNDARY):
        resolve_workspace(cwd=tmp_path, env={"SOLSTICE_WORKSPACE": str(link)})


# --- .solstice/config.yaml ------------------------------------------------


def test_config_in_parent_directory_is_found(tmp_path, write_config):
    write_config(tmp_path, "workspace_root: .\n")
    deep = tmp_path / "a" / "b"
    deep.mkdir(parents=True)
    assert resolve_workspace(cwd=deep, env={}) == tmp_path.resolve()


def test_config_without_workspace_root_defaults_to_config_dir(tmp_path, write_config):
    write_config(tmp_path, "{}\n")
    assert resolve_workspace(cwd=tmp_path, env={}) == tmp_path.resolve()


def test_config_relative_workspace_root_resolves_against_config_owner(
    tmp_path, write_config
):
    (tmp_path / "data").mkdir()
    write_config(tmp_path, "workspace_root: data\n")
    sub = tmp_path / "x"
    sub.mkdir()
    assert resolve_workspace(cwd=sub, env={}) == (tmp_path / "data").resolve()


def test_config_workspace_root_missing_fails_closed(tmp_path, write_config):
    write_config(tmp_path, "workspace_root: missing\n")
    with pytest.raises(WorkspaceError, match="does not exist"):
        resolve_workspace(cwd=tmp_path, env={})


def test_config_malformed_fails_closed(tmp_path, write_config):
    write_config(tmp_path, "workspace_root: [unclosed\n")
    with pytest.raises(WorkspaceError, match="config"):
        resolve_workspace(cwd=tmp_path, env={})


def test_config_non_mapping_fails_closed(tmp_path, write_config):
    write_config(tmp_path, "- just\n- a list\n")
    with pytest.raises(WorkspaceError, match="mapping"):
        resolve_workspace(cwd=tmp_path, env={})


def test_nothing_found_fails_and_never_falls_back_to_cwd(tmp_path):
    lonely = tmp_path / "lonely"
    lonely.mkdir()
    with pytest.raises(WorkspaceError, match="no workspace"):
        resolve_workspace(cwd=lonely, env={})


@pytest.mark.parametrize("remote", [PLUGIN_REMOTE_HTTPS, PLUGIN_REMOTE_SSH])
def test_config_resolving_inside_plugin_checkout_is_refused(
    tmp_path, make_checkout, write_config, remote
):
    checkout = make_checkout(tmp_path / "plugin", remote)
    write_config(checkout, "workspace_root: .\n")
    with pytest.raises(WorkspaceError, match=BOUNDARY):
        resolve_workspace(cwd=checkout, env={})


def test_other_git_remote_is_allowed(tmp_path, make_checkout, write_config):
    ws = make_checkout(tmp_path / "ws", OTHER_REMOTE)
    write_config(ws, "workspace_root: .\n")
    assert resolve_workspace(cwd=ws, env={}) == ws.resolve()


def test_nested_repo_inside_plugin_checkout_is_refused(
    tmp_path, make_checkout, write_config
):
    checkout = make_checkout(tmp_path / "plugin", PLUGIN_REMOTE_HTTPS)
    nested = make_checkout(checkout / "nested-ws", OTHER_REMOTE)
    write_config(nested, "workspace_root: .\n")
    with pytest.raises(WorkspaceError, match=BOUNDARY):
        resolve_workspace(cwd=nested, env={})


@pytest.mark.parametrize(
    "url",
    [
        "https://github.com/pando-b/summer-solstice",
        "https://github.com/pando-b/summer-solstice.git",
        "https://github.com/pando-b/summer-solstice/",
        "git@github.com:pando-b/summer-solstice.git",
        "ssh://git@github.com/pando-b/summer-solstice.git",
        "HTTPS://GitHub.com/Pando-B/Summer-Solstice.git",
    ],
)
def test_plugin_remote_forms_are_recognized(url):
    from solstice.workspace import is_plugin_remote

    assert is_plugin_remote(url)


@pytest.mark.parametrize(
    "url",
    [
        "https://github.com/pando-b/summer-solstice-fork.git",
        "https://github.com/example-owner/summer-solstice.git",
        OTHER_REMOTE,
    ],
)
def test_non_plugin_remotes_are_not_matched(url):
    from solstice.workspace import is_plugin_remote

    assert not is_plugin_remote(url)


# --- CLI entry point ------------------------------------------------------


def test_cli_workspace_prints_path_on_success(tmp_path, monkeypatch, capsys):
    ws = tmp_path / "ws"
    ws.mkdir()
    monkeypatch.setenv("SOLSTICE_WORKSPACE", str(ws))
    assert main(["workspace"]) == 0
    assert capsys.readouterr().out.strip() == str(ws.resolve())


def test_cli_workspace_fails_non_zero_with_message(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("SOLSTICE_WORKSPACE", str(tmp_path / "missing"))
    assert main(["workspace"]) != 0
    err = capsys.readouterr().err
    assert "does not exist" in err


def test_cli_workspace_boundary_refusal(tmp_path, monkeypatch, capsys, make_checkout):
    checkout = make_checkout(tmp_path / "plugin", PLUGIN_REMOTE_SSH)
    monkeypatch.setenv("SOLSTICE_WORKSPACE", str(checkout))
    assert main(["workspace"]) != 0
    assert BOUNDARY in capsys.readouterr().err


def test_cli_version(capsys):
    from solstice import __version__

    with pytest.raises(SystemExit) as exc:
        main(["--version"])
    assert exc.value.code == 0
    assert __version__ in capsys.readouterr().out
