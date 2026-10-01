"""Approval records and the owner queue (R13, R18, KTD7, KTD8).

Subtypes:

- `outbound` (content to publish) and `irreversible` (pricing change,
  sunset with paying customers, marketplace submission) are decided by the
  owner: `approve` or `reject`.
- `owner_prereq` (accounts, keys, licensed files, artwork, name choice) is
  work, not content: it is `close`d through the lifecycle, which keeps the
  R18 buy-signal guard.

`approve` stores the approver, the time, and a SHA-256 over the RFC 8785
canonical JSON of the payload, channel, executor, product ID, and the hash of
every attachment file. It runs only in an interactive terminal, outside a
scheduled run, and only after the owner types the displayed hash prefix.
Those checks stop an agent approving by accident; they are not an
owner-presence factor (KTD8).

Aging is derived on every read (`list`, `show`), never stored: a nudge at 7
days, and at 14 days an open `owner_prereq` moves its product to
`awaiting_owner` with reason "parked". A prereq over the launch limit waits on
buyers, so its clock starts at the product's first buy signal; products in
`testing` or `parked` are never moved (the R21 window governs them).
"""

from __future__ import annotations

import getpass
import hashlib
import json
import os
import sys
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

from solstice import canonical
from solstice.errors import SolsticeError
from solstice.lifecycle import BUY_SIGNAL_KINDS, PRODUCT_TERMINAL
from solstice.state import (
    _APPROVAL_FLOW_FIELDS,
    RecordError,
    Store,
    fmt_ts,
    launch_spend_limit,
    parse_ts,
)

SCHEDULED_RUN_ENV = "SOLSTICE_SCHEDULED_RUN"
PREFIX_LEN = 8
NUDGE_AFTER = timedelta(days=7)
PARK_AFTER = timedelta(days=14)
DECIDED_SUBTYPES = ("outbound", "irreversible")
# Products the aging park never moves: the R21 test window governs these.
PARK_EXEMPT = {"testing", "parked"}
PARK_REASON = "parked"


class ApprovalError(SolsticeError):
    """The approvals flow refused the action (`kind: approval`)."""

    kind = "approval"


def _ask_terminal(text: str) -> str:
    print(text, end="", file=sys.stderr, flush=True)
    return sys.stdin.readline()


@dataclass
class Deps:
    """The owner's terminal, injected (like doctor's Probes)."""

    # Read for the scheduled-run marker only; never for keys (KTD17).
    env: Mapping[str, str] = field(default_factory=lambda: os.environ)
    isatty: Callable[[], bool] = lambda: sys.stdin.isatty()
    ask: Callable[[str], str] = _ask_terminal
    user: Callable[[], str] = getpass.getuser


# --- hashing -----------------------------------------------------------------


def file_sha256(path: Path) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 16), b""):
            h.update(chunk)
    return h.hexdigest()


def _attachment_file(workspace: Path, rel: str) -> tuple[str, Path]:
    """(normalized workspace-relative path, absolute path) for an attachment."""
    if not isinstance(rel, str) or not rel.strip():
        raise ApprovalError("each attachment must be a non-empty path string")
    root = workspace.resolve()
    full = (root / rel).resolve()
    if Path(rel).is_absolute() or not full.is_relative_to(root):
        raise ApprovalError(f"attachment {rel} must be a path inside the workspace",
                            details={"path": rel})
    if not full.is_file():
        raise ApprovalError(f"attachment {rel} is not a file in the workspace",
                            details={"path": rel})
    return full.relative_to(root).as_posix(), full


def _current_attachments(store: Store, rec: dict) -> list[dict]:
    out = []
    for a in rec.get("attachments") or []:
        rel, full = _attachment_file(store.workspace, a["path"])
        out.append({"path": rel, "sha256": file_sha256(full)})
    return out


def hash_material(rec: dict, attachments: list[dict]) -> dict:
    return {
        "payload": rec.get("payload"),
        "channel": rec.get("channel"),
        "executor": rec.get("executor"),
        "product_id": rec.get("product_id"),
        "attachments": [{"path": a["path"], "sha256": a["sha256"]} for a in attachments],
    }


def content_hash(store: Store, rec: dict) -> str:
    """SHA-256 of the item's canonical content, with attachments hashed from disk now."""
    return canonical.canonical_hash(hash_material(rec, _current_attachments(store, rec)))


# --- request -----------------------------------------------------------------


def request(store: Store, body: dict) -> dict:
    """Queue an approval item. Skills and scheduled runs may call this."""
    if not isinstance(body, dict):
        raise RecordError("approval body must be a JSON object")
    flow = [k for k in _APPROVAL_FLOW_FIELDS if k != "attachments" and body.get(k) is not None]
    if flow:
        raise RecordError(f"cannot set {', '.join(flow)}: set by the approvals flow at approve/reject")
    paths = body.get("attachments") or []
    if not isinstance(paths, list):
        raise RecordError("attachments must be a list of workspace-relative paths")
    attachments = []
    for p in paths:
        rel, full = _attachment_file(store.workspace, p)
        attachments.append({"path": rel, "sha256": file_sha256(full)})
    body = {**body, "status": body.get("status", "pending")}
    body.pop("attachments", None)
    if attachments:
        body["attachments"] = attachments
    if "payload" in body:
        canonical.canonical_bytes(body["payload"])  # refuse an unhashable payload now, not at approve
    return store.create_managed("approval", body)


# --- approve / reject / close ------------------------------------------------


def _owner_terminal(deps: Deps, action: str) -> None:
    if deps.env.get(SCHEDULED_RUN_ENV):
        raise ApprovalError(
            f"{action} refused: {SCHEDULED_RUN_ENV} is set, and scheduled runs can only list, "
            f"show, and request approvals",
            details={"action": action, "reason": "scheduled_run"})
    if not deps.isatty():
        raise ApprovalError(
            f"{action} refused: stdin is not an interactive terminal; the owner runs "
            f"`solstice approvals {action}` in their own terminal",
            details={"action": action, "reason": "not_a_terminal"})


def _decidable(rec: dict, action: str) -> None:
    if rec["subtype"] not in DECIDED_SUBTYPES:
        raise ApprovalError(
            f"{rec['subtype']} items are work, not content: they close with "
            f"`solstice approvals close`, not {action}",
            details={"id": rec["id"], "subtype": rec["subtype"]})
    if rec["status"] != "pending":
        raise ApprovalError(f"approval {rec['id']} is {rec['status']}; only pending items can be "
                            f"approved or rejected",
                            details={"id": rec["id"], "status": rec["status"]})


def _changed_attachments(store: Store, rec: dict) -> list[str]:
    changed = []
    for a in rec.get("attachments") or []:
        full = (store.workspace.resolve() / a["path"]).resolve()
        if not full.is_file() or file_sha256(full) != a["sha256"]:
            changed.append(a["path"])
    return changed


def _display(rec: dict, digest: str) -> str:
    lines = [
        f"Approval {rec['id']} ({rec['subtype']}): {rec['title']}",
        f"  product:  {rec.get('product_id') or '-'}",
        f"  channel:  {rec.get('channel') or '-'}",
        f"  executor: {rec.get('executor') or '-'}",
        "  payload:",
        *("    " + ln for ln in json.dumps(rec.get("payload"), indent=2, sort_keys=True,
                                         ensure_ascii=False).splitlines()),
    ]
    for a in rec.get("attachments") or []:
        lines.append(f"  attachment: {a['path']}  sha256 {a['sha256']}")
    lines += [f"  content hash: {digest}",
              f"Type the first {PREFIX_LEN} characters of the content hash to approve: "]
    return "\n".join(lines)


def approve(store: Store, rid: str, deps: Deps) -> dict:
    _owner_terminal(deps, "approve")
    rec = store.get("approval", rid)
    _decidable(rec, "approve")
    changed = _changed_attachments(store, rec)
    if changed:
        raise ApprovalError(
            f"approve refused: attachment(s) changed since the request: {', '.join(changed)}; "
            f"request a new approval for the new files",
            details={"id": rid, "changed": changed})
    digest = content_hash(store, rec)
    typed = (deps.ask(_display(rec, digest)) or "").strip().lower()
    if typed != digest[:PREFIX_LEN]:
        raise ApprovalError("approve refused: the typed prefix does not match the content hash; "
                            "the approval is unchanged", details={"id": rid})
    with store.lock():
        cur = store.get("approval", rid)
        if cur["status"] != "pending" or content_hash(store, cur) != digest:
            raise ApprovalError("approve refused: the item changed while it was being reviewed; "
                                "run approve again to review the current content",
                                details={"id": rid})
        now = fmt_ts(store.now())
        new = {**cur, "status": "approved", "approver": deps.user(), "approved_at": now,
               "content_hash": digest}
        return store.put_locked("approval", new, {
            "at": now, "type": "transition", "from": "pending", "to": "approved",
            "approver": new["approver"], "content_hash": digest})


def reject(store: Store, rid: str, reason: str, deps: Deps) -> dict:
    _owner_terminal(deps, "reject")
    if not isinstance(reason, str) or not reason.strip():
        raise ApprovalError("reject needs a reason", details={"id": rid})
    with store.lock():
        rec = store.get("approval", rid)
        _decidable(rec, "reject")
        now = fmt_ts(store.now())
        new = {**rec, "status": "rejected", "rejected_at": now, "rejection_reason": reason.strip()}
        return store.put_locked("approval", new, {
            "at": now, "type": "transition", "from": "pending", "to": "rejected",
            "reason": reason.strip()})


def close(store: Store, rid: str, reason: str | None = None) -> dict:
    """Close an owner_prereq through the lifecycle (R18 buy-signal guard)."""
    return store.transition("approval", rid, "closed", {"reason": reason} if reason else None)


# --- aging and the queue -----------------------------------------------------


def _first_buy_signal(events: list[dict]) -> datetime | None:
    times = [parse_ts(e["at"]) for e in events
             if e.get("type") == "buy_signal" and e.get("kind") in BUY_SIGNAL_KINDS]
    return min(times) if times else None


def _aging(rec: dict, product: dict | None, product_events: list[dict], now: datetime,
           limit: float) -> dict | None:
    """Derived aging for a pending item, or None once decided or closed."""
    if rec["status"] != "pending":
        return None
    prereq = rec["subtype"] == "owner_prereq"
    start, clock = parse_ts(rec["created_at"]), "requested"
    if prereq and rec.get("cost_usd", 0) > limit:
        signal = _first_buy_signal(product_events)
        if signal is None:
            return {"clock": "waiting_on_buy_signal", "started_at": None, "age_days": None,
                    "nudge": False, "nudge_at": None, "park_at": None, "parks": False}
        start, clock = max(start, signal), "first_buy_signal"
    age = now - start
    parks = (prereq and age >= PARK_AFTER and product is not None
             and product["status"] not in PARK_EXEMPT | PRODUCT_TERMINAL | {"awaiting_owner"})
    return {"clock": clock, "started_at": fmt_ts(start), "age_days": age.days,
            "nudge": age >= NUDGE_AFTER, "nudge_at": fmt_ts(start + NUDGE_AFTER),
            "park_at": fmt_ts(start + PARK_AFTER) if prereq else None, "parks": parks}


def _product(store: Store, pid: str | None) -> tuple[dict | None, list[dict]]:
    if not pid:
        return None, []
    try:
        return store.get("product", pid), store.events("product", pid)
    except RecordError as exc:
        if exc.kind == "not_found":
            return None, []
        raise


def _aging_of(store: Store, rec: dict, limit: float) -> dict | None:
    product, events = _product(store, rec.get("product_id"))
    return _aging(rec, product, events, store.now(), limit)


def _park_due(store: Store, limit: float, only: str | None = None) -> None:
    """Move products of 14-day-old open owner_prereqs to awaiting_owner.

    Checked again under the workspace lock, so concurrent readers move a
    product once and a second read makes no change."""
    pending = [r for r in store.list("approval", status="pending")
               if r["subtype"] == "owner_prereq" and (only is None or r["id"] == only)]
    due = [r["id"] for r in pending if (_aging_of(store, r, limit) or {}).get("parks")]
    if not due:
        return
    with store.lock():
        for aid in due:
            rec = store.get("approval", aid)
            if not (_aging_of(store, rec, limit) or {}).get("parks"):
                continue
            store.transition_locked("product", rec["product_id"], "awaiting_owner",
                                    reason=PARK_REASON, event={"approval_id": aid})


def _item(store: Store, rec: dict, limit: float) -> dict:
    aging = _aging_of(store, rec, limit)
    if aging is not None:
        aging = {k: v for k, v in aging.items() if k != "parks"}
    return {**rec, "aging": aging}


def _order(item: dict) -> tuple:
    a = item["aging"] or {}
    return (item["status"] != "pending", not a.get("nudge"), a.get("started_at") or "~",
            item["created_at"])


def list_queue(store: Store, status: str = "pending") -> list[dict]:
    """The owner queue: nudged items first, then oldest first. `status` may be `all`."""
    limit = launch_spend_limit(store.workspace)
    _park_due(store, limit)
    recs = store.list("approval", status=None if status == "all" else status)
    return sorted((_item(store, r, limit) for r in recs), key=_order)


def show(store: Store, rid: str) -> dict:
    limit = launch_spend_limit(store.workspace)
    store.get("approval", rid)
    _park_due(store, limit, only=rid)
    return _item(store, store.get("approval", rid), limit)
