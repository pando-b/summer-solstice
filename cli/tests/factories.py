"""Synthetic record bodies for tests. Every name, URL, and number is made up."""

from __future__ import annotations

import copy
from datetime import UTC, datetime, timedelta

T0 = datetime(2026, 1, 5, 12, 0, tzinfo=UTC)


def ts(dt: datetime) -> str:
    return dt.isoformat().replace("+00:00", "Z")


class Clock:
    """Injectable clock: call it for the current time, `advance` to move it."""

    def __init__(self, start: datetime = T0):
        self.now = start

    def __call__(self) -> datetime:
        return self.now

    def advance(self, **kw) -> None:
        self.now += timedelta(**kw)


def demand(**over) -> dict:
    d = {
        "metric": "keyword_volume",
        "value": 1300,
        "unit": "searches_per_month",
        "source": "example-keyword-source",
        "query": "example widget tracker",
        "fetched_at": "2026-01-04T09:30:00Z",
        "url": "https://example.com/keyword/example-widget-tracker",
        "adapter": "example_adapter",
        "method": "api",
    }
    d.update(over)
    return d


def problem(**over) -> dict:
    p = {
        "title": "Example widget owners lose track of restocks",
        "slug": "example-widget-restocks",
        "status": "found",
        "demand": [demand()],
    }
    p.update(over)
    return p


def evidence(**over) -> dict:
    e = {
        "kind": "complaint",
        "url": "https://example.com/thread/123",
        "fetched_at": "2026-01-04T10:00:00Z",
        "adapter": "example_adapter",
        "method": "scrape",
        "summary": "Synthetic complaint about example widgets.",
    }
    e.update(over)
    return e


def product(**over) -> dict:
    p = {
        "name": "Example Widget",
        "slug": "example-widget",
        "status": "qualified",
        "estimated_upfront_spend_usd": 20,
    }
    p.update(over)
    return p


def pro_forma(**over) -> dict:
    p = {
        "price_usd": 19,
        "billing": "monthly",
        "fees_usd_per_customer": 1.5,
        "running_cost_usd_per_customer": 0.5,
        "support_cost_usd_per_customer": 1.0,
        "owner_rate_usd_per_hour": 60,
        "upfront_spend_usd": 30,
        "gross_margin": 0.84,
        "break_even_customers": 2,
        "customers_for_5k_mrr": 264,
        "channel_capacity_customers": 400,
    }
    p.update(over)
    return p


ALL_PASS = {
    k: "pass"
    for k in (
        "demand_score",
        "proof_of_spend",
        "channel",
        "payment_rail",
        "name_available",
        "owner_prereqs",
        "upfront_cash",
        "operator_load",
    )
}


def decision(**over) -> dict:
    d = {
        "verdict": "go",
        "reason": "Synthetic go decision.",
        "checks": dict(ALL_PASS),
        "alive_bar": {"metric": "mrr_usd", "threshold": 200, "description": "MRR at day 60"},
        "kill_window": {"days": 60},
        "pro_forma": pro_forma(),
        "operator_load": {
            "rating": "low",
            "support_volume": "low",
            "compliance_exposure": "none",
            "hands_on": "none",
        },
        "owner_prereqs": [],
    }
    d.update(over)
    return copy.deepcopy(d)


def approval(**over) -> dict:
    a = {
        "subtype": "owner_prereq",
        "title": "Buy example asset license",
        "status": "pending",
        "cost_usd": 0,
    }
    a.update(over)
    return a


def buy_signal(kind: str = "pre_order", at: datetime | None = None, **over) -> dict:
    e = {"type": "buy_signal", "kind": kind, "source": "example-checkout"}
    if at is not None:
        e["at"] = ts(at)
    e.update(over)
    return e
