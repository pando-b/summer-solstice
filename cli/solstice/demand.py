"""`solstice demand` and `solstice run`: fetch orchestration, the run spend
ledger, and the factory budget (R3, R5, R16, R22, R26; KTD4, KTD17).

One `demand fetch` call:

1. checks the adapter's params, then its availability: an installed engine,
   then its keys (through `credentials`, environment only). A missing key
   makes it `unavailable` before any network call.
2. under the workspace lock, sums this calendar month's run spend (UTC,
   `running` runs included) and reserves the call's estimated cost on the
   run. A reservation that would cross the per-run cap or the monthly
   factory cap is refused with `kind: budget`, and the adapter is marked
   `unavailable: budget` on the run; no record is touched.
3. outside the lock, waits for the adapter's rate slot (a slot file under
   `.solstice/rate/`, shared across processes) and calls the source,
   retrying HTTP 429 (or a source's rate-limit code) a bounded number of
   times.
4. under the lock again, books the actual cost against the reservation,
   writes the adapter status, and writes evidence and the problem.

A failed fetch is never a zero (R5). A problem with no demand becomes, or
stays, `pending_evidence` with `pending_fetch`; a problem that already holds
a demand entry stays as it is and the failure is logged on the run.
"""

from __future__ import annotations

import fcntl
import os
import subprocess
import time
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path

from solstice import credentials
from solstice.adapters import REGISTRY, base
from solstice.adapters.base import (
    BUDGET, OUT_OF_CREDITS, Adapter, Ctx, FetchFailed, Params, RateLimited, Result, Runner,
    TransportError, Unavailable)
from solstice.errors import SolsticeError, UsageError
from solstice.state import RecordError, Store, fmt_ts, new_ulid, now_utc, parse_ts
from solstice.workspace import adapter_cfg, budget, load_config

__all__ = ["Deps", "Pacer", "fetch", "sources", "start_run", "finish_run", "reserve",
           "month_spend", "MAX_RETRIES"]

MAX_RETRIES = 3
BACKOFF_BASE_S = 2.0
BACKOFF_MAX_S = 60.0
DEFAULT_MONTHLY_CAP_USD = 50.0
DEFAULT_PER_RUN_CAP_USD = 5.0
# Unavailable reasons that mean the run did not get everything it asked for.
SHORTFALL_REASONS = {BUDGET, OUT_OF_CREDITS}
_EPS = 1e-9


class AdapterError(SolsticeError):
    kind = "adapter"


class BudgetError(SolsticeError):
    kind = "budget"


def _unavailable_error(adapter: str, reason: str, run_id: str,
                       message: str | None = None) -> AdapterError:
    return AdapterError(message or f"{adapter} unavailable: {reason}",
                        details={"adapter": adapter, "status": "unavailable",
                                 "reason": reason, "run_id": run_id})


def monthly_cap_crossed(spent: float, estimate: float, monthly: float) -> bool:
    """True when the month is already at the cap or `estimate` would cross it."""
    return spent >= monthly - _EPS or spent + estimate > monthly + _EPS


def _run_process(argv: list[str], timeout: float) -> tuple[int, str, str]:
    try:
        p = subprocess.run(argv, capture_output=True, text=True, timeout=timeout, check=False)
    except FileNotFoundError:
        return 127, "", f"{argv[0]}: command not found"
    except OSError as exc:  # e.g. not executable
        return 126, "", f"{argv[0]}: cannot run: {exc.strerror or exc}"
    except subprocess.TimeoutExpired:
        return 124, "", f"timed out after {timeout:g}s"
    return p.returncode, p.stdout, p.stderr


@dataclass
class Deps:
    """The outside world, injected (like doctor's Probes)."""

    transport: base.Transport = field(default_factory=lambda: base.http_transport)
    runner: Runner = _run_process
    env: Mapping[str, str] | None = None  # None: the process environment, via credentials
    now: Callable[[], datetime] = now_utc
    clock: Callable[[], float] = time.time  # for rate slots
    sleep: Callable[[float], None] = time.sleep
    home: Path | None = field(default_factory=Path.home)


# --- config -------------------------------------------------------------------


def caps(cfg: dict) -> tuple[float, float]:
    return (budget(cfg, "factory_monthly_cap_usd", DEFAULT_MONTHLY_CAP_USD),
            budget(cfg, "per_run_cap_usd", DEFAULT_PER_RUN_CAP_USD))


def month_spend(store: Store, at: datetime) -> float:
    total = 0.0
    for run in store.list("run"):
        started = parse_ts(run["started_at"])
        if (started.year, started.month) == (at.year, at.month):
            total += float(run.get("spend_usd") or 0)
    return total


# --- rate slots -------------------------------------------------------------------


class Pacer:
    """Spaces calls to one adapter at least `interval` seconds apart across
    concurrent CLI processes. Each caller takes the next free slot under an
    advisory lock on `.solstice/rate/<adapter>.slot`, then sleeps until it."""

    MAX_QUEUE = 100  # a slot further out than this many intervals is stale

    def __init__(self, workspace: Path, *, clock: Callable[[], float],
                 sleep: Callable[[float], None]):
        self.dir = Path(workspace) / ".solstice" / "rate"
        self.clock, self.sleep = clock, sleep

    def wait(self, name: str, interval: float) -> None:
        if interval <= 0:
            return
        self.dir.mkdir(parents=True, exist_ok=True)
        fd = os.open(self.dir / f"{name}.slot", os.O_RDWR | os.O_CREAT, 0o644)
        try:
            fcntl.flock(fd, fcntl.LOCK_EX)
            try:
                next_at = float(os.read(fd, 64).decode().strip() or 0)
            except ValueError:
                next_at = 0.0
            now = self.clock()
            slot = max(now, min(next_at, now + interval * self.MAX_QUEUE))
            os.lseek(fd, 0, os.SEEK_SET)
            os.ftruncate(fd, 0)
            os.write(fd, repr(slot + interval).encode())
        finally:
            os.close(fd)
        if slot > now:
            self.sleep(slot - now)


# --- runs ---------------------------------------------------------------------------


def _fresh_status() -> dict:
    return {"calls": 0, "ok": 0, "failures": 0, "spend_usd": 0}


def start_run(store: Store, stage: str) -> dict:
    if not stage.strip():
        raise UsageError("run start needs a non-empty --stage")
    return store.create_managed("run", {
        "stage": stage, "status": "running", "started_at": fmt_ts(store.now()),
        "spend_usd": 0, "adapter_status": {}})


def _running(store: Store, run_id: str) -> dict:
    run = store.get("run", run_id)
    if run["status"] != "running":
        raise RecordError(f"run {run_id} is {run['status']}; start a new one with "
                          f"`solstice run start`", details={"run_id": run_id,
                                                            "status": run["status"]})
    return run


def finish_run(store: Store, run_id: str) -> dict:
    with store.lock():
        run = _running(store, run_id)
        statuses = list((run.get("adapter_status") or {}).values())
        short = any(s.get("failures", 0) > 0 or (s["status"] == "unavailable"
                                                 and s.get("reason") in SHORTFALL_REASONS)
                    for s in statuses)
        got = any(s.get("ok", 0) > 0 for s in statuses)
        status = "complete" if not short else ("partial" if got else "failed")
        run = {**run, "status": status, "finished_at": fmt_ts(store.now())}
        return store.put_locked("run", run, {"type": "run_finished", "status": status})


def _set_status(store: Store, run: dict, adapter: str, event: dict, **fields) -> dict:
    """Write one adapter's status on a run the caller holds the lock for."""
    statuses = dict(run.get("adapter_status") or {})
    st = {**_fresh_status(), **statuses.get(adapter, {}), **fields}
    for k in ("error", "reason"):
        if st.get(k) is None:
            st.pop(k, None)
    statuses[adapter] = st
    return store.put_locked("run", {**run, "adapter_status": statuses}, event)


def _mark_unavailable(store: Store, run_id: str, adapter: str, reason: str) -> None:
    with store.lock():
        run = _running(store, run_id)
        _set_status(store, run, adapter, {"type": "adapter_unavailable", "adapter": adapter,
                                          "reason": reason},
                    status="unavailable", reason=reason, error=None)


def reserve(store: Store, run_id: str, adapter: Adapter, estimate_usd: float, cfg: dict) -> None:
    """Reserve a call's estimated cost on the run, or refuse with `budget`."""
    with store.lock():
        run = _running(store, run_id)
        st = {**_fresh_status(), **(run.get("adapter_status") or {}).get(adapter.name, {})}
        if st.get("status") == "unavailable" and st.get("reason") == OUT_OF_CREDITS:
            raise _unavailable_error(adapter.name, OUT_OF_CREDITS, run_id,
                                     f"{adapter.name} is out of credits for the rest of run {run_id}")
        spend = float(run.get("spend_usd") or 0)
        if adapter.paid:
            monthly, per_run = caps(cfg)
            month = month_spend(store, store.now())
            why = None
            if spend + estimate_usd > per_run + _EPS:
                why = (f"per-run cap ${per_run:g} would be crossed: run has ${spend:.4f}, "
                       f"{adapter.name} needs ${estimate_usd:.4f}")
            elif monthly_cap_crossed(month, estimate_usd, monthly):
                why = (f"monthly factory cap ${monthly:g} would be crossed: ${month:.4f} spent "
                       f"this month, {adapter.name} needs ${estimate_usd:.4f}")
            if why:
                _set_status(store, run, adapter.name, {"type": "adapter_unavailable",
                                                       "adapter": adapter.name, "reason": why},
                            status="unavailable", reason=BUDGET, error=None)
                raise BudgetError(why, details={
                    "adapter": adapter.name, "run_id": run_id, "estimate_usd": estimate_usd,
                    "run_spend_usd": round(spend, 6), "per_run_cap_usd": per_run,
                    "month_spend_usd": round(month, 6), "monthly_cap_usd": monthly})
        run = {**run, "spend_usd": spend + estimate_usd}
        _set_status(store, run, adapter.name,
                    {"type": "spend_reserved", "adapter": adapter.name, "usd": estimate_usd},
                    status=st.get("status", "skipped"),  # settled after the call
                    calls=st["calls"] + 1, spend_usd=st["spend_usd"] + estimate_usd)


# --- fetch --------------------------------------------------------------------------


def fetch(store: Store, adapter_name: str, params: Params, *, deps: Deps,
          run_id: str | None = None, new_problem: str | None = None,
          problem_id: str | None = None) -> dict:
    adapter = REGISTRY.get(adapter_name)
    if adapter is None:
        raise UsageError(f"unknown adapter {adapter_name!r}; one of {', '.join(REGISTRY)}")
    adapter.check(params)
    if new_problem is not None and problem_id:
        raise UsageError("pass --new-problem or --problem, not both")
    if new_problem is not None and not new_problem.strip():
        raise UsageError("--new-problem needs a non-empty --title")
    if adapter.evidence_only and new_problem is not None:
        raise UsageError(f"{adapter.name} yields evidence, not a demand number, so it cannot "
                         f"create a problem; use --problem <id>")
    if problem_id:
        store.get("problem", problem_id)
    if run_id:
        _running(store, run_id)

    implicit = run_id is None
    if implicit:
        run_id = start_run(store, "find")["id"]
    try:
        return _fetch_in_run(store, adapter, params, deps, run_id, new_problem, problem_id)
    finally:
        if implicit:
            finish_run(store, run_id)


def _fetch_in_run(store, adapter: Adapter, params: Params, deps: Deps, run_id: str,
                  new_problem: str | None, problem_id: str | None) -> dict:
    cfg = load_config(store.workspace)
    acfg = adapter_cfg(cfg, adapter.name)

    def unavailable(reason: str):
        _mark_unavailable(store, run_id, adapter.name, reason)
        return _unavailable_error(adapter.name, reason, run_id)

    reason = adapter.unavailable_reason(acfg, deps.home)
    if reason:
        raise unavailable(reason)
    try:
        creds = credentials.load(adapter.keys, env=deps.env)
    except credentials.MissingKey as exc:
        raise unavailable(str(exc)) from None

    estimate = adapter.estimate_usd(params, acfg)
    reserve(store, run_id, adapter, estimate, cfg)

    ctx = Ctx(transport=deps.transport, creds=creds, now=deps.now(), cfg=acfg,
              runner=deps.runner, home=deps.home)
    pacer = Pacer(store.workspace, clock=deps.clock, sleep=deps.sleep)
    result: Result | None = None
    status, error, why = "ok", None, None
    try:
        result = _with_retries(adapter, params, ctx, pacer, deps.sleep)
    except Unavailable as exc:
        status, why = "unavailable", str(exc)
    except (FetchFailed, TransportError) as exc:
        status, error = "failed", credentials.redact(str(exc)) or type(exc).__name__
    except (KeyError, TypeError, ValueError, AttributeError, IndexError) as exc:
        status, error = "failed", credentials.redact(f"unreadable response: {type(exc).__name__}: {exc}")
    except Exception as exc:  # noqa: BLE001 -- anything else still settles the reservation as failed
        status, error = "failed", credentials.redact(f"{type(exc).__name__}: {exc}")

    if status == "unavailable":
        actual = 0.0  # the source refused before doing paid work
    elif result is not None and result.cost_usd is not None:
        actual = float(result.cost_usd)
    else:
        actual = estimate

    with store.lock():
        run = _running(store, run_id)
        st = {**_fresh_status(), **(run.get("adapter_status") or {}).get(adapter.name, {})}
        delta = actual - estimate
        run = {**run, "spend_usd": max(0.0, float(run.get("spend_usd") or 0) + delta)}
        _set_status(store, run, adapter.name,
                    {"type": "spend_booked", "adapter": adapter.name, "estimate_usd": estimate,
                     "actual_usd": actual, "status": status},
                    status=status, error=error, reason=why,
                    ok=st["ok"] + (status == "ok"), failures=st["failures"] + (status == "failed"),
                    spend_usd=max(0.0, st["spend_usd"] + delta))
        if status == "ok":
            known = store.evidence_index() if result.evidence else {}
            evidence_ids = list(dict.fromkeys(
                store.insert_locked("evidence", ev, known_evidence=known)["id"]
                for ev in result.evidence))
            entries = [{"id": new_ulid(ctx.now), **e} for e in result.entries]
            problem = _record_success(store, adapter, new_problem, problem_id, entries,
                                      evidence_ids)
        elif status == "failed":
            problem = _record_failure(store, adapter, new_problem, problem_id, error, ctx.now)

    if status == "unavailable":
        raise _unavailable_error(adapter.name, why, run_id)
    if status == "failed":
        details = {"adapter": adapter.name, "status": "failed", "error": error, "run_id": run_id}
        if problem is not None:
            details.update(problem_id=problem["id"], problem_status=problem["status"])
        raise AdapterError(f"{adapter.name} fetch failed: {error}", details=details)
    return {"adapter": adapter.name, "status": "ok", "run_id": run_id, "entries": entries,
            "evidence_ids": evidence_ids, "problem": problem, "cost_usd": actual,
            "cost_estimated": adapter.cost.estimated}


def _with_retries(adapter: Adapter, params: Params, ctx: Ctx, pacer: Pacer,
                  sleep: Callable[[float], None]) -> Result:
    for attempt in range(MAX_RETRIES + 1):
        pacer.wait(adapter.name, adapter.min_interval_s)
        try:
            return adapter.fetch(params, ctx)
        except RateLimited as exc:
            if attempt == MAX_RETRIES:
                raise FetchFailed(f"{exc}; gave up after {MAX_RETRIES} retries") from None
            delay = exc.retry_after if exc.retry_after is not None else BACKOFF_BASE_S * 2 ** attempt
            sleep(min(BACKOFF_MAX_S, delay))
    raise AssertionError("unreachable")


def _record_success(store: Store, adapter: Adapter, new_problem: str | None,
                    problem_id: str | None, entries: list[dict],
                    evidence_ids: list[str]) -> dict | None:
    if new_problem is not None:
        body = {"title": new_problem, "status": "found", "demand": entries}
        if evidence_ids:
            body["evidence_ids"] = evidence_ids
        return store.insert_locked("problem", body)
    if not problem_id:
        return None
    rec = store.get("problem", problem_id)
    new = {**rec, "demand": [*(rec.get("demand") or []), *entries],
           "evidence_ids": list(dict.fromkeys([*(rec.get("evidence_ids") or []), *evidence_ids]))}
    if not new["evidence_ids"]:
        new.pop("evidence_ids")
    events = [{"type": "demand_fetched", "adapter": adapter.name,
               "entry_ids": [e["id"] for e in entries], "evidence_ids": evidence_ids}]
    if rec["status"] == "pending_evidence" and entries:
        new.update(status="found", refetch_failures=0)
        new.pop("pending_fetch", None)
        events.append({"type": "transition", "from": "pending_evidence", "to": "found",
                       "reason": f"demand fetched by {adapter.name}"})
    return store.put_locked("problem", new, *events)


def _record_failure(store: Store, adapter: Adapter, new_problem: str | None,
                    problem_id: str | None, error: str, at: datetime) -> dict | None:
    pending = {"adapter": adapter.name, "error": error, "attempted_at": fmt_ts(at)}
    if new_problem is not None:
        return store.insert_locked("problem", {"title": new_problem, "status": "pending_evidence",
                                               "pending_fetch": pending})
    if not problem_id:
        return None
    rec = store.get("problem", problem_id)
    if rec.get("demand") or rec["status"] != "pending_evidence":
        return rec  # it already holds a number; the failure lives on the run
    return store.put_locked("problem", {**rec, "pending_fetch": pending},
                            {"type": "fetch_failed", "adapter": adapter.name, "error": error})


# --- sources ------------------------------------------------------------------------


def sources(store: Store, deps: Deps) -> dict:
    cfg = load_config(store.workspace)
    monthly, per_run = caps(cfg)
    spent = month_spend(store, store.now())
    out = []
    for a in REGISTRY.values():
        acfg = adapter_cfg(cfg, a.name)
        gone = credentials.missing(a.keys, env=deps.env)
        unit, src = a.unit_usd(acfg)
        reason = None
        if a.method == "manual":
            status = "manual"
        else:
            reason = a.unavailable_reason(acfg, deps.home)
            if reason is None and gone:
                reason = str(credentials.MissingKey(gone))
            if reason is None and a.paid and monthly_cap_crossed(spent, unit, monthly):
                reason = BUDGET
            status = "unavailable" if reason else "available"
        item = {"name": a.name, "label": a.label, "status": status, "method": a.method,
                "confidence": a.confidence, "paid": a.paid, "evidence_only": a.evidence_only,
                "keys": [{"name": k, "set": k not in gone} for k in a.keys],
                "cost": {"model": a.cost.model, "usd": unit if a.paid else 0.0,
                         "source": src if a.paid else "default", "estimated": a.cost.estimated},
                "min_interval_s": a.min_interval_s}
        if reason:
            item["reason"] = reason
        out.append(item)
    keyed = any(s["status"] == "available" and s["keys"] for s in out)
    return {"sources": out, "mode": "keyed" if keyed else "keyless",
            "budget": {"monthly_cap_usd": monthly, "per_run_cap_usd": per_run,
                       "spent_this_month_usd": round(spent, 6),
                       "remaining_usd": round(max(0.0, monthly - spent), 6)}}
