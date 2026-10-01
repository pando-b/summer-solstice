"""The machine contract agents parse: one JSON error envelope on stderr, stable
`kind` tokens, documented exit codes, and `record events`."""

import json
from datetime import timedelta

import pytest

import factories as f
from solstice import state
from solstice.__main__ import main
from solstice.errors import KINDS


@pytest.fixture
def cli(ws, monkeypatch, capsys, tmp_path):
    monkeypatch.setenv("SOLSTICE_WORKSPACE", str(ws))

    def run(*argv, body=None):
        if body is not None:
            p = tmp_path / "body.json"
            p.write_text(json.dumps(body))
            argv = [a if a != "@body" else str(p) for a in argv]
        code = main(list(argv))
        cap = capsys.readouterr()
        return code, cap.out, cap.err

    return run


def _envelope(err: str) -> dict:
    data = json.loads(err)
    assert set(data) == {"error"}
    assert set(data["error"]) == {"kind", "message", "details"}
    assert data["error"]["kind"] in KINDS
    return data["error"]


def _create(cli, entity, body):
    code, out, _ = cli("record", "create", entity, "--file", "@body", body=body)
    assert code == 0
    return json.loads(out)


def test_table_refusal_lists_allowed_statuses(cli):
    prod = _create(cli, "product", f.product())
    code, out, err = cli("record", "transition", "product", prod["id"], "live")
    assert code == 1 and out == ""
    e = _envelope(err)
    assert e["kind"] == "transition_refused"
    assert e["details"] == {"from": "qualified", "to": "live", "allowed": ["building", "testing"]}
    assert "qualified -> live" in e["message"]


def test_guard_refusal_names_the_rule(cli):
    prod = _create(cli, "product", f.product(estimated_upfront_spend_usd=280))
    assert cli("record", "transition", "product", prod["id"], "testing")[0] == 0
    for _ in range(2):
        assert cli("record", "event", "product", prod["id"], "--file", "@body",
                   body=f.buy_signal("pre_order"))[0] == 0
    code, _, err = cli("record", "transition", "product", prod["id"], "building")
    assert code == 1
    e = _envelope(err)
    assert e["kind"] == "transition_refused"
    d = e["details"]
    assert d["from"] == "testing" and d["to"] == "building"
    assert d["allowed"] == ["building", "parked"]
    assert d["rule"] == "pre_orders_to_unlock" and d["requirement"] == "R21"
    assert (d["needed"], d["have"]) == (3, 2)


def test_missing_record_is_not_found(cli):
    code, out, err = cli("record", "get", "problem", "01JZZZZZZZZZZZZZZZZZZZZZZZ")
    assert code == 1 and out == ""
    e = _envelope(err)
    assert e["kind"] == "not_found"
    assert e["details"] == {"entity": "problem", "id": "01JZZZZZZZZZZZZZZZZZZZZZZZ"}


def test_invalid_record_kind(cli):
    code, _, err = cli("record", "create", "problem", "--file", "@body",
                       body=f.problem(demand=[f.demand(method="model")]))
    assert code == 1 and _envelope(err)["kind"] == "invalid_record"


def test_held_lock_is_lock_held_exit_3(cli, ws, monkeypatch):
    monkeypatch.setattr(state, "LOCK_WAIT_SECONDS", 0)
    lock = ws / ".solstice" / "write.lock"
    lock.parent.mkdir(parents=True)
    now = state.now_utc()
    lock.write_text(json.dumps({"pid": 99999, "acquired_at": f.ts(now),
                                "expires_at": f.ts(now + timedelta(hours=1))}))
    code, out, err = cli("record", "create", "problem", "--file", "@body", body=f.problem())
    assert code == 3 and out == ""
    e = _envelope(err)
    assert e["kind"] == "lock_held" and e["details"]["pid"] == 99999


def test_no_workspace_is_workspace_exit_2(cli, tmp_path, monkeypatch):
    monkeypatch.setenv("SOLSTICE_WORKSPACE", str(tmp_path / "missing"))
    code, out, err = cli("record", "list", "problem")
    assert code == 2 and out == ""
    e = _envelope(err)
    assert e["kind"] == "workspace" and "does not exist" in e["message"]


@pytest.mark.parametrize("argv", [["record", "nosuch"], ["nosuch"], ["record", "get", "problem"]])
def test_usage_error_exits_64_with_empty_stdout(argv, capsys):
    with pytest.raises(SystemExit) as exc:
        main(argv)
    assert exc.value.code == 64
    cap = capsys.readouterr()
    assert cap.out == ""
    assert _envelope(cap.err)["kind"] == "usage"


def test_unexpected_failure_is_internal_without_traceback(cli, monkeypatch):
    def boom(*a, **kw):
        raise ZeroDivisionError("synthetic")

    monkeypatch.setattr(state.Store, "list", boom)
    code, out, err = cli("record", "list", "problem")
    assert code == 70 and out == ""
    e = _envelope(err)
    assert e["kind"] == "internal" and e["details"] == {"type": "ZeroDivisionError"}
    assert "Traceback" not in err


def test_record_events_prints_history_in_order(cli):
    rec = _create(cli, "problem", f.problem())
    assert cli("record", "update", "problem", rec["id"], "--file", "@body",
               body={"slug": "example-widget-restock-dates"})[0] == 0
    assert cli("record", "transition", "problem", rec["id"], "rejected")[0] == 0
    code, out, _ = cli("record", "events", "problem", rec["id"])
    assert code == 0
    events = json.loads(out)
    assert [e["type"] for e in events] == ["created", "updated", "transition"]
    assert events[2]["to"] == "rejected"


def test_record_events_for_missing_record_is_not_found(cli):
    code, _, err = cli("record", "events", "problem", "01JZZZZZZZZZZZZZZZZZZZZZZZ")
    assert code == 1 and _envelope(err)["kind"] == "not_found"


@pytest.mark.parametrize("argv", [["record", "events", "problem"],
                                  ["record", "transition", "problem"]])
def test_corrupt_history_line_is_an_error_not_a_traceback(cli, ws, argv):
    rec = _create(cli, "problem", f.problem())
    path = ws / "records" / "problems" / f"{rec['id']}.events.jsonl"
    with path.open("a") as fh:
        fh.write("{not json\n")
    extra = ["rejected"] if argv[1] == "transition" else []
    code, out, err = cli(*argv, rec["id"], *extra)
    assert code == 1 and out == ""
    e = _envelope(err)
    assert e["kind"] == "corrupt_history"
    assert e["details"] == {"path": str(path), "line": 2}
    assert "line 2" in e["message"] and "Traceback" not in err
