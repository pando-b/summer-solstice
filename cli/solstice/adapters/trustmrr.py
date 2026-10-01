"""TrustMRR startup revenue by slug (Bearer key).

Revenue here is verified payment-provider revenue of a comparable product,
which makes it a spend signal. Money arrives in cents and is stored in USD.
Only startups listed on TrustMRR are covered. Field names are read through a
short alias list; confirm them against a recorded response of your own.
"""

from __future__ import annotations

import re
import urllib.parse

from solstice.adapters.base import (
    Adapter, Cost, Ctx, FetchFailed, Params, Request, Result, first, num, raise_for_http)
from solstice.errors import UsageError

API = "https://trustmrr.com/api/v1"
KEY = "TRUSTMRR_API_KEY"
_SLUG = re.compile(r"^[a-z0-9][a-z0-9-]*$")
MRR_FIELDS = ("mrr", "currentMrr", "mrrCents")
REVENUE_30D_FIELDS = ("revenueLast30Days", "last30DaysRevenue", "revenue30d")


class TrustMRR(Adapter):
    name = "trustmrr"
    label = "TrustMRR"
    method = "api"
    confidence = "medium"
    keys = (KEY,)
    cost = Cost("per_call", "usd_per_call", 0.0)
    min_interval_s = 6.0  # documented limit for standard keys: 10 requests per minute

    def check(self, params: Params) -> None:
        super().check(params)
        if not _SLUG.match(params.queries[0]):
            raise UsageError("trustmrr --query is a startup slug (lowercase letters, digits, -)")

    def fetch(self, params: Params, ctx: Ctx) -> Result:
        slug = params.queries[0]
        url = f"{API}/startups/{urllib.parse.quote(slug)}"
        resp = ctx.transport(Request("GET", url, headers={"Authorization": f"Bearer {ctx.creds[KEY]}"}))
        raise_for_http(resp, label=self.label)
        data = resp.json()
        rec = data.get("data") if isinstance(data, dict) else None
        if not isinstance(rec, dict):
            raise FetchFailed("TrustMRR response has no data object")
        mrr = num(first(rec, *MRR_FIELDS))
        rev = num(first(rec, *REVENUE_30D_FIELDS))
        if mrr is None and rev is None:
            raise FetchFailed("TrustMRR response carries no MRR or 30-day revenue")
        page = f"https://trustmrr.com/startup/{urllib.parse.quote(slug)}"
        entries = []
        if mrr is not None:
            entries.append(self.entry(ctx, metric="mrr_usd", value=round(mrr / 100, 2),
                                      unit="usd_per_month", query=slug, url=page))
        if rev is not None:
            entries.append(self.entry(ctx, metric="revenue_30d_usd", value=round(rev / 100, 2),
                                      unit="usd", query=slug, url=page))
        evidence = [self.evidence(
            ctx, kind="startup_revenue", url=page, summary=rec.get("name"),
            metric="mrr_usd" if mrr is not None else "revenue_30d_usd",
            value=round((mrr if mrr is not None else rev) / 100, 2), unit="usd",
            data={k: rec.get(k) for k in ("slug", "website", "customers", "activeSubscriptions",
                                          "growth30d", "totalRevenue") if k in rec})]
        return Result(entries=entries, evidence=evidence)
