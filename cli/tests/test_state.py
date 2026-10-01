"""Record store: KTD1 layout, ULIDs, events, lock, migrate, validate CLI."""

import json
import re
from datetime import timedelta

import pytest

import factories as f
from solstice import state
from solstice.__main__ import main
from solstice.state import (
    SCHEMA_VERSION,
    LockError,
    RecordError,
    Store,
    new_ulid,
)

ULID_RE = re.compile(r"^[0-9A-HJKMNP-TV-Z]{26}$")


def _events(ws, plural, rid):
    path = ws / "records" / plural / f"{rid}.events.jsonl"
    return [json.loads(line) for line in path.read_text().splitlines()]


# --- ids and layout ---------------------------------------------------------


def test_ulids_are_crockford_26_chars_and_time_ordered(clock):
    a = new_ulid(clock())
    clock.advance(milliseconds=5)
    b = new_ulid(clock())
    assert ULID_RE.match(a) and ULID_RE.match(b)
    assert a < b


def test_create_writes_one_file_per_record_with_version_and_event(store, ws):
    rec = store.create("problem", f.problem())
    assert ULID_RE.match(rec["id"])
    assert rec["schema_version"] == SCHEMA_VERSION
    path = ws / "records" / "problems" / f"{rec['id']}.json"
    assert json.loads(path.read_text()) == rec
    assert [e["type"] for e in _events(ws, "problems", rec["id"])] == ["created"]


def test_problem_round_trips_create_get_list_unchanged(store):
    body = f.problem()
    rec = store.create("problem", body)
    for k, v in body.items():
        assert rec[k] == v
    assert store.get("problem", rec["id"]) == rec
    assert store.list("problem") == [rec]
    assert store.list("problem", status="found") == [rec]
    assert store.list("problem", status="dropped") == []


def test_create_rejects_invalid_record_and_writes_nothing(store, ws):
    with pytest.raises(RecordError, match="method"):
        store.create("problem", f.problem(demand=[f.demand(method="model")]))
    assert not list(ws.rglob("*.json"))


def test_create_refuses_caller_supplied_identity_fields(store):
    with pytest.raises(RecordError):
        store.create("problem", f.problem(id="01JAAAAAAAAAAAAAAAAAAAAAAA"))


@pytest.mark.parametrize("entity,body", [
    ("problem", {**{k: v for k, v in f.problem().items() if k != "demand"},
                 "status": "pending_evidence", "refetch_failures": 3, "pending_fetch": {
                     "adapter": "example_adapter", "error": "timeout",
                     "attempted_at": "2026-01-05T10:00:00Z"}}),
    ("product", f.product(test_started_at="2026-01-05T12:00:00Z")),
    ("product", f.product(awaiting_owner_from="testing")),
    ("approval", f.approval(approver="someone")),
    ("evidence", f.evidence(idempotency_key="https://example.com/x|2026-01-04")),
])
def test_create_refuses_lifecycle_managed_fields(store, ws, entity, body):
    with pytest.raises(RecordError, match="lifecycle|approvals flow|set by the CLI"):
        store.create(entity, body)
    assert not list(ws.rglob("*.json"))


def test_get_unknown_id_is_a_readable_error(store):
    with pytest.raises(RecordError, match="not found"):
        store.get("problem", "01JAAAAAAAAAAAAAAAAAAAAAAA")


def test_decision_with_owner_prereqs_round_trips_unchanged(store):
    body = f.decision(owner_prereqs=[
        {"kind": "account", "description": "Example payment account", "cost_usd": 0},
        {"kind": "license", "description": "Example asset license", "cost_usd": 280},
    ])
    rec = store.create("decision", body)
    got = store.get("decision", rec["id"])
    assert got["owner_prereqs"] == body["owner_prereqs"]
    assert got == rec


# --- evidence idempotency ---------------------------------------------------


def test_duplicate_evidence_same_url_same_fetch_date_is_not_recorded_twice(store):
    first = store.create("evidence", f.evidence(fetched_at="2026-01-04T10:00:00Z"))
    again = store.create("evidence", f.evidence(fetched_at="2026-01-04T18:45:00Z",
                                                summary="Re-fetch later the same day."))
    assert again["id"] == first["id"]
    assert len(store.list("evidence")) == 1
    other_day = store.create("evidence", f.evidence(fetched_at="2026-01-05T10:00:00Z"))
    assert other_day["id"] != first["id"]
    assert len(store.list("evidence")) == 2


# --- update and rename ------------------------------------------------------


def test_update_merges_patch_and_appends_history(store, ws, clock):
    rec = store.create("problem", f.problem())
    clock.advance(hours=1)
    got = store.update("problem", rec["id"], {"title": "Renamed synthetic problem"})
    assert got["title"] == "Renamed synthetic problem"
    assert got["updated_at"] != rec["updated_at"]
    ev = _events(ws, "problems", rec["id"])
    assert ev[-1]["type"] == "updated" and ev[-1]["fields"] == ["title"]


@pytest.mark.parametrize("field", ["id", "schema_version", "created_at", "status"])
def test_update_refuses_managed_fields(store, field):
    rec = store.create("problem", f.problem())
    with pytest.raises(RecordError):
        store.update("problem", rec["id"], {field: "x"})


def test_update_cannot_self_approve_an_approval(store):
    rec = store.create("approval", f.approval())
    with pytest.raises(RecordError):
        store.update("approval", rec["id"], {"approver": "someone"})


def test_update_validates_result(store):
    rec = store.create("problem", f.problem())
    with pytest.raises(RecordError):
        store.update("problem", rec["id"], {"demand": [f.demand(method="model")]})
    assert store.get("problem", rec["id"]) == rec


def test_product_slug_change_keeps_every_id_reference_resolving(store):
    prob = store.create("problem", f.problem())
    prod = store.create("product", f.product(problem_id=prob["id"]))
    dec = store.create("decision", f.decision(problem_id=prob["id"], product_id=prod["id"]))
    appr = store.create("approval", f.approval(product_id=prod["id"]))
    content = store.create("content_item", {"product_id": prod["id"], "channel": "example-forum",
                                            "kind": "launch_post", "status": "draft"})
    store.update("product", prod["id"], {"slug": "example-gadget", "name": "Example Gadget"})
    for entity, rec in (("decision", dec), ("approval", appr), ("content_item", content)):
        ref = store.get(entity, rec["id"])["product_id"]
        assert store.get("product", ref)["slug"] == "example-gadget"
    assert store.check_references() == []


def test_dangling_reference_is_reported(store):
    store.create("approval", f.approval(product_id="01JZZZZZZZZZZZZZZZZZZZZZZZ"))
    errs = store.check_references()
    assert errs and "01JZZZZZZZZZZZZZZZZZZZZZZZ" in errs[0]


# --- events -----------------------------------------------------------------


def test_buy_signal_event_is_validated_and_appended(store, ws):
    prod = store.create("product", f.product())
    store.add_event("product", prod["id"], f.buy_signal("pre_order"))
    assert _events(ws, "products", prod["id"])[-1]["kind"] == "pre_order"
    with pytest.raises(RecordError):
        store.add_event("product", prod["id"], f.buy_signal("rumour"))
    with pytest.raises(RecordError):
        store.add_event("product", prod["id"], {"type": "transition", "to": "live"})


def test_event_append_does_not_rewrite_record(store):
    prod = store.create("product", f.product())
    store.add_event("product", prod["id"], f.buy_signal())
    assert store.get("product", prod["id"]) == prod


# --- lock -------------------------------------------------------------------


def _hold_lock(ws, clock, seconds):
    lock = ws / ".solstice" / "write.lock"
    lock.parent.mkdir(parents=True, exist_ok=True)
    lock.write_text(json.dumps({
        "pid": 99999, "acquired_at": f.ts(clock()),
        "expires_at": f.ts(clock() + timedelta(seconds=seconds)),
    }))
    return lock


def test_second_writer_exits_with_lock_message_when_lock_held(store, ws, clock):
    _hold_lock(ws, clock, 60)
    with pytest.raises(LockError, match="locked"):
        store.create("problem", f.problem())


def test_second_writer_waits_for_release(ws, clock):
    lock = _hold_lock(ws, clock, 60)
    calls = []

    def fake_sleep(sec):
        calls.append(sec)
        lock.unlink()

    s = Store(ws, now=clock, lock_wait=5, sleep=fake_sleep)
    rec = s.create("problem", f.problem())
    assert calls and rec["id"]
    assert not lock.exists()


def test_expired_lock_is_reclaimed(store, ws, clock):
    lock = _hold_lock(ws, clock, 60)
    clock.advance(seconds=61)
    store.create("problem", f.problem())
    assert not lock.exists()


def test_lock_released_after_failed_write(store, ws):
    with pytest.raises(RecordError):
        store.create("problem", f.problem(demand=[]))
    assert not (ws / ".solstice" / "write.lock").exists()


# --- schema_version and migrate ---------------------------------------------


def _write_raw(ws, plural, rec):
    d = ws / "records" / plural
    d.mkdir(parents=True, exist_ok=True)
    (d / f"{rec['id']}.json").write_text(json.dumps(rec))


def _old_problem(rid="01JCCCCCCCCCCCCCCCCCCCCCCC"):
    rec = {"id": rid, "schema_version": 0, "created_at": "2026-01-01T00:00:00Z",
           "updated_at": "2026-01-01T00:00:00Z", **f.problem()}
    rec["name_v0"] = rec.pop("title")  # v0 called it name_v0
    return rec


def _migrate_v0(entity, rec):
    rec = dict(rec)
    if entity == "problem":
        rec["title"] = rec.pop("name_v0")
    rec["schema_version"] = 1
    return rec


def test_older_record_is_refused_until_migrated(store, ws, monkeypatch, capsys):
    monkeypatch.setitem(state.MIGRATIONS, 0, _migrate_v0)
    old = _old_problem()
    _write_raw(ws, "problems", old)
    with pytest.raises(RecordError, match="solstice migrate"):
        store.get("problem", old["id"])
    with pytest.raises(RecordError, match="solstice migrate"):
        store.list("problem")

    monkeypatch.setenv("SOLSTICE_WORKSPACE", str(ws))
    assert main(["record", "get", "problem", old["id"]]) != 0
    assert "solstice migrate" in capsys.readouterr().err

    assert main(["migrate"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out["migrated"] == [old["id"]]
    got = store.get("problem", old["id"])
    assert got["schema_version"] == SCHEMA_VERSION
    assert got["title"] == "Example widget owners lose track of restocks"
    assert _events(ws, "problems", old["id"])[-1]["type"] == "migrated"
    assert main(["validate"]) == 0


def test_migrate_without_registered_migration_fails(ws, monkeypatch, capsys):
    _write_raw(ws, "problems", _old_problem())
    monkeypatch.setenv("SOLSTICE_WORKSPACE", str(ws))
    assert main(["migrate"]) != 0
    assert "no migration" in capsys.readouterr().out


def test_newer_record_is_refused_with_upgrade_message(store, ws, monkeypatch, capsys):
    rec = {"id": "01JDDDDDDDDDDDDDDDDDDDDDDD", "schema_version": SCHEMA_VERSION + 1,
           "created_at": "2026-01-01T00:00:00Z", "updated_at": "2026-01-01T00:00:00Z",
           **f.problem()}
    _write_raw(ws, "problems", rec)
    with pytest.raises(RecordError, match="upgrade the CLI"):
        store.get("problem", rec["id"])
    monkeypatch.setenv("SOLSTICE_WORKSPACE", str(ws))
    assert main(["migrate"]) != 0
    assert "upgrade the CLI" in capsys.readouterr().out


# --- CLI --------------------------------------------------------------------


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
        out = json.loads(cap.out) if cap.out.strip() else None
        return code, out, cap.err

    return run


def test_cli_record_create_get_list_update(cli):
    code, rec, _ = cli("record", "create", "problem", "--file", "@body", body=f.problem())
    assert code == 0
    assert cli("record", "get", "problem", rec["id"])[1] == rec
    assert cli("record", "list", "problem", "--status", "found")[1] == [rec]
    code, upd, _ = cli("record", "update", "problem", rec["id"], "--file", "@body",
                       body={"slug": "example-widget-restock-dates"})
    assert code == 0 and upd["slug"] == "example-widget-restock-dates"


def test_cli_create_from_stdin(cli, monkeypatch):
    import io

    monkeypatch.setattr("sys.stdin", io.StringIO(json.dumps(f.problem())))
    code, rec, _ = cli("record", "create", "problem", "--file", "-")
    assert code == 0 and rec["status"] == "found"


def test_cli_create_invalid_is_non_zero_with_readable_error(cli):
    d = f.demand()
    del d["fetched_at"]
    code, _, err = cli("record", "create", "problem", "--file", "@body", body=f.problem(demand=[d]))
    assert code == 1
    assert "fetched_at" in err


def test_cli_event_and_transition(cli):
    _, prod, _ = cli("record", "create", "product", "--file", "@body", body=f.product())
    code, ev, _ = cli("record", "event", "product", prod["id"], "--file", "@body",
                      body=f.buy_signal())
    assert code == 0 and ev["type"] == "buy_signal"
    code, moved, _ = cli("record", "transition", "product", prod["id"], "building")
    assert code == 0 and moved["status"] == "building"
    code, _, err = cli("record", "transition", "product", prod["id"], "live")
    assert code == 1 and "building -> live" in err


def test_cli_lock_held_exits_with_lock_message(cli, ws, monkeypatch):
    monkeypatch.setattr(state, "LOCK_WAIT_SECONDS", 0)
    _hold_lock(ws, state.now_utc, 3600)
    code, _, err = cli("record", "create", "problem", "--file", "@body", body=f.problem())
    assert code == 3 and "locked" in err


def test_cli_validate_clean_workspace_passes(cli):
    cli("record", "create", "problem", "--file", "@body", body=f.problem())
    code, out, _ = cli("validate")
    assert code == 0 and out["ok"] is True and out["checked"] == 1


def test_cli_validate_fails_on_invalid_record(cli, ws):
    bad = {"id": "01JEEEEEEEEEEEEEEEEEEEEEEE", "schema_version": SCHEMA_VERSION,
           "created_at": "2026-01-01T00:00:00Z", "updated_at": "2026-01-01T00:00:00Z",
           **f.problem(demand=[f.demand(method="model")])}
    _write_raw(ws, "problems", bad)
    code, out, _ = cli("validate")
    assert code == 1 and out["ok"] is False
    assert any(bad["id"] in e for e in out["errors"])


def test_cli_validate_fails_on_filename_id_mismatch_and_bad_json(cli, ws):
    rec = {"id": "01JEEEEEEEEEEEEEEEEEEEEEEE", "schema_version": SCHEMA_VERSION,
           "created_at": "2026-01-01T00:00:00Z", "updated_at": "2026-01-01T00:00:00Z",
           **f.problem()}
    d = ws / "records" / "problems"
    d.mkdir(parents=True)
    (d / "01JFFFFFFFFFFFFFFFFFFFFFFF.json").write_text(json.dumps(rec))
    (d / "01JGGGGGGGGGGGGGGGGGGGGGGG.json").write_text("{not json")
    code, out, _ = cli("validate")
    assert code == 1 and len(out["errors"]) == 2
