"""Name and slug availability for Qualify's name check (R6, AE4, KTD7).

- WordPress.org: the plugins API `plugin_information` action. A found plugin
  is `taken`; a closed plugin keeps its slug, so it is `taken` too; "Plugin
  not found." is `available`. Slugs held by a submission still under review
  are not visible to the API, which the result notes.
- Domains: RDAP through the rdap.org bootstrap, which redirects to the
  registry's RDAP server. A registry 404 is `available` (not registered,
  though it may still be reserved or premium); a 200 is `taken`. A 404 from
  rdap.org itself means it knows no RDAP server for the TLD, which says
  nothing about the name, so it is `pending`.

Any lookup that cannot answer (timeout, connection failure, an error status,
an unreadable body) is `pending`, never `available`. Redirects are followed
here, one hop at a time over https only, so the transport must not follow
them itself. The Chrome Web Store has no lookup API: the qualify skill
searches the store and saves the result as `manual`-method evidence.
"""

from __future__ import annotations

import json
import re
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime

from solstice.adapters.base import Request, Response, Transport, TransportError, send, url_with
from solstice.adapters.wporg import API as WPORG_API
from solstice.errors import UsageError
from solstice.lifecycle import fmt_ts
from solstice.state import now_utc

RDAP_BOOTSTRAP = "https://rdap.org/domain/"
TIMEOUT = 20.0
MAX_REDIRECTS = 3

_SLUG = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,198}[a-z0-9])?$")
_LABEL = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?$")
_PENDING_NOTE = "lookup could not answer; recheck before relying on the name"

__all__ = ["Deps", "UsageError", "check_domain", "check_wporg", "MAX_REDIRECTS"]


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):  # noqa: D401 (hand redirects back as responses)
        return None


def no_redirect_transport(req: Request) -> Response:
    """Like `base.http_transport`, but a 3xx comes back as a Response."""
    return send(req, urllib.request.build_opener(_NoRedirect).open)


@dataclass
class Deps:
    transport: Transport = field(default_factory=lambda: no_redirect_transport)
    now: Callable[[], datetime] = now_utc


def _result(check: str, name: str, status: str, url: str, detail: str, deps: Deps) -> dict:
    return {"check": check, "name": name, "status": status, "url": url, "detail": detail,
            "checked_at": fmt_ts(deps.now())}


def _get(url: str, deps: Deps) -> Response:
    return deps.transport(Request("GET", url, headers={"Accept": "application/json"},
                                  timeout=TIMEOUT))


def _json(resp: Response):
    try:
        return json.loads(resp.body)
    except ValueError:
        return None


# --- WordPress.org ---------------------------------------------------------------


def check_wporg(slug: str, deps: Deps) -> dict:
    if not isinstance(slug, str) or not _SLUG.match(slug):
        raise UsageError(f"{slug!r} is not a WordPress.org slug (lowercase letters, digits, "
                         f"and inner hyphens, at most 200 characters)", details={"slug": slug})
    url = url_with(WPORG_API, {"action": "plugin_information", "request[slug]": slug})
    page = f"https://wordpress.org/plugins/{slug}/"

    def done(status: str, detail: str) -> dict:
        return _result("wporg", slug, status, page if status == "taken" else url, detail, deps)

    try:
        resp = _get(url, deps)
    except TransportError as exc:
        return done("pending", f"{exc}; {_PENDING_NOTE}")
    data = _json(resp)
    if not isinstance(data, dict):
        return done("pending", f"HTTP {resp.status} with an unreadable body; {_PENDING_NOTE}")
    error = data.get("error")
    if error == "closed" or data.get("closed") is True:
        return done("taken", "a closed plugin holds this slug; WordPress.org does not reuse it")
    if isinstance(error, str) and "not found" in error.lower() and resp.status in (200, 404):
        return done("available", "no plugin in the directory has this slug; a submission still "
                                 "under review would not show here")
    if resp.status == 200 and data.get("slug"):
        return done("taken", f"listed in the plugin directory as {data['slug']}")
    return done("pending", f"HTTP {resp.status} without a recognizable answer; {_PENDING_NOTE}")


# --- domains -----------------------------------------------------------------------


def _domain(name: str) -> str:
    n = name.strip().lower().rstrip(".") if isinstance(name, str) else ""
    labels = n.split(".")
    if len(labels) < 2 or len(n) > 253 or not all(_LABEL.match(lb) for lb in labels):
        raise UsageError(f"{name!r} is not a domain name (e.g. example.com)",
                         details={"domain": name})
    return n


def check_domain(name: str, deps: Deps) -> dict:
    domain = _domain(name)
    url = RDAP_BOOTSTRAP + domain

    def done(status: str, detail: str, at: str = url) -> dict:
        return _result("domain", domain, status, at, detail, deps)

    redirected = False
    for _ in range(MAX_REDIRECTS + 1):
        try:
            resp = _get(url, deps)
        except TransportError as exc:
            return done("pending", f"{exc}; {_PENDING_NOTE}")
        if 300 <= resp.status < 400:
            target = resp.header("Location") or ""
            if not target.startswith("https://"):
                return done("pending", f"RDAP redirect to {target or 'nowhere'} is not https; "
                                       f"{_PENDING_NOTE}")
            url, redirected = target, True
            continue
        if resp.status == 404:
            if not redirected:
                return done("pending", "rdap.org knows no RDAP server for this TLD; check "
                                       "with the TLD's registry")
            return done("available", "the registry's RDAP server has no record of this domain "
                                     "(not registered; it may still be reserved or premium)")
        data = _json(resp)
        if resp.status == 200 and isinstance(data, dict) and data.get("objectClassName") == "domain":
            return done("taken", "registered: the registry's RDAP server returned its record")
        return done("pending", f"HTTP {resp.status} without a recognizable answer; {_PENDING_NOTE}")
    return done("pending", f"more than {MAX_REDIRECTS} RDAP redirects; {_PENDING_NOTE}")
