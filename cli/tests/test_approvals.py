"""Approval records and the owner queue (R13, R18, KTD7, KTD8).

Every name, path, and payload here is synthetic."""

import io
import json
import re

import pytest

import factories as f
from solstice import approvals
from solstice.__main__ import main
from solstice.approvals import ApprovalError, Deps
from solstice.lifecycle import TransitionError
from solstice.state import RecordError, Store


def _shown_hash(text: str) -> str:
    return re.search(r"content hash: ([0-9a-f]{64})", text).group(1)


class Terminal:
    """A fake owner terminal: records what was shown, answers with `reply`."""

    def __init__(self, reply=None, tty=True):
        self.reply, self.tty, self.shown = reply, tty, []

    def deps(self, env=None) -> Deps:
        return Deps(env=env or {}, isatty=lambda: self.tty, ask=self._ask,
                    user=lambda: "example-owner")

    def _ask(self, text: str) -> str:
        self.shown.append(text)
        if self.reply is None:  # type the displayed prefix
            return _shown_hash(text)[:approvals.PREFIX_LEN] + "\n"
        return self.reply


def _product(store, status="building", **over):
    rec = store.create("product", f.product(**over))
    path = {"building": ["building"], "testing": ["testing"], "qualified": [],
            "built": ["building", "built"]}[status]
    for to in path:
        rec = store.transition("product", rec["id"], to)
    return rec


def _outbound(store, ws, **over):
    (ws / "media").mkdir(exist_ok=True)
    (ws / "media" / "shot.png").write_bytes(b"synthetic image bytes")
    body = {"subtype": "outbound", "title": "Launch post for example widget",
            "channel": "example-forum", "executor": "example_poster",
            "payload": {"text": "Example widget is live.", "price_cents": 1900},
            "attachments": ["media/shot.png"]}
    body.update(over)
    return approvals.request(store, body)


# --- request and hashing -----------------------------------------------------


def test_request_stores_attachment_hashes_and_starts_pending(store, ws):
    rec = _outbound(store, ws)
    assert rec["status"] == "pending"
    assert rec["attachments"] == [{"path": "media/shot.png",
                                   "sha256": approvals.file_sha256(ws / "media" / "shot.png")}]
    for k in ("approver", "approved_at", "content_hash"):
        assert rec.get(k) is None


@pytest.mark.parametrize("bad", ["../outside.png", "/etc/hosts", "media/../../outside.png"])
def test_request_refuses_attachments_outside_the_workspace(store, ws, tmp_path, bad):
    (tmp_path / "outside.png").write_bytes(b"x")
    with pytest.raises(ApprovalError, match="inside the workspace"):
        _outbound(store, ws, attachments=[bad])
    assert store.list("approval") == []


def test_request_refuses_a_missing_attachment(store, ws):
    with pytest.raises(ApprovalError, match="media/none.png"):
        _outbound(store, ws, attachments=["media/none.png"])


def test_request_refuses_approval_flow_fields(store, ws):
    with pytest.raises(RecordError, match="approvals flow"):
        _outbound(store, ws, approver="someone")


def test_hash_ignores_key_order_and_changes_on_edits(store, ws):
    a = _outbound(store, ws, payload={"text": "Hello", "price_cents": 1900})
    b = _outbound(store, ws, payload=json.loads('{"price_cents": 1900, "text": "Hello"}'))
    c = _outbound(store, ws, payload={"text": "Hellp", "price_cents": 1900})
    ha, hb, hc = (approvals.content_hash(store, r) for r in (a, b, c))
    assert ha == hb != hc
    for field, value in (("channel", "other-forum"), ("executor", "other_poster")):
        assert approvals.content_hash(store, {**a, field: value}) != ha
    (ws / "media" / "shot.png").write_bytes(b"synthetic image bytes, edited")
    assert approvals.content_hash(store, a) != ha


def test_hash_covers_the_product_id(store, ws):
    prod = _product(store)
    a = _outbound(store, ws)
    assert approvals.content_hash(store, {**a, "product_id": prod["id"]}) != approvals.content_hash(store, a)


# --- approve -----------------------------------------------------------------


def test_approve_records_approver_time_and_hash(store, ws, clock):
    rec = _outbound(store, ws)
    term = Terminal()
    got = approvals.approve(store, rec["id"], term.deps())
    expected = approvals.content_hash(store, rec)
    assert got["status"] == "approved"
    assert got["approver"] == "example-owner"
    assert got["approved_at"] == f.ts(clock())
    assert got["content_hash"] == expected
    assert expected in term.shown[0] and "Example widget is live." in term.shown[0]
    assert store.events("approval", rec["id"])[-1]["to"] == "approved"


def test_scheduled_run_marker_refuses_approve_but_not_request(store, ws):
    env = {approvals.SCHEDULED_RUN_ENV: "1"}
    rec = _outbound(store, ws)  # request accepted
    with pytest.raises(ApprovalError) as exc:
        approvals.approve(store, rec["id"], Terminal().deps(env=env))
    assert exc.value.kind == "approval" and approvals.SCHEDULED_RUN_ENV in exc.value.message
    assert store.get("approval", rec["id"])["status"] == "pending"


def test_approve_refuses_without_a_terminal(store, ws):
    rec = _outbound(store, ws)
    term = Terminal(tty=False)
    with pytest.raises(ApprovalError, match="terminal"):
        approvals.approve(store, rec["id"], term.deps())
    assert term.shown == []
    assert store.get("approval", rec["id"])["status"] == "pending"


def test_approve_refuses_a_wrong_prefix_and_leaves_the_item_unchanged(store, ws):
    rec = _outbound(store, ws)
    before = store.get("approval", rec["id"])
    with pytest.raises(ApprovalError, match="prefix"):
        approvals.approve(store, rec["id"], Terminal(reply="00000000\n").deps())
    assert store.get("approval", rec["id"]) == before


def test_approve_refuses_an_attachment_edited_after_the_request(store, ws):
    rec = _outbound(store, ws)
    (ws / "media" / "shot.png").write_bytes(b"swapped image")
    term = Terminal()
    with pytest.raises(ApprovalError, match="media/shot.png") as exc:
        approvals.approve(store, rec["id"], term.deps())
    assert exc.value.details["changed"] == ["media/shot.png"]
    assert term.shown == []
    assert store.get("approval", rec["id"])["status"] == "pending"


def test_approve_refuses_when_the_item_changes_while_the_owner_reviews(store, ws):
    rec = _outbound(store, ws)

    def ask(text):
        store.update("approval", rec["id"], {"payload": {"text": "Changed behind the owner"}})
        return _shown_hash(text)[:approvals.PREFIX_LEN]

    deps = Deps(env={}, isatty=lambda: True, ask=ask, user=lambda: "example-owner")
    with pytest.raises(ApprovalError, match="changed"):
        approvals.approve(store, rec["id"], deps)
    assert store.get("approval", rec["id"])["status"] == "pending"


def test_owner_prereq_cannot_be_approved_or_rejected(store):
    rec = approvals.request(store, f.approval())
    with pytest.raises(ApprovalError, match="close"):
        approvals.approve(store, rec["id"], Terminal().deps())
    with pytest.raises(ApprovalError, match="close"):
        approvals.reject(store, rec["id"], "not needed", Terminal().deps())


def test_an_approved_item_cannot_be_approved_again(store, ws):
    rec = _outbound(store, ws)
    approvals.approve(store, rec["id"], Terminal().deps())
    with pytest.raises(ApprovalError, match="approved"):
        approvals.approve(store, rec["id"], Terminal().deps())


# --- reject and close --------------------------------------------------------


def test_reject_records_reason_and_time(store, ws, clock):
    rec = _outbound(store, ws, subtype="irreversible", title="Raise example price")
    got = approvals.reject(store, rec["id"], "price too high for the niche", Terminal().deps())
    assert got["status"] == "rejected"
    assert got["rejection_reason"] == "price too high for the niche"
    assert got["rejected_at"] == f.ts(clock())
    assert store.events("approval", rec["id"])[-1]["reason"] == "price too high for the niche"


def test_reject_refuses_scheduled_runs_and_non_terminals(store, ws):
    rec = _outbound(store, ws)
    with pytest.raises(ApprovalError):
        approvals.reject(store, rec["id"], "no", Terminal().deps(env={approvals.SCHEDULED_RUN_ENV: "1"}))
    with pytest.raises(ApprovalError):
        approvals.reject(store, rec["id"], "no", Terminal(tty=False).deps())
    with pytest.raises(ApprovalError, match="reason"):
        approvals.reject(store, rec["id"], "  ", Terminal().deps())
    assert store.get("approval", rec["id"])["status"] == "pending"


def test_close_costly_owner_prereq_without_buy_signal_is_refused_by_r18(store):
    prod = _product(store)
    rec = approvals.request(store, f.approval(product_id=prod["id"], cost_usd=280))
    with pytest.raises(TransitionError) as exc:
        approvals.close(store, rec["id"])
    assert exc.value.kind == "transition_refused"
    assert exc.value.details["rule"] == "buy_signal_before_spend"
    store.add_event("product", prod["id"], f.buy_signal("paid_conversion"))
    assert approvals.close(store, rec["id"], reason="license bought")["status"] == "closed"


# --- aging (KTD7, KTD8) ------------------------------------------------------


def test_owner_prereq_open_8_days_is_listed_first_with_a_nudge(store, clock):
    prod = _product(store)
    old = approvals.request(store, f.approval(product_id=prod["id"], title="Create example account"))
    clock.advance(days=6)
    approvals.request(store, f.approval(product_id=prod["id"], title="Upload example artwork"))
    clock.advance(days=2)
    queue = approvals.list_queue(store)
    assert [q["id"] for q in queue][0] == old["id"]
    assert queue[0]["aging"]["nudge"] is True and queue[0]["aging"]["age_days"] == 8
    assert queue[1]["aging"]["nudge"] is False
    assert "aging" not in store.get("approval", old["id"])  # derived, never stored
    assert store.get("product", prod["id"])["status"] == "building"


def test_owner_prereq_open_15_days_parks_the_product_once(store, clock):
    prod = _product(store)
    rec = approvals.request(store, f.approval(product_id=prod["id"]))
    clock.advance(days=15)
    approvals.list_queue(store)
    got = store.get("product", prod["id"])
    assert got["status"] == "awaiting_owner" and got["awaiting_owner_from"] == "building"
    events = store.events("product", prod["id"])
    assert events[-1]["reason"] == "parked" and events[-1]["approval_id"] == rec["id"]
    n = len(events)
    approvals.list_queue(store)
    approvals.show(store, rec["id"])
    assert len(store.events("product", prod["id"])) == n
    assert store.get("product", prod["id"])["status"] == "awaiting_owner"


def test_show_also_parks(store, clock):
    prod = _product(store, status="built")
    rec = approvals.request(store, f.approval(product_id=prod["id"]))
    clock.advance(days=14)
    shown = approvals.show(store, rec["id"])
    assert shown["aging"]["nudge"] is True
    assert store.get("product", prod["id"])["status"] == "awaiting_owner"


def test_costly_prereq_on_testing_product_does_not_age_without_buy_signal(store, clock):
    prod = _product(store, status="testing", estimated_upfront_spend_usd=280)
    rec = approvals.request(store, f.approval(product_id=prod["id"], cost_usd=280,
                                              title="Buy example license"))
    clock.advance(days=15)
    item = approvals.show(store, rec["id"])
    assert item["aging"]["nudge"] is False and item["aging"]["age_days"] is None
    assert store.get("product", prod["id"])["status"] == "testing"


def test_costly_prereq_ages_from_the_first_buy_signal(store, clock):
    prod = _product(store)
    rec = approvals.request(store, f.approval(product_id=prod["id"], cost_usd=280))
    clock.advance(days=20)
    store.add_event("product", prod["id"], f.buy_signal("pre_order"))
    clock.advance(days=8)
    item = approvals.show(store, rec["id"])
    assert item["aging"]["age_days"] == 8 and item["aging"]["nudge"] is True
    assert store.get("product", prod["id"])["status"] == "building"
    clock.advance(days=6)
    approvals.list_queue(store)
    assert store.get("product", prod["id"])["status"] == "awaiting_owner"


def test_aging_never_moves_a_testing_product(store, clock):
    prod = _product(store, status="testing")
    approvals.request(store, f.approval(product_id=prod["id"]))
    clock.advance(days=20)
    approvals.list_queue(store)
    assert store.get("product", prod["id"])["status"] == "testing"


def test_closed_items_leave_the_queue_and_do_not_park(store, clock):
    prod = _product(store)
    rec = approvals.request(store, f.approval(product_id=prod["id"]))
    approvals.close(store, rec["id"])
    clock.advance(days=20)
    assert approvals.list_queue(store) == []
    assert [q["id"] for q in approvals.list_queue(store, status="all")] == [rec["id"]]
    assert store.get("product", prod["id"])["status"] == "building"


# --- CLI ---------------------------------------------------------------------


class _TTYStdin(io.StringIO):
    def isatty(self):
        return True


@pytest.fixture
def cli(ws, monkeypatch, capsys, tmp_path):
    monkeypatch.setenv("SOLSTICE_WORKSPACE", str(ws))
    monkeypatch.delenv(approvals.SCHEDULED_RUN_ENV, raising=False)

    def run(*argv, body=None):
        if body is not None:
            p = tmp_path / "body.json"
            p.write_text(json.dumps(body))
            argv = [a if a != "@body" else str(p) for a in argv]
        code = main(list(argv))
        cap = capsys.readouterr()
        return code, cap.out, cap.err

    return run


def _request_cli(cli, ws, subtype="outbound"):
    (ws / "page.html").write_text("<p>synthetic</p>")
    body = {"subtype": subtype, "title": "Example item", "channel": "example-forum",
            "executor": "example_poster", "payload": {"text": "hi"}, "attachments": ["page.html"]}
    code, out, err = cli("approvals", "request", "--file", "@body", body=body)
    assert code == 0, err
    return json.loads(out)


def test_cli_every_decided_subtype_requests_approves_and_rejects(cli, ws, monkeypatch):
    for subtype in ("outbound", "irreversible"):
        rec = _request_cli(cli, ws, subtype)
        h = approvals.content_hash(Store(ws), rec)
        monkeypatch.setattr("sys.stdin", _TTYStdin(h[:8] + "\n"))
        code, out, err = cli("approvals", "approve", rec["id"])
        assert code == 0, err
        assert json.loads(out)["content_hash"] == h
        assert h in err  # the hash is shown on the terminal, not on stdout

        rec = _request_cli(cli, ws, subtype)
        monkeypatch.setattr("sys.stdin", _TTYStdin(""))
        code, out, err = cli("approvals", "reject", rec["id"], "--reason", "not now")
        assert code == 0, err
        assert json.loads(out)["status"] == "rejected"


def test_cli_owner_prereq_requests_lists_shows_and_closes(cli):
    code, out, _ = cli("approvals", "request", "--file", "@body", body=f.approval())
    rec = json.loads(out)
    code, out, _ = cli("approvals", "list")
    assert code == 0 and [q["id"] for q in json.loads(out)] == [rec["id"]]
    code, out, _ = cli("approvals", "show", rec["id"])
    assert code == 0 and json.loads(out)["aging"]["nudge"] is False
    code, out, _ = cli("approvals", "close", rec["id"])
    assert code == 0 and json.loads(out)["status"] == "closed"


def test_cli_approve_without_a_terminal_is_an_approval_envelope(cli, ws, monkeypatch):
    rec = _request_cli(cli, ws)
    monkeypatch.setattr("sys.stdin", io.StringIO("whatever\n"))
    code, out, err = cli("approvals", "approve", rec["id"])
    assert code == 1 and out == ""
    assert json.loads(err)["error"]["kind"] == "approval"


def test_cli_scheduled_run_marker_refuses_approve_and_accepts_request(cli, ws, monkeypatch):
    monkeypatch.setenv(approvals.SCHEDULED_RUN_ENV, "1")
    rec = _request_cli(cli, ws)
    monkeypatch.setattr("sys.stdin", _TTYStdin("00000000\n"))
    code, out, err = cli("approvals", "approve", rec["id"])
    assert code == 1 and json.loads(err)["error"]["kind"] == "approval"


def test_cli_close_guard_uses_the_transition_envelope(cli):
    code, out, _ = cli("record", "create", "product", "--file", "@body", body=f.product())
    prod = json.loads(out)
    code, out, _ = cli("approvals", "request", "--file", "@body",
                       body=f.approval(product_id=prod["id"], cost_usd=280))
    rec = json.loads(out)
    code, out, err = cli("approvals", "close", rec["id"])
    e = json.loads(err)["error"]
    assert code == 1 and e["kind"] == "transition_refused"
    assert e["details"]["rule"] == "buy_signal_before_spend"
