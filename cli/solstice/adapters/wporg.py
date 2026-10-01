"""WordPress.org plugin directory search (keyless).

`active_installs` is bucketed by WordPress.org (floored to 10, 100, 1,000,
10,000 ...), so every install number is stored as the bucket floor and noted
as a lower bound.
"""

from __future__ import annotations

from solstice.adapters.base import (
    Adapter, Ctx, FetchFailed, Params, Request, Result, num, raise_for_http, url_with)

API = "https://api.wordpress.org/plugins/info/1.2/"
PER_PAGE = 20
BUCKET_NOTE = "WordPress.org buckets active installs; value is the bucket floor (a lower bound)"


class WordPressOrg(Adapter):
    name = "wporg"
    label = "WordPress.org"
    method = "api"
    confidence = "high"

    def fetch(self, params: Params, ctx: Ctx) -> Result:
        query = params.queries[0]
        url = url_with(API, {"action": "query_plugins", "request[search]": query,
                             "request[per_page]": PER_PAGE, "request[page]": 1})
        resp = ctx.transport(Request("GET", url))
        raise_for_http(resp, label=self.label)
        data = resp.json()
        if not isinstance(data, dict) or not isinstance(data.get("plugins"), list):
            raise FetchFailed("WordPress.org response has no plugins list")
        total = num((data.get("info") or {}).get("results"))

        evidence, installs = [], []
        for p in data["plugins"]:
            slug = p.get("slug")
            floor = num(p.get("active_installs"))
            if not slug or floor is None:
                continue
            installs.append(floor)
            evidence.append(self.evidence(
                ctx, kind="plugin_listing", url=f"https://wordpress.org/plugins/{slug}/",
                summary=p.get("name"), metric="active_installs", value=floor, unit="installs",
                data={"slug": slug, "active_installs_bucket": str(p.get("active_installs")),
                      "rating": p.get("rating"), "num_ratings": p.get("num_ratings"),
                      "support_threads": p.get("support_threads"),
                      "support_threads_resolved": p.get("support_threads_resolved"),
                      "last_updated": p.get("last_updated")}))
        if total is None and not installs:
            raise FetchFailed("WordPress.org response carried no counts")

        entries = []
        if installs:
            entries.append(self.entry(ctx, metric="active_installs_top", value=max(installs),
                                      unit="installs", query=query, url=url, note=BUCKET_NOTE))
            entries.append(self.entry(ctx, metric="active_installs_sum", value=sum(installs),
                                      unit="installs", query=query, url=url,
                                      note=f"{BUCKET_NOTE}; summed over the first {PER_PAGE} results"))
        if total is not None:
            entries.append(self.entry(ctx, metric="plugin_count", value=total, unit="plugins",
                                      query=query, url=url))
        return Result(entries=entries, evidence=evidence)
