"""ScrapeCreators social search (x-api-key header; 1 credit per request).

Reddit, TikTok, and YouTube use keyword search. X has no keyword search on
this API, only handle lookups, so the X platform reads the popular posts of
one named account (`--handle`) and never claims a keyword-wide count.

Social numbers are engagement proxies: post count and summed engagement are
recorded at `low` confidence, and every post is kept as an evidence record.
HTTP 402 means the account is out of credits; the adapter is then
unavailable for the rest of the run.

Response field names are read through short alias lists; confirm them
against a recorded response of your own.
"""

from __future__ import annotations

import re

from solstice.adapters.base import (
    Adapter, Cost, Ctx, FetchFailed, Params, Request, Result, Unavailable, first, num,
    raise_for_http, url_with)
from solstice.errors import UsageError

API = "https://api.scrapecreators.com"
KEY = "SCRAPECREATORS_API_KEY"
KEYWORD_PLATFORMS = ("reddit", "tiktok", "youtube")
PLATFORMS = (*KEYWORD_PLATFORMS, "x")
_HANDLE = re.compile(r"^[A-Za-z0-9_]{1,15}$")


class ScrapeCreators(Adapter):
    name = "scrapecreators"
    label = "ScrapeCreators"
    method = "api"
    confidence = "low"
    keys = (KEY,)
    cost = Cost("per_credit", "usd_per_credit", 0.002)

    def check(self, params: Params) -> None:
        if params.platform not in PLATFORMS:
            raise UsageError(f"scrapecreators needs --platform, one of {', '.join(PLATFORMS)}")
        if params.platform == "x":
            if params.queries or not params.handle:
                raise UsageError("scrapecreators --platform x reads one account: pass --handle, "
                                 "not --query (there is no keyword search for X)")
            if not _HANDLE.match(params.handle.lstrip("@")):
                raise UsageError("--handle must be an X handle (letters, digits, _)")
            return
        if params.handle:
            raise UsageError(f"--handle applies only to --platform x, not {params.platform}")
        super().check(params)

    def fetch(self, params: Params, ctx: Ctx) -> Result:
        if params.platform == "x":
            handle = params.handle.lstrip("@")
            url = url_with(f"{API}/v1/twitter/user-tweets", {"handle": handle})
            query = f"@{handle}"
        else:
            query = params.queries[0]
            path, extra = {
                "reddit": ("/v1/reddit/search", {"sort": "relevance", "timeframe": "year"}),
                "tiktok": ("/v1/tiktok/search/keyword", {}),
                "youtube": ("/v1/youtube/search", {"uploadDate": "this_year",
                                                   "includeExtras": "true"}),
            }[params.platform]
            url = url_with(f"{API}{path}", {"query": query, **extra})
        resp = ctx.transport(Request("GET", url, headers={"x-api-key": ctx.creds[KEY]}))
        if resp.status == 402:
            raise Unavailable("out of credits")
        raise_for_http(resp, label=self.label)
        data = resp.json()
        if not isinstance(data, dict):
            raise FetchFailed("ScrapeCreators response is not an object")
        posts = getattr(self, f"_{params.platform}")(data, params)

        evidence = [self.evidence(ctx, kind="social_post", url=p["url"], summary=p["title"],
                                  metric="engagement", value=p["engagement"], unit="engagement",
                                  data={"platform": params.platform, **p["stats"]})
                    for p in posts]
        total = sum(p["engagement"] for p in posts)
        pf = params.platform
        entries = [
            self.entry(ctx, metric=f"{pf}_post_count", value=len(posts), unit="posts",
                       query=query, url=url, source=f"{self.label} ({pf})"),
            self.entry(ctx, metric=f"{pf}_engagement_sum", value=total, unit="engagement",
                       query=query, url=url, source=f"{self.label} ({pf})",
                       note="engagement proxy summed over the posts returned"),
        ]
        return Result(entries=entries, evidence=evidence)

    # per-platform parsing -> [{"url", "title", "engagement", "stats"}]

    @staticmethod
    def _post(url: str, title, stats: dict) -> dict:
        clean = {k: v for k, v in stats.items() if v is not None}
        return {"url": url, "title": str(title or "")[:300], "stats": clean,
                "engagement": sum(clean.values())}

    def _reddit(self, data: dict, params: Params) -> list[dict]:
        posts = data.get("posts")
        if not isinstance(posts, list):
            raise FetchFailed("ScrapeCreators reddit response has no posts list")
        out = []
        for p in posts:
            url = p.get("url") or (f"https://www.reddit.com{p['permalink']}" if p.get("permalink") else None)
            if not url:
                continue
            out.append(self._post(url, p.get("title"), {
                "score": num(first(p, "score", "ups", "upvotes")),
                "comments": num(first(p, "num_comments", "comment_count"))}))
        return out

    def _tiktok(self, data: dict, params: Params) -> list[dict]:
        items = data.get("search_item_list")
        if not isinstance(items, list):
            raise FetchFailed("ScrapeCreators tiktok response has no search_item_list")
        out, seen = [], set()
        for it in items:
            info = (it or {}).get("aweme_info") or {}
            vid = info.get("aweme_id")
            if not vid or vid in seen:
                continue  # the API can repeat items
            seen.add(vid)
            author = (info.get("author") or {}).get("unique_id") or "_"
            s = info.get("statistics") or {}
            out.append(self._post(f"https://www.tiktok.com/@{author}/video/{vid}", info.get("desc"), {
                k: num(s.get(k)) for k in ("play_count", "digg_count", "comment_count",
                                           "share_count", "collect_count")}))
        return out

    def _youtube(self, data: dict, params: Params) -> list[dict]:
        videos = first(data, "videos", "items")
        if not isinstance(videos, list):
            raise FetchFailed("ScrapeCreators youtube response has no videos list")
        out = []
        for v in videos:
            url = v.get("url") or (f"https://www.youtube.com/watch?v={v['id']}" if v.get("id") else None)
            if not url:
                continue
            out.append(self._post(url, v.get("title"), {
                "views": num(first(v, "viewCountInt", "viewCount")),
                "likes": num(first(v, "likeCountInt", "likeCount")),
                "comments": num(first(v, "commentCountInt", "commentCount"))}))
        return out

    def _x(self, data: dict, params: Params) -> list[dict]:
        tweets = first(data, "tweets", "data")
        if not isinstance(tweets, list):
            raise FetchFailed("ScrapeCreators x response has no tweets list")
        handle = params.handle.lstrip("@")
        out = []
        for t in tweets:
            tid = first(t, "rest_id", "id_str", "id")
            if not tid:
                continue
            legacy = t.get("legacy") or t
            out.append(self._post(f"https://x.com/{handle}/status/{tid}", legacy.get("full_text"), {
                **{k: num(legacy.get(k)) for k in ("favorite_count", "reply_count",
                                                   "retweet_count", "bookmark_count")},
                "views": num((t.get("views") or {}).get("count"))}))
        return out
