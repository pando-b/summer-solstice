"""Status transitions for problems, products, and approvals (KTD6, R18, R21).

Pure functions: `apply` takes the record (with any caller-supplied fields
already merged), the target status, and a Context, and returns the new record
or raises TransitionError. The Store supplies the context and does the I/O.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta

from solstice.errors import SolsticeError

LIVE_CAP = 3
TEST_WINDOW = timedelta(days=14)
PRE_ORDERS_TO_UNLOCK = 3

# Paid pre-sale signals (R21). paid_conversion is a buy signal (R18) but not a pre-order.
PRE_ORDER_KINDS = {"pre_order", "founding_member"}
BUY_SIGNAL_KINDS = PRE_ORDER_KINDS | {"paid_conversion"}

PROBLEM_TRANSITIONS = {
    "found": {"pending_evidence", "rejected"},
    "pending_evidence": {"found", "dropped"},
    "rejected": set(),
    "dropped": set(),
}

PRODUCT_TRANSITIONS = {
    "qualified": {"building", "testing"},
    "testing": {"building", "parked"},
    "parked": {"testing"},
    "building": {"built"},
    "built": {"in_review", "live"},
    "in_review": {"building", "live"},
    "live": {"growing", "killing"},
    "growing": {"selling"},
    "killing": {"sunset"},
    "selling": set(),
    "sunset": set(),
}
PRODUCT_TERMINAL = {s for s, nxt in PRODUCT_TRANSITIONS.items() if not nxt}

# Statuses that count toward the live cap (KTD6). awaiting_owner counts when
# the product was in one of these before it started waiting.
CAP_STATUSES = {"building", "built", "in_review", "live", "killing"}

# Approvals: approve/reject belong to the interactive approvals flow (U9).
# Through `record transition` an owner_prereq can only be closed.
APPROVAL_TRANSITIONS = {"pending": {"closed"}, "approved": {"closed"}}

INITIAL = {
    "problem": {"found", "pending_evidence"},
    "product": {"qualified"},
    "approval": {"pending"},
}


class TransitionError(SolsticeError):
    """The requested status change is not allowed.

    `details` carries `from`, `to`, and `allowed` (the statuses the lifecycle
    table allows from the current one). When the table allows the move but a
    guard refuses it, `details.rule` names the guard."""

    kind = "transition_refused"


def _refuse(message: str, cur: str, to: str, allowed, rule: str | None = None,
            **extra) -> TransitionError:
    details = {"from": cur, "to": to, "allowed": sorted(allowed)}
    if rule:
        details["rule"] = rule
    details.update(extra)
    return TransitionError(message, details=details)


@dataclass
class Context:
    now: datetime
    events: list[dict] = field(default_factory=list)  # this record's history
    others: list[dict] = field(default_factory=list)  # other products (cap check)
    product_events: list[dict] = field(default_factory=list)  # for approvals
    launch_limit: float = 50.0


def counts_toward_cap(product: dict) -> bool:
    status = product["status"]
    if status == "awaiting_owner":
        status = product.get("awaiting_owner_from")
    return status in CAP_STATUSES


def apply(entity: str, rec: dict, to: str, ctx: Context) -> dict:
    if entity == "product":
        return _product(rec, to, ctx)
    if entity == "problem":
        return _problem(rec, to)
    if entity == "approval":
        return _approval(rec, to, ctx)
    raise TransitionError(f"{entity} records have no status lifecycle",
                          details={"from": rec.get("status"), "to": to, "allowed": []})


def _not_allowed(entity: str, cur: str, to: str, allowed) -> TransitionError:
    opts = ", ".join(sorted(allowed)) or "none (terminal)"
    return _refuse(f"{entity} {cur} -> {to} is not allowed; allowed from {cur}: {opts}",
                   cur, to, allowed)


def _product(rec: dict, to: str, ctx: Context) -> dict:
    cur = rec["status"]
    new = dict(rec, status=to)

    if cur == "awaiting_owner":
        prior = rec.get("awaiting_owner_from")
        if to != prior:
            raise _refuse(f"product awaiting_owner returns only to {prior}, not {to}",
                          cur, to, [prior] if prior else [], rule="awaiting_owner_return")
        new.pop("awaiting_owner_from", None)
        return new
    if to == "awaiting_owner":
        if cur in PRODUCT_TERMINAL:
            raise _not_allowed("product", cur, to, ())
        new["awaiting_owner_from"] = cur
        return new

    allowed = PRODUCT_TRANSITIONS.get(cur, set())
    if to not in allowed:
        raise _not_allowed("product", cur, to, allowed)

    if to == "live" and not new.get("channel_live_at"):
        raise _refuse(f"product {cur} -> live needs channel_live_at (the kill window starts there)",
                      cur, to, allowed, rule="channel_live_at_required")

    if cur == "qualified" and to == "building":
        spend = rec.get("estimated_upfront_spend_usd", 0)
        if spend > ctx.launch_limit:
            raise _refuse(
                f"estimated upfront spend ${spend:g} is over the ${ctx.launch_limit:g} launch limit (R18); "
                f"move to testing for a pay-before-spend test instead",
                cur, to, allowed, rule="launch_spend_limit", requirement="R18",
                spend_usd=spend, limit_usd=ctx.launch_limit)

    if cur == "testing":
        start = parse_ts(rec["test_started_at"])
        pre_orders = _pre_orders_in_window(ctx.events, start)
        if to == "building" and pre_orders < PRE_ORDERS_TO_UNLOCK:
            raise _refuse(
                f"testing -> building needs {PRE_ORDERS_TO_UNLOCK} paid pre-order buy signals within "
                f"14 days of the test start; have {pre_orders} (R21)",
                cur, to, allowed, rule="pre_orders_to_unlock", requirement="R21",
                needed=PRE_ORDERS_TO_UNLOCK, have=pre_orders)
        if to == "parked":
            if pre_orders >= PRE_ORDERS_TO_UNLOCK:
                raise _refuse(f"test has {pre_orders} paid pre-orders; move to building, not parked",
                              cur, to, allowed, rule="pre_orders_reached", requirement="R21",
                              needed=PRE_ORDERS_TO_UNLOCK, have=pre_orders)
            if ctx.now < start + TEST_WINDOW:
                raise _refuse(
                    f"test runs until day 14 ({fmt_ts(start + TEST_WINDOW)}); it can be parked only after that",
                    cur, to, allowed, rule="test_window", requirement="R21",
                    window_ends_at=fmt_ts(start + TEST_WINDOW))

    if to == "testing":
        new["test_started_at"] = fmt_ts(ctx.now)

    if not counts_toward_cap(rec) and to in CAP_STATUSES:
        in_flight = [p for p in ctx.others if counts_toward_cap(p)]
        if len(in_flight) >= LIVE_CAP:
            raise _refuse(
                f"live cap reached: {len(in_flight)} products already in flight "
                f"({', '.join(sorted(p.get('slug', p['id']) for p in in_flight))}); "
                f"the cap is {LIVE_CAP} (KTD6)",
                cur, to, allowed, rule="live_cap", cap=LIVE_CAP,
                in_flight=sorted(p["id"] for p in in_flight))
    return new


def _problem(rec: dict, to: str) -> dict:
    cur = rec["status"]
    allowed = PROBLEM_TRANSITIONS.get(cur, set())
    if to not in allowed:
        raise _not_allowed("problem", cur, to, allowed)
    new = dict(rec, status=to)
    failures = rec.get("refetch_failures", 0)
    if to == "dropped" and failures < 3:
        raise _refuse(f"pending_evidence -> dropped needs 3 failed refetch runs; have {failures}",
                      cur, to, allowed, rule="refetch_failures", needed=3, have=failures)
    if cur == "pending_evidence" and to == "found":
        new["refetch_failures"] = 0
    return new


def _approval(rec: dict, to: str, ctx: Context) -> dict:
    cur = rec["status"]
    allowed = APPROVAL_TRANSITIONS.get(cur, set()) if rec["subtype"] == "owner_prereq" else set()
    if to not in allowed:
        raise _refuse(
            f"approval ({rec['subtype']}) {cur} -> {to} is not allowed here; approving and rejecting "
            f"go through the approvals flow, and only owner_prereq items close through `record transition`",
            cur, to, allowed)
    cost = rec.get("cost_usd", 0)
    if cost > ctx.launch_limit and not any(
        e.get("type") == "buy_signal" and e.get("kind") in BUY_SIGNAL_KINDS for e in ctx.product_events
    ):
        raise _refuse(
            f"owner_prereq costs ${cost:g}, over the ${ctx.launch_limit:g} launch limit; it cannot close "
            f"until the product records a buy signal (R18)",
            cur, to, allowed, rule="buy_signal_before_spend", requirement="R18",
            cost_usd=cost, limit_usd=ctx.launch_limit)
    return dict(rec, status=to)


def _pre_orders_in_window(events: list[dict], start: datetime) -> int:
    end = start + TEST_WINDOW
    return sum(
        1 for e in events
        if e.get("type") == "buy_signal" and e.get("kind") in PRE_ORDER_KINDS
        and start <= parse_ts(e["at"]) <= end
    )


def parse_ts(value: str) -> datetime:
    return datetime.fromisoformat(value).astimezone(UTC)


def fmt_ts(dt: datetime) -> str:
    return dt.astimezone(UTC).isoformat().replace("+00:00", "Z")
