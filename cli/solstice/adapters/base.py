"""The demand-adapter contract.

An adapter turns one fetch request into normalized demand entries (the
problem schema's `demand` shape) and evidence bodies. It declares its
method, confidence, the key names it needs, and its cost model. Its HTTP
transport (or, for a local engine, its process runner) is injected, so tests
replay recorded responses without a network.

Adapters never read keys themselves: `demand.py` asks `credentials.py` and
passes the values in `Ctx.creds`. They raise:

- `FetchFailed`  the source answered with an error, or nothing usable
- `RateLimited`  retry after a pause (bounded by the caller)
- `Unavailable`  the source cannot serve this run (e.g. out of credits)
- `TransportError` (from the transport) timeouts and connection failures
"""

from __future__ import annotations

import http.client
import json
import urllib.error
import urllib.parse
import urllib.request
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from solstice.errors import UsageError
from solstice.lifecycle import fmt_ts

# `Unavailable` reasons the run ledger recognizes.
OUT_OF_CREDITS = "out of credits"
BUDGET = "budget"

USER_AGENT = "solstice-cli (+https://github.com/pando-b/summer-solstice)"
DEFAULT_TIMEOUT = 60.0


# --- transport ----------------------------------------------------------------


@dataclass
class Request:
    method: str
    url: str
    headers: dict[str, str] = field(default_factory=dict)
    body: bytes | None = None
    timeout: float = DEFAULT_TIMEOUT


@dataclass
class Response:
    status: int
    headers: Mapping[str, str]
    body: bytes

    def header(self, name: str) -> str | None:
        for k, v in self.headers.items():
            if k.lower() == name.lower():
                return v
        return None

    def json(self) -> Any:
        try:
            return json.loads(self.body)
        except ValueError as exc:
            raise FetchFailed(f"response is not JSON (HTTP {self.status})") from exc


class TransportError(Exception):
    """Timeout or connection failure: no HTTP response at all."""


Transport = Callable[[Request], Response]


def send(req: Request, open_fn: Callable[..., Any]) -> Response:
    """Send `req` through `open_fn` (`urlopen` or an opener's `open`). HTTP
    error statuses come back as a Response; only timeouts and connection
    failures raise."""
    r = urllib.request.Request(req.url, data=req.body, method=req.method,
                               headers={"User-Agent": USER_AGENT, **req.headers})
    try:
        with open_fn(r, timeout=req.timeout) as resp:  # noqa: S310 (https URLs only)
            return Response(resp.status, dict(resp.headers), resp.read())
    except urllib.error.HTTPError as exc:
        return Response(exc.code, dict(exc.headers or {}), exc.read() or b"")
    except (urllib.error.URLError, TimeoutError, OSError, http.client.HTTPException) as exc:
        reason = getattr(exc, "reason", exc)
        raise TransportError(f"{type(exc).__name__}: {reason}") from None


def http_transport(req: Request) -> Response:
    """The real transport (stdlib urllib, following redirects)."""
    return send(req, urllib.request.urlopen)


# Runner for local engines: (argv, timeout) -> (exit code, stdout, stderr).
Runner = Callable[[list[str], float], tuple[int, str, str]]


# --- outcomes -------------------------------------------------------------------


class FetchFailed(Exception):
    def __init__(self, message: str, code: int | str | None = None):
        self.code = code
        super().__init__(message if code is None else f"{message} (code {code})")


class RateLimited(Exception):
    def __init__(self, retry_after: float | None = None, message: str = "rate limited"):
        self.retry_after = retry_after
        super().__init__(message)


class Unavailable(Exception):
    """The source cannot serve calls for the rest of this run."""


# --- request / context / result ---------------------------------------------------


@dataclass
class Params:
    queries: list[str] = field(default_factory=list)
    handle: str | None = None
    platform: str | None = None
    # manual entry
    metric: str | None = None
    value: float | None = None
    unit: str | None = None
    url: str | None = None
    source: str | None = None


@dataclass
class Ctx:
    transport: Transport
    creds: dict[str, str]
    now: datetime
    cfg: dict
    runner: Runner | None = None
    home: Path | None = None


@dataclass
class Result:
    entries: list[dict] = field(default_factory=list)
    evidence: list[dict] = field(default_factory=list)
    cost_usd: float | None = None  # actual cost when the source reports it


@dataclass(frozen=True)
class Cost:
    model: str  # free | per_task | per_credit | per_call | per_run
    config_key: str | None  # adapters.<name>.<config_key> overrides the default
    default_usd: float
    estimated: bool = False  # true when the real spend is only knowable outside the CLI


class Adapter:
    name: str = ""
    label: str = ""
    method: str = "api"
    confidence: str = "medium"
    keys: tuple[str, ...] = ()
    cost: Cost = Cost("free", None, 0.0)
    min_interval_s: float = 0.0  # documented rate limit, enforced across processes
    evidence_only: bool = False  # never yields a demand number

    @property
    def paid(self) -> bool:
        return self.cost.model != "free"

    def unit_usd(self, cfg: dict) -> tuple[float, str]:
        """(USD per unit, "config"|"default")."""
        if self.cost.config_key and cfg.get(self.cost.config_key) is not None:
            return float(cfg[self.cost.config_key]), "config"
        return self.cost.default_usd, "default"

    def estimate_usd(self, params: Params, cfg: dict) -> float:
        return self.unit_usd(cfg)[0] if self.paid else 0.0

    def check(self, params: Params) -> None:
        """Raise UsageError when the params do not fit this adapter."""
        if len(params.queries) != 1 or not params.queries[0].strip():
            raise UsageError(f"{self.name} takes exactly one --query")
        if params.handle:
            raise UsageError(f"{self.name} does not take --handle")

    def unavailable_reason(self, cfg: dict, home: Path | None) -> str | None:
        """Why the adapter cannot run apart from keys and budget, or None."""
        return None

    def fetch(self, params: Params, ctx: Ctx) -> Result:
        raise NotImplementedError

    # helpers

    def entry(self, ctx: Ctx, *, metric: str, value: float, unit: str, query: str, url: str,
              source: str | None = None, note: str | None = None) -> dict:
        e = {"metric": metric, "value": value, "unit": unit, "source": source or self.label,
             "query": query, "fetched_at": fmt_ts(ctx.now), "url": url, "adapter": self.name,
             "method": self.method, "confidence": self.confidence}
        if note:
            e["note"] = note
        return e

    def evidence(self, ctx: Ctx, *, kind: str, url: str, summary: str | None = None,
                 metric: str | None = None, value: float | None = None, unit: str | None = None,
                 data: dict | None = None) -> dict:
        ev = {"kind": kind, "url": url, "fetched_at": fmt_ts(ctx.now), "adapter": self.name,
              "method": self.method}
        if summary:
            ev["summary"] = summary[:500]
        if metric is not None and value is not None:
            ev.update(metric=metric, value=value, unit=unit or "count")
        if data:
            ev["data"] = data
        return ev


def url_with(base: str, params: Mapping[str, Any]) -> str:
    return f"{base}?{urllib.parse.urlencode(params)}"


def raise_for_http(resp: Response, *, label: str) -> None:
    """Map the common HTTP statuses: 429 is a retry, anything else non-2xx fails."""
    if resp.status == 429:
        raise RateLimited(retry_after_seconds(resp), f"{label} rate limited (HTTP 429)")
    if not 200 <= resp.status < 300:
        raise FetchFailed(f"{label} returned HTTP {resp.status}", code=resp.status)


def retry_after_seconds(resp: Response) -> float | None:
    for name in ("Retry-After", "X-RateLimit-Reset"):
        raw = resp.header(name)
        if raw is None:
            continue
        try:
            value = float(raw)
        except ValueError:
            continue
        if value > 1_000_000_000:  # an epoch timestamp, not a delay
            return None
        return max(0.0, value)
    return None


def num(value: Any) -> float | None:
    """A number from an int, float, or a numeric string like "12,000" or "2,000+"."""
    if isinstance(value, bool) or value is None:
        return None
    if isinstance(value, (int, float)):
        return value
    if isinstance(value, str):
        cleaned = value.replace(",", "").rstrip("+").strip()
        try:
            f = float(cleaned)
        except ValueError:
            return None
        return int(f) if f.is_integer() else f
    return None


def first(mapping: Mapping, *names: str) -> Any:
    for n in names:
        if mapping.get(n) is not None:
            return mapping[n]
    return None
