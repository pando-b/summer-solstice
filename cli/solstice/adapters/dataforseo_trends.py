"""DataForSEO Google Trends explore (live endpoint).

Trends values are relative (0-100, normalized within the request), so this
adapter takes exactly one query and records relative interest and its change
across the window, never a volume.
"""

from __future__ import annotations

from solstice.adapters.base import Adapter, Cost, Ctx, FetchFailed, Params, Result, num
from solstice.adapters.dataforseo_volume import API, KEYS, call, location

TIME_RANGE = "past_12_months"


class DataForSEOTrends(Adapter):
    name = "dataforseo_trends"
    label = "DataForSEO Google Trends"
    method = "api"
    confidence = "high"
    keys = KEYS
    cost = Cost("per_task", "usd_per_task", 0.011)
    min_interval_s = 0.25  # documented limit: 250 live tasks per minute

    def fetch(self, params: Params, ctx: Ctx) -> Result:
        query = params.queries[0]
        path = "keywords_data/google_trends/explore/live"
        result, cost = call(ctx, path, {"keywords": [query], "time_range": TIME_RANGE,
                                        "type": "web", "item_types": ["google_trends_graph"],
                                        **location(ctx.cfg)}, label=self.label)
        points = []
        for res in result:
            for item in (res or {}).get("items") or []:
                if item.get("type") != "google_trends_graph":
                    continue
                for d in item.get("data") or []:
                    v = num((d.get("values") or [None])[0])
                    if v is not None and not d.get("missing_data"):
                        points.append(v)
        if len(points) < 2:
            raise FetchFailed(f"{self.label} returned too few data points ({len(points)})")
        half = len(points) // 2
        early, recent = points[:half], points[-half:]
        early_mean = sum(early) / len(early)
        recent_mean = sum(recent) / len(recent)
        url = f"{API}/{path}"
        entries = [self.entry(ctx, metric="trend_interest_recent", value=round(recent_mean, 2),
                              unit="relative_0_100", query=query, url=url,
                              note=f"mean of the last {half} points over {TIME_RANGE}; relative, "
                                   f"not a volume")]
        if early_mean > 0:
            entries.append(self.entry(
                ctx, metric="trend_change_pct",
                value=round((recent_mean - early_mean) / early_mean * 100, 2), unit="percent",
                query=query, url=url, note=f"recent half vs early half over {TIME_RANGE}"))
        return Result(entries=entries, cost_usd=cost)
