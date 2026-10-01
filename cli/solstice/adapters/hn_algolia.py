"""Hacker News search through the Algolia API (keyless).

Counts stories mentioning the query over a trailing window (`nbHits`) and
sums points and comments over the top hits returned.
"""

from __future__ import annotations

from datetime import timedelta

from solstice.adapters.base import (
    Adapter, Ctx, FetchFailed, Params, Request, Result, num, raise_for_http, url_with)

API = "https://hn.algolia.com/api/v1/search"
WINDOW_DAYS = 365
HITS = 20


class HackerNews(Adapter):
    name = "hn_algolia"
    label = "Hacker News"
    method = "api"
    confidence = "medium"
    min_interval_s = 0.4  # documented limit: 10,000 requests per hour per IP

    def fetch(self, params: Params, ctx: Ctx) -> Result:
        query = params.queries[0]
        since = int((ctx.now - timedelta(days=WINDOW_DAYS)).timestamp())
        url = url_with(API, {"query": query, "tags": "story",
                             "numericFilters": f"created_at_i>{since}", "hitsPerPage": HITS})
        resp = ctx.transport(Request("GET", url))
        raise_for_http(resp, label=self.label)
        data = resp.json()
        hits = data.get("hits") if isinstance(data, dict) else None
        total = num(data.get("nbHits")) if isinstance(data, dict) else None
        if total is None or not isinstance(hits, list):
            raise FetchFailed("Hacker News response has no nbHits/hits")

        points = sum(num(h.get("points")) or 0 for h in hits)
        comments = sum(num(h.get("num_comments")) or 0 for h in hits)
        evidence = [
            self.evidence(ctx, kind="hn_story",
                          url=f"https://news.ycombinator.com/item?id={h['objectID']}",
                          summary=h.get("title"), metric="points", value=num(h.get("points")) or 0,
                          unit="points", data={"num_comments": h.get("num_comments"),
                                               "created_at_i": h.get("created_at_i"),
                                               "link": h.get("url")})
            for h in hits if h.get("objectID")
        ]
        w = f"{WINDOW_DAYS}d"
        entries = [
            self.entry(ctx, metric=f"hn_stories_{w}", value=total, unit="stories", query=query,
                       url=url),
            self.entry(ctx, metric="hn_points_top", value=points, unit="points", query=query,
                       url=url, note=f"summed over the top {len(hits)} stories"),
            self.entry(ctx, metric="hn_comments_top", value=comments, unit="comments",
                       query=query, url=url, note=f"summed over the top {len(hits)} stories"),
        ]
        return Result(entries=entries, evidence=evidence)
