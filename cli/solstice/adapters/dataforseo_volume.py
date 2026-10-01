"""DataForSEO Google Ads keyword volume (live endpoint, HTTP Basic auth).

All `--query` values go into one task (the endpoint charges per task, not
per keyword), so a skill batches keywords after its fan-out. DataForSEO
answers HTTP 200 even when a task fails: any top-level or task
`status_code` other than 20000 is a failure, never a zero.
"""

from __future__ import annotations

import base64
import json

from solstice import credentials
from solstice.adapters.base import (
    Adapter, Cost, Ctx, FetchFailed, Params, RateLimited, Request, Response, Result, num,
    raise_for_http)
from solstice.errors import UsageError

API = "https://api.dataforseo.com/v3"
KEYS = ("DATAFORSEO_LOGIN", "DATAFORSEO_PASSWORD")
OK = 20000
RATE_LIMIT_CODES = {40202}  # per-minute rate limit exceeded
DEFAULT_LOCATION = 2840  # United States
DEFAULT_LANGUAGE = "en"
MAX_KEYWORDS = 1000


def call(ctx: Ctx, path: str, task: dict, *, label: str) -> tuple[list, float | None]:
    """POST one task; return (task result list, reported cost in USD)."""
    token = base64.b64encode(
        f"{ctx.creds[KEYS[0]]}:{ctx.creds[KEYS[1]]}".encode()).decode()
    credentials.register_secret(token)
    resp: Response = ctx.transport(Request(
        "POST", f"{API}/{path}", body=json.dumps([task]).encode(),
        headers={"Authorization": f"Basic {token}", "Content-Type": "application/json"}))
    raise_for_http(resp, label=label)
    data = resp.json()
    if not isinstance(data, dict):
        raise FetchFailed(f"{label} response is not an object")
    _check_code(data, label)
    tasks = data.get("tasks") or []
    if len(tasks) != 1:
        raise FetchFailed(f"{label} returned {len(tasks)} tasks, expected 1")
    _check_code(tasks[0], label)
    cost = num(data.get("cost"))
    return tasks[0].get("result") or [], cost


def _check_code(obj: dict, label: str) -> None:
    code = obj.get("status_code")
    if code == OK:
        return
    if code in RATE_LIMIT_CODES:
        raise RateLimited(None, f"{label} rate limited (status_code {code})")
    raise FetchFailed(f"{label} status_code {code}: {obj.get('status_message', 'no message')}",
                      code=code)


def location(cfg: dict) -> dict:
    return {"location_code": int(cfg.get("location_code", DEFAULT_LOCATION)),
            "language_code": str(cfg.get("language_code", DEFAULT_LANGUAGE))}


class DataForSEOVolume(Adapter):
    name = "dataforseo_volume"
    label = "DataForSEO keyword volume"
    method = "api"
    confidence = "high"
    keys = KEYS
    cost = Cost("per_task", "usd_per_task", 0.09)
    min_interval_s = 5.0  # documented limit: 12 requests per minute per account

    def check(self, params: Params) -> None:
        qs = [q for q in params.queries if q.strip()]
        if not qs or len(qs) != len(params.queries):
            raise UsageError(f"{self.name} needs one or more non-empty --query values")
        if len(qs) > MAX_KEYWORDS:
            raise UsageError(f"{self.name} takes at most {MAX_KEYWORDS} --query values per task")
        if params.handle:
            raise UsageError(f"{self.name} does not take --handle")

    def fetch(self, params: Params, ctx: Ctx) -> Result:
        path = "keywords_data/google_ads/search_volume/live"
        result, cost = call(ctx, path, {"keywords": params.queries, **location(ctx.cfg)},
                            label=self.label)
        url = f"{API}/{path}"
        by_kw = {str(r.get("keyword", "")).lower(): r for r in result if isinstance(r, dict)}
        entries, missing = [], []
        for q in params.queries:
            vol = num((by_kw.get(q.lower()) or {}).get("search_volume"))
            if vol is None:  # no data is not zero (R5)
                missing.append(q)
                continue
            entries.append(self.entry(ctx, metric="keyword_volume", value=vol,
                                      unit="searches_per_month", query=q, url=url))
        if not entries:
            raise FetchFailed(f"{self.label} returned no volume for: {', '.join(missing)}")
        return Result(entries=entries, cost_usd=cost)
