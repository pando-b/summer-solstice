"""Typed JSON records in the workspace (KTD1).

Layout under the workspace root::

    records/<plural>/<ULID>.json          one record, validated against its schema
    records/<plural>/<ULID>.events.jsonl  append-only history for that record
    .solstice/write.lock                  single-writer lock with a time-to-live

Every write goes through `Store`, which holds the lock while it writes.
"""

from __future__ import annotations

import json
import os
import time
from collections.abc import Callable
from datetime import UTC, datetime, timedelta
from functools import cache
from importlib import resources
from pathlib import Path

import yaml
from jsonschema import Draft202012Validator

from solstice import lifecycle
from solstice.lifecycle import fmt_ts, parse_ts  # noqa: F401  (re-exported)

SCHEMA_VERSION = 1

ENTITIES: dict[str, str] = {
    "problem": "problems",
    "evidence": "evidence",
    "decision": "decisions",
    "product": "products",
    "approval": "approvals",
    "content_item": "content_items",
    "revenue_snapshot": "revenue_snapshots",
    "run": "runs",
}

# Fields that point at other records by ID; `validate` checks they resolve.
REF_FIELDS: dict[str, str] = {
    "problem_id": "problem",
    "product_id": "product",
    "decision_id": "decision",
    "approval_id": "approval",
    "content_item_id": "content_item",
}

# from_version -> fn(entity, record) returning the record at from_version + 1.
MIGRATIONS: dict[int, Callable[[str, dict], dict]] = {}

DEFAULT_LAUNCH_SPEND_LIMIT_USD = 50.0
LOCK_TTL_SECONDS = 60.0
LOCK_WAIT_SECONDS = 10.0

_IDENTITY = ("id", "schema_version", "created_at", "updated_at")
# Fields only the lifecycle (or a later approvals module) may set.
# Set only by U9's approve/reject flow, never at creation or by update.
_APPROVAL_FLOW_FIELDS = ("approver", "approved_at", "content_hash")

_MANAGED: dict[str, tuple[str, ...]] = {
    "problem": ("status", "refetch_failures"),
    "product": ("status", "test_started_at", "awaiting_owner_from"),
    "approval": ("status", *_APPROVAL_FLOW_FIELDS),
    "evidence": ("url", "fetched_at", "idempotency_key"),
}
# Managed against `update`, but the caller supplies them when creating the record.
_CALLER_PROVENANCE: dict[str, tuple[str, ...]] = {"evidence": ("url", "fetched_at")}
_RESERVED_EVENTS = {"created", "updated", "transition", "migrated", "refetch_failed"}

_CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


class RecordError(Exception):
    """A record is invalid, missing, or at the wrong schema version."""


class LockError(Exception):
    """Another writer holds the workspace lock."""


def now_utc() -> datetime:
    return datetime.now(UTC)


def new_ulid(at: datetime | None = None) -> str:
    ms = int((at or now_utc()).timestamp() * 1000)
    n = (ms << 80) | int.from_bytes(os.urandom(10), "big")
    return "".join(_CROCKFORD[(n >> (5 * i)) & 31] for i in range(25, -1, -1))


# --- schemas and validation -------------------------------------------------


def _require_entity(entity: str) -> None:
    if entity not in ENTITIES:
        raise RecordError(f"unknown entity {entity!r}; expected one of {', '.join(ENTITIES)}")


@cache
def load_schema(entity: str) -> dict:
    _require_entity(entity)
    text = (resources.files("solstice") / "schemas" / f"{entity}.schema.json").read_text()
    return json.loads(text)


@cache
def _validator(entity: str) -> Draft202012Validator:
    return Draft202012Validator(load_schema(entity))


def validate_record(entity: str, record: dict) -> list[str]:
    """Schema errors plus rules JSON Schema cannot express. Empty list = valid."""
    errors = []
    for err in sorted(_validator(entity).iter_errors(record), key=lambda e: list(e.path)):
        where = "/".join(str(p) for p in err.absolute_path) or "(record)"
        errors.append(f"{entity} {where}: {err.message}")
    if entity == "decision" and not errors:
        errors += _decision_rules(record)
    return errors


def _decision_rules(rec: dict) -> list[str]:
    if rec["verdict"] != "go":
        return []
    errs = []
    pf = rec["pro_forma"]
    if pf["gross_margin"] < 0.80:
        errs.append(f"decision pro_forma: go needs gross margin >= 0.80 (R20), got {pf['gross_margin']}")
    if pf["break_even_customers"] > 10:
        errs.append(f"decision pro_forma: go needs break-even within 10 customers (R20), "
                    f"got {pf['break_even_customers']}")
    failing = sorted(k for k, v in rec["checks"].items() if v != "pass")
    if failing:
        errs.append(f"decision checks: go needs every R6 check to pass; not passing: {', '.join(failing)}")
    if rec["operator_load"]["rating"] != "low":
        errs.append(f"decision operator_load: go needs rating low (R19), got {rec['operator_load']['rating']}")
    return errs


def _event_errors(entity: str, event: dict) -> list[str]:
    if not isinstance(event.get("type"), str) or not event["type"]:
        return ["event needs a non-empty string 'type'"]
    if event["type"] in _RESERVED_EVENTS:
        return [f"event type {event['type']!r} is written by the CLI, not by callers"]
    if entity == "product" and event["type"] == "buy_signal":
        defs = load_schema("product")["$defs"]
        sub = {**defs["buy_signal"], "$defs": defs}
        return [f"buy_signal {'/'.join(map(str, e.absolute_path)) or '(event)'}: {e.message}"
                for e in Draft202012Validator(sub).iter_errors(event)]
    return []


# --- config -----------------------------------------------------------------


def launch_spend_limit(workspace: Path) -> float:
    cfg = workspace / ".solstice" / "config.yaml"
    if not cfg.is_file():
        return DEFAULT_LAUNCH_SPEND_LIMIT_USD
    data = yaml.safe_load(cfg.read_text()) or {}
    value = (data.get("budgets") or {}).get("launch_spend_limit_usd")
    return DEFAULT_LAUNCH_SPEND_LIMIT_USD if value is None else float(value)


# --- lock -------------------------------------------------------------------


class Lock:
    """Exclusive create of `.solstice/write.lock` holding an expiry time.

    A holder that crashes leaves a lock that the next writer reclaims once it
    has expired. While a live lock is held the writer polls until `wait`
    seconds pass, then raises LockError.
    """

    def __init__(self, workspace: Path, *, ttl: float, wait: float,
                 now: Callable[[], datetime], sleep: Callable[[float], None]):
        self.path = workspace / ".solstice" / "write.lock"
        self.ttl, self.wait, self.now, self.sleep = ttl, wait, now, sleep

    def __enter__(self) -> Lock:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        waited = 0.0
        while True:
            now = self.now()
            body = json.dumps({"pid": os.getpid(), "acquired_at": fmt_ts(now),
                               "expires_at": fmt_ts(now + timedelta(seconds=self.ttl))})
            tmp = self.path.with_name(f"{self.path.name}.{os.getpid()}.tmp")
            tmp.write_text(body)
            try:
                os.link(tmp, self.path)  # atomic: fails if a lock exists, never half-written
            except FileExistsError:
                holder = self._holder()
                if holder == "gone":
                    continue
                if holder is None or parse_ts(holder["expires_at"]) <= now:
                    self.path.unlink(missing_ok=True)  # expired or unreadable: reclaim
                    continue
                if waited >= self.wait:
                    raise LockError(
                        f"workspace is locked by another solstice writer (pid {holder.get('pid')}) "
                        f"until {holder['expires_at']}; retry after it finishes or the lock expires"
                    ) from None
                step = min(0.2, self.wait - waited) or 0.2
                self.sleep(step)
                waited += step
                continue
            finally:
                tmp.unlink(missing_ok=True)
            return self

    def __exit__(self, *exc) -> None:
        self.path.unlink(missing_ok=True)

    def _holder(self) -> dict | str | None:
        try:
            data = json.loads(self.path.read_text())
            parse_ts(data["expires_at"])
            return data
        except FileNotFoundError:
            return "gone"
        except (ValueError, KeyError, TypeError):
            return None


# --- store ------------------------------------------------------------------


class Store:
    def __init__(self, workspace: Path | str, *, now: Callable[[], datetime] = now_utc,
                 lock_ttl: float | None = None, lock_wait: float | None = None,
                 sleep: Callable[[float], None] = time.sleep):
        self.workspace = Path(workspace)
        self.now = now
        self._lock_args = {
            "ttl": LOCK_TTL_SECONDS if lock_ttl is None else lock_ttl,
            "wait": LOCK_WAIT_SECONDS if lock_wait is None else lock_wait,
            "now": now, "sleep": sleep,
        }

    # paths

    def dir(self, entity: str) -> Path:
        _require_entity(entity)
        return self.workspace / "records" / ENTITIES[entity]

    def _path(self, entity: str, rid: str) -> Path:
        return self.dir(entity) / f"{rid}.json"

    def _events_path(self, entity: str, rid: str) -> Path:
        return self.dir(entity) / f"{rid}.events.jsonl"

    def lock(self) -> Lock:
        return Lock(self.workspace, **self._lock_args)

    # reads

    def get(self, entity: str, rid: str) -> dict:
        path = self._path(entity, rid)
        if not path.is_file():
            raise RecordError(f"{entity} {rid} not found")
        return self._load(entity, path)

    def list(self, entity: str, status: str | None = None) -> list[dict]:
        d = self.dir(entity)
        if not d.is_dir():
            return []
        recs = [self._load(entity, p) for p in sorted(d.glob("*.json"))]
        return [r for r in recs if status is None or r.get("status") == status]

    def events(self, entity: str, rid: str) -> list[dict]:
        path = self._events_path(entity, rid)
        if not path.is_file():
            return []
        return [json.loads(line) for line in path.read_text().splitlines() if line.strip()]

    def _load(self, entity: str, path: Path) -> dict:
        try:
            rec = json.loads(path.read_text())
        except ValueError as exc:
            raise RecordError(f"{path}: not valid JSON ({exc})") from exc
        check_version(rec, path)
        return rec

    # writes

    def create(self, entity: str, body: dict) -> dict:
        if not isinstance(body, dict):
            raise RecordError("record body must be a JSON object")
        clash = [k for k in _IDENTITY if k in body]
        if clash:
            raise RecordError(f"fields set by the CLI cannot be supplied: {', '.join(clash)}")
        initial = lifecycle.INITIAL.get(entity)
        if initial is not None and body.get("status") not in initial:
            raise RecordError(f"a new {entity} must start in {' or '.join(sorted(initial))}; "
                              f"later statuses are reached through `record transition`")
        if entity == "approval" and any(body.get(k) is not None for k in _APPROVAL_FLOW_FIELDS):
            raise RecordError("approver, approved_at and content_hash are set by the approvals flow")
        managed = [k for k in body if k in _MANAGED.get(entity, ())
                   and k not in ("status", *_CALLER_PROVENANCE.get(entity, ()))]
        if managed:
            raise RecordError(f"cannot set {', '.join(managed)} when creating a {entity} "
                              f"(lifecycle-managed; set by `record transition` or the CLI)")
        with self.lock():
            now = self.now()
            rec = {"id": new_ulid(now), "schema_version": SCHEMA_VERSION,
                   "created_at": fmt_ts(now), "updated_at": fmt_ts(now), **body}
            if entity == "evidence":
                rec["idempotency_key"] = evidence_key(rec)
                for existing in self.list("evidence"):
                    if existing.get("idempotency_key") == rec["idempotency_key"]:
                        return existing
            self._check(entity, rec)
            self._write(entity, rec)
            self._append(entity, rec["id"], {"type": "created"})
            return rec

    def update(self, entity: str, rid: str, patch: dict) -> dict:
        if not isinstance(patch, dict) or not patch:
            raise RecordError("patch must be a non-empty JSON object")
        blocked = [k for k in patch if k in _IDENTITY or k in _MANAGED.get(entity, ())]
        if blocked:
            raise RecordError(f"cannot update {', '.join(blocked)} on {entity} "
                              f"(identity or lifecycle-managed; use `record transition`)")
        with self.lock():
            rec = {**self.get(entity, rid), **patch, "updated_at": fmt_ts(self.now())}
            self._check(entity, rec)
            self._write(entity, rec)
            self._append(entity, rid, {"type": "updated", "fields": sorted(patch)})
            return rec

    def transition(self, entity: str, rid: str, to: str, fields: dict | None = None) -> dict:
        fields = dict(fields or {})
        reason = fields.pop("reason", None)
        blocked = [k for k in fields if k in _IDENTITY or k in _MANAGED.get(entity, ())]
        if blocked:
            raise RecordError(f"transition cannot set {', '.join(blocked)}")
        with self.lock():
            rec = self.get(entity, rid)
            ctx = lifecycle.Context(
                now=self.now(),
                events=self.events(entity, rid),
                others=[p for p in self.list("product") if p["id"] != rid] if entity == "product" else [],
                product_events=(self.events("product", rec["product_id"])
                                if entity == "approval" and rec.get("product_id") else []),
                launch_limit=launch_spend_limit(self.workspace),
            )
            new = lifecycle.apply(entity, {**rec, **fields}, to, ctx)
            new["updated_at"] = fmt_ts(self.now())
            self._check(entity, new)
            self._write(entity, new)
            event = {"type": "transition", "from": rec["status"], "to": to}
            if reason:
                event["reason"] = reason
            self._append(entity, rid, event)
            return new

    def record_refetch_failure(self, rid: str, error: str) -> dict:
        """Count one failed refetch run for a pending_evidence problem (R5)."""
        with self.lock():
            rec = self.get("problem", rid)
            if rec["status"] != "pending_evidence":
                raise RecordError(f"problem {rid} is {rec['status']}, not pending_evidence")
            rec = {**rec, "refetch_failures": rec.get("refetch_failures", 0) + 1,
                   "updated_at": fmt_ts(self.now())}
            self._check("problem", rec)
            self._write("problem", rec)
            self._append("problem", rid, {"type": "refetch_failed", "error": error,
                                          "count": rec["refetch_failures"]})
            return rec

    def add_event(self, entity: str, rid: str, event: dict) -> dict:
        if not isinstance(event, dict):
            raise RecordError("event must be a JSON object")
        with self.lock():
            self.get(entity, rid)
            event = {**event, "at": event.get("at") or fmt_ts(self.now())}
            errs = _event_errors(entity, event)
            if errs:
                raise RecordError("; ".join(errs))
            self._append(entity, rid, event, stamp=False)
            return event

    # whole-workspace checks

    def iter_files(self):
        root = self.workspace / "records"
        for entity, plural in ENTITIES.items():
            d = root / plural
            if d.is_dir():
                for p in sorted(d.glob("*.json")):
                    yield entity, p

    def validate_all(self) -> tuple[int, list[str]]:
        errors, checked = [], 0
        for entity, path in self.iter_files():
            checked += 1
            try:
                rec = self._load(entity, path)
            except RecordError as exc:
                errors.append(str(exc))
                continue
            if rec.get("id") != path.stem:
                errors.append(f"{path}: id {rec.get('id')!r} does not match filename")
            errors += [f"{path.stem}: {e}" for e in validate_record(entity, rec)]
            ev = self._events_path(entity, path.stem)
            if ev.is_file():
                for n, line in enumerate(ev.read_text().splitlines(), 1):
                    try:
                        json.loads(line)
                    except ValueError:
                        errors.append(f"{ev}: line {n} is not valid JSON")
        if not errors:
            errors += self.check_references()
        return checked, errors

    def check_references(self) -> list[str]:
        known = {(e, p.stem) for e, p in self.iter_files()}
        errs = []
        for entity, path in self.iter_files():
            rec = json.loads(path.read_text())
            for field, target in REF_FIELDS.items():
                ref = rec.get(field)
                if ref and (target, ref) not in known:
                    errs.append(f"{entity} {path.stem}: {field} {ref} does not resolve to a {target}")
            for ref in rec.get("evidence_ids") or []:
                if ("evidence", ref) not in known:
                    errs.append(f"{entity} {path.stem}: evidence_ids {ref} does not resolve")
        return errs

    def migrate(self) -> tuple[list[str], list[str]]:
        migrated, errors = [], []
        with self.lock():
            for entity, path in self.iter_files():
                try:
                    rec = json.loads(path.read_text())
                except ValueError as exc:
                    errors.append(f"{path}: not valid JSON ({exc})")
                    continue
                version = rec.get("schema_version")
                if not isinstance(version, int):
                    errors.append(f"{path}: missing schema_version")
                    continue
                if version > SCHEMA_VERSION:
                    errors.append(_newer_msg(path, version))
                    continue
                if version == SCHEMA_VERSION:
                    continue
                start = version
                try:
                    while rec["schema_version"] < SCHEMA_VERSION:
                        step = MIGRATIONS.get(rec["schema_version"])
                        if step is None:
                            raise RecordError(f"no migration registered from schema_version "
                                              f"{rec['schema_version']}")
                        rec = step(entity, rec)
                    errs = validate_record(entity, rec)
                    if errs:
                        raise RecordError("; ".join(errs))
                except RecordError as exc:
                    errors.append(f"{path}: {exc}")
                    continue
                self._write(entity, rec)
                self._append(entity, rec["id"], {"type": "migrated", "from": start,
                                                 "to": SCHEMA_VERSION})
                migrated.append(rec["id"])
        return migrated, errors

    # internals

    def _check(self, entity: str, rec: dict) -> None:
        errs = validate_record(entity, rec)
        if errs:
            raise RecordError("invalid record: " + "; ".join(errs))

    def _write(self, entity: str, rec: dict) -> None:
        path = self._path(entity, rec["id"])
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(rec, indent=2, sort_keys=True) + "\n")
        os.replace(tmp, path)

    def _append(self, entity: str, rid: str, event: dict, stamp: bool = True) -> None:
        if stamp:
            event = {"at": fmt_ts(self.now()), **event}
        path = self._events_path(entity, rid)
        with path.open("a") as fh:
            fh.write(json.dumps(event, sort_keys=True) + "\n")


def evidence_key(rec: dict) -> str:
    day = parse_ts(rec["fetched_at"]).date().isoformat() if _is_ts(rec.get("fetched_at")) else "?"
    return f"{rec.get('url')}|{day}"


def _is_ts(value) -> bool:
    try:
        parse_ts(value)
        return True
    except (TypeError, ValueError):
        return False


def check_version(rec: dict, path: Path) -> None:
    version = rec.get("schema_version")
    if not isinstance(version, int):
        raise RecordError(f"{path}: missing schema_version")
    if version < SCHEMA_VERSION:
        raise RecordError(f"{path}: schema_version {version} is older than this CLI's "
                          f"{SCHEMA_VERSION}; run `solstice migrate` first")
    if version > SCHEMA_VERSION:
        raise RecordError(_newer_msg(path, version))


def _newer_msg(path: Path, version: int) -> str:
    return (f"{path}: schema_version {version} is newer than this CLI's {SCHEMA_VERSION}; "
            f"upgrade the CLI")
