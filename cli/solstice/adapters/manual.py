"""A human-entered number with its URL, for sources with no API (for
example marketplace dashboards or ranks). Always `manual` and `low`
confidence; it still enters only through `demand fetch` (R5)."""

from __future__ import annotations

from solstice.adapters.base import Adapter, Ctx, Params, Result
from solstice.errors import UsageError


class Manual(Adapter):
    name = "manual"
    label = "manual entry"
    method = "manual"
    confidence = "low"

    def check(self, params: Params) -> None:
        super().check(params)
        need = [f"--{n}" for n in ("metric", "unit", "url", "source")
                if not (getattr(params, n) or "").strip()]
        if params.value is None:
            need.append("--value")
        if need:
            raise UsageError(f"manual entry needs {', '.join(need)}")
        if not params.url.startswith(("http://", "https://")) or any(c.isspace() for c in params.url):
            raise UsageError("--url must be an http(s) URL without spaces")

    def fetch(self, params: Params, ctx: Ctx) -> Result:
        return Result(entries=[self.entry(
            ctx, metric=params.metric, value=params.value, unit=params.unit,
            query=params.queries[0], url=params.url, source=params.source)])
