"""Demand adapters (KTD4). REGISTRY order is the order `demand sources`
lists them: keyless first, then paid, then evidence-only and manual."""

from __future__ import annotations

from solstice.adapters.base import Adapter
from solstice.adapters.dataforseo_trends import DataForSEOTrends
from solstice.adapters.dataforseo_volume import DataForSEOVolume
from solstice.adapters.hn_algolia import HackerNews
from solstice.adapters.last30days import Last30Days
from solstice.adapters.manual import Manual
from solstice.adapters.scrapecreators import ScrapeCreators
from solstice.adapters.trustmrr import TrustMRR
from solstice.adapters.wporg import WordPressOrg

REGISTRY: dict[str, Adapter] = {a.name: a for a in (
    WordPressOrg(), HackerNews(), DataForSEOTrends(), DataForSEOVolume(), TrustMRR(),
    ScrapeCreators(), Last30Days(), Manual())}
