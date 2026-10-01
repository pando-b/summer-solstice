"""Product and problem lifecycle per the plan's state diagram (KTD6, R18, R21; AE5)."""

import json

import pytest

import factories as f
from solstice.lifecycle import TransitionError

LIVE_AT = "2026-01-20T00:00:00Z"


def _events(ws, rid):
    path = ws / "records" / "products" / f"{rid}.events.jsonl"
    return [json.loads(line) for line in path.read_text().splitlines()]


def _product(store, *path, **over):
    rec = store.create("product", f.product(**over))
    for status in path:
        fields = {"channel_live_at": LIVE_AT} if status == "live" else None
        rec = store.transition("product", rec["id"], status, fields)
    return rec


# --- legal / illegal transitions -------------------------------------------


def test_product_must_be_created_at_qualified(store):
    with pytest.raises(Exception, match="qualified"):
        store.create("product", f.product(status="building"))


def test_happy_path_through_review_to_growing(store):
    rec = _product(store, "building", "built", "in_review", "live", "growing", "selling")
    assert rec["status"] == "selling"
    assert rec["channel_live_at"] == LIVE_AT


@pytest.mark.parametrize("path,bad", [
    ((), "live"),
    ((), "built"),
    (("building",), "in_review"),
    (("building", "built", "live"), "building"),
    (("building", "built", "live", "killing"), "growing"),
])
def test_illegal_transitions_are_rejected(store, path, bad):
    rec = _product(store, *path)
    with pytest.raises(TransitionError, match="not allowed"):
        store.transition("product", rec["id"], bad)


def test_building_to_live_is_rejected(store):
    rec = _product(store, "building")
    with pytest.raises(TransitionError):
        store.transition("product", rec["id"], "live")
    with pytest.raises(TransitionError):
        store.transition("product", rec["id"], "live", {"channel_live_at": LIVE_AT})


@pytest.mark.parametrize("path", [("building", "built"), ("building", "built", "in_review")])
def test_live_requires_channel_live_at(store, path):
    rec = _product(store, *path)
    with pytest.raises(TransitionError, match="channel_live_at"):
        store.transition("product", rec["id"], "live")
    got = store.transition("product", rec["id"], "live", {"channel_live_at": LIVE_AT})
    assert got["status"] == "live"


def test_marketplace_rejection_returns_to_building_and_appends_history(store, ws):
    rec = _product(store, "building", "built", "in_review")
    before = len(_events(ws, rec["id"]))
    got = store.transition("product", rec["id"], "building", {"reason": "example review note"})
    assert got["status"] == "building"
    ev = _events(ws, rec["id"])
    assert len(ev) == before + 1
    assert ev[-1] | {"at": None} == {"type": "transition", "from": "in_review", "to": "building",
                                    "reason": "example review note", "at": None}


def test_terminal_states_have_no_exits(store):
    rec = _product(store, "building", "built", "live", "killing", "sunset")
    for to in ("live", "awaiting_owner", "growing"):
        with pytest.raises(TransitionError):
            store.transition("product", rec["id"], to)


# --- awaiting_owner ---------------------------------------------------------


def test_awaiting_owner_returns_only_to_prior_state(store):
    rec = _product(store, "building", "built")
    got = store.transition("product", rec["id"], "awaiting_owner", {"reason": "needs example key"})
    assert got["awaiting_owner_from"] == "built"
    with pytest.raises(TransitionError, match="built"):
        store.transition("product", rec["id"], "in_review")
    got = store.transition("product", rec["id"], "built")
    assert got["status"] == "built" and "awaiting_owner_from" not in got


# --- live cap (KTD6) ---------------------------------------------------------


def test_fourth_product_into_building_rejected_with_cap_message(store):
    _product(store, "building")
    _product(store, "building", "built", "live")
    _product(store, "building", "awaiting_owner")
    fourth = _product(store)
    with pytest.raises(TransitionError, match="live cap"):
        store.transition("product", fourth["id"], "building")


def test_problems_and_qualified_products_do_not_count(store):
    for i in range(10):
        store.create("problem", f.problem(slug=f"example-problem-{i}"))
    _product(store)
    _product(store)
    _product(store, "building")
    _product(store, "building")
    third = _product(store)
    assert store.transition("product", third["id"], "building")["status"] == "building"


def test_growing_selling_testing_parked_do_not_count(store, clock):
    for _ in range(3):
        _product(store, "building", "built", "live", "growing")
    _product(store, "building", "built", "live", "growing", "selling")
    _product(store, "testing", estimated_upfront_spend_usd=280)
    fourth = _product(store)
    assert store.transition("product", fourth["id"], "building")["status"] == "building"


def test_awaiting_owner_from_a_non_counting_state_does_not_count(store):
    _product(store, "building")
    _product(store, "building")
    _product(store, "awaiting_owner")  # waiting from qualified
    third = _product(store)
    assert store.transition("product", third["id"], "building")["status"] == "building"


# --- pay-before-spend test (R18, R21, AE5) ----------------------------------


def test_over_limit_launch_cannot_go_straight_to_building(store):
    rec = _product(store, estimated_upfront_spend_usd=280)
    with pytest.raises(TransitionError, match="testing"):
        store.transition("product", rec["id"], "building")
    got = store.transition("product", rec["id"], "testing")
    assert got["test_started_at"] == f.ts(f.T0)


def test_launch_limit_read_from_workspace_config(store, ws):
    (ws / ".solstice").mkdir(exist_ok=True)
    (ws / ".solstice" / "config.yaml").write_text("budgets:\n  launch_spend_limit_usd: 300\n")
    rec = _product(store, estimated_upfront_spend_usd=280)
    assert store.transition("product", rec["id"], "building")["status"] == "building"


def test_three_pre_orders_within_14_days_unlock_building(store, clock):
    rec = _product(store, "testing", estimated_upfront_spend_usd=280)
    for day in (1, 4, 9):
        store.add_event("product", rec["id"], f.buy_signal("pre_order", at=f.T0.replace(day=5 + day)))
    clock.advance(days=10)
    assert store.transition("product", rec["id"], "building")["status"] == "building"


def test_two_pre_orders_park_only_after_day_14(store, clock):
    rec = _product(store, "testing", estimated_upfront_spend_usd=280)
    for day in (1, 2):
        store.add_event("product", rec["id"], f.buy_signal("pre_order", at=f.T0.replace(day=5 + day)))
    for _ in range(40):
        store.add_event("product", rec["id"], f.buy_signal("waitlist_signup"))
    clock.advance(days=10)
    with pytest.raises(TransitionError, match="pre-order"):
        store.transition("product", rec["id"], "building")
    with pytest.raises(TransitionError, match="day 14"):
        store.transition("product", rec["id"], "parked")
    clock.advance(days=5)
    # a third pre-order after the 14-day window does not unlock spend
    store.add_event("product", rec["id"], f.buy_signal("pre_order"))
    with pytest.raises(TransitionError):
        store.transition("product", rec["id"], "building")
    assert store.transition("product", rec["id"], "parked")["status"] == "parked"


def test_parked_can_be_revived_into_a_fresh_test(store, clock):
    rec = _product(store, "testing", estimated_upfront_spend_usd=280)
    clock.advance(days=15)
    store.transition("product", rec["id"], "parked")
    clock.advance(days=30)
    got = store.transition("product", rec["id"], "testing")
    assert got["test_started_at"] == f.ts(clock())


# --- owner_prereq over the launch limit (R18) -------------------------------


def test_costly_owner_prereq_cannot_close_until_buy_signal(store):
    prod = _product(store)
    appr = store.create("approval", f.approval(product_id=prod["id"], cost_usd=280))
    with pytest.raises(TransitionError, match="buy signal"):
        store.transition("approval", appr["id"], "closed")
    store.add_event("product", prod["id"], f.buy_signal("waitlist_signup"))
    with pytest.raises(TransitionError, match="buy signal"):
        store.transition("approval", appr["id"], "closed")
    store.add_event("product", prod["id"], f.buy_signal("pre_order"))
    assert store.transition("approval", appr["id"], "closed")["status"] == "closed"


def test_cheap_owner_prereq_closes_without_buy_signal(store):
    prod = _product(store)
    appr = store.create("approval", f.approval(product_id=prod["id"], cost_usd=50))
    assert store.transition("approval", appr["id"], "closed")["status"] == "closed"


def test_approval_cannot_be_approved_through_record_transition(store):
    appr = store.create("approval", f.approval(subtype="outbound"))
    with pytest.raises(TransitionError):
        store.transition("approval", appr["id"], "approved")


# --- problems ----------------------------------------------------------------


def _pending_problem(store):
    body = f.problem(status="pending_evidence", pending_fetch={
        "adapter": "example_adapter", "error": "timeout", "attempted_at": "2026-01-05T10:00:00Z"})
    del body["demand"]
    return store.create("problem", body)


def test_problem_drops_only_after_three_failed_refetches(store):
    rec = _pending_problem(store)
    for n in (1, 2):
        got = store.record_refetch_failure(rec["id"], "timeout again")
        assert got["refetch_failures"] == n and got["status"] == "pending_evidence"
        with pytest.raises(TransitionError, match="3"):
            store.transition("problem", rec["id"], "dropped")
    store.record_refetch_failure(rec["id"], "timeout again")
    assert store.transition("problem", rec["id"], "dropped")["status"] == "dropped"


def test_pending_problem_returns_to_found_only_with_demand(store):
    rec = _pending_problem(store)
    with pytest.raises(Exception):
        store.transition("problem", rec["id"], "found")
    got = store.transition("problem", rec["id"], "found", {"demand": [f.demand(value=0)]})
    assert got["status"] == "found" and got["refetch_failures"] == 0


def test_problem_illegal_transition(store):
    rec = store.create("problem", f.problem())
    with pytest.raises(TransitionError):
        store.transition("problem", rec["id"], "dropped")
    assert store.transition("problem", rec["id"], "rejected")["status"] == "rejected"


# --- refusals carry structured details (agent contract) ---------------------


def test_refusals_carry_from_to_allowed_and_rule(store):
    rec = _product(store, "building")
    with pytest.raises(TransitionError) as exc:
        store.transition("product", rec["id"], "live")
    assert exc.value.kind == "transition_refused"
    assert exc.value.details == {"from": "building", "to": "live", "allowed": ["built"]}

    rec = _product(store, "building", "built")
    with pytest.raises(TransitionError) as exc:
        store.transition("product", rec["id"], "live")
    assert exc.value.details["rule"] == "channel_live_at_required"
    assert exc.value.details["allowed"] == ["in_review", "live"]


def test_problem_drop_refusal_names_refetch_rule(store):
    rec = _pending_problem(store)
    with pytest.raises(TransitionError) as exc:
        store.transition("problem", rec["id"], "dropped")
    d = exc.value.details
    assert d["rule"] == "refetch_failures" and (d["needed"], d["have"]) == (3, 0)
    assert d["allowed"] == ["dropped", "found"]
