"""The `last30days` research engine, saved as evidence.

The engine runs locally on the user's own setup and may spend the user's own
paid-backend credits, so each invocation is reserved against the caps at an
estimated `adapters.last30days.usd_per_run`. Its items are stored as evidence
records with their engagement; it never yields a demand number.

The command comes from workspace config `adapters.last30days.command` (a
list, or a string split like a shell would). Without one, the CLI looks for
the skill's engine under the user's Claude skills directory. The CLI appends
`<query> --emit=json --json-profile=raw`.
"""

from __future__ import annotations

import json
import shlex
import shutil
from functools import cache
from pathlib import Path

from solstice.adapters.base import Adapter, Cost, Ctx, FetchFailed, Params, Result, num

ENGINE = Path("scripts") / "last30days.py"
TIMEOUT_S = 600.0


def discover(home: Path | None) -> list[str] | None:
    """The engine under the user's skills, else under an installed plugin."""
    argv = _discover(home)
    return list(argv) if argv else None


@cache
def _discover(home: Path | None) -> tuple[str, str] | None:
    """`discover`, cached per home so one CLI process resolves it once."""
    if home is None:
        return None
    found = home / ".claude" / "skills" / "last30days" / ENGINE
    if not found.is_file():
        plugins = home / ".claude" / "plugins"
        hits = (sorted(c for c in plugins.glob(f"**/skills/last30days/{ENGINE.as_posix()}")
                       if c.is_file()) if plugins.is_dir() else [])
        if not hits:
            return None
        found = hits[0]
    return shutil.which("python3") or "python3", str(found)


def command(cfg: dict, home: Path | None) -> list[str] | None:
    raw = cfg.get("command")
    if isinstance(raw, str) and raw.strip():
        return shlex.split(raw)
    if isinstance(raw, list) and raw and all(isinstance(a, str) for a in raw):
        return list(raw)
    return discover(home)


class Last30Days(Adapter):
    name = "last30days"
    label = "last30days"
    method = "scrape"
    confidence = "low"
    cost = Cost("per_run", "usd_per_run", 0.10, estimated=True)
    evidence_only = True

    def unavailable_reason(self, cfg: dict, home: Path | None) -> str | None:
        if command(cfg, home) is None:
            return "not installed: set adapters.last30days.command in workspace config"
        return None

    def fetch(self, params: Params, ctx: Ctx) -> Result:
        argv = [*command(ctx.cfg, ctx.home), params.queries[0], "--emit=json",
                "--json-profile=raw"]
        code, stdout, stderr = ctx.runner(argv, TIMEOUT_S)
        if code != 0:
            tail = (stderr or "").strip().splitlines()[-1:] or [""]
            raise FetchFailed(f"last30days exited {code}: {tail[0][:300]}", code=code)
        try:
            data = json.loads(stdout)
        except ValueError:
            raise FetchFailed("last30days output is not JSON") from None
        evidence = []
        for source, items in _items(data):
            for it in items:
                url = it.get("url") if isinstance(it, dict) else None
                if not isinstance(url, str) or not url.startswith(("http://", "https://")):
                    continue
                eng = {k: v for k, v in (it.get("engagement") or {}).items()
                       if num(v) is not None and not isinstance(v, str)}
                evidence.append(self.evidence(
                    ctx, kind="social_mention", url=url, summary=it.get("title"),
                    metric="engagement", value=sum(eng.values()), unit="engagement",
                    data={"source": source, "query": params.queries[0], **eng}))
        if not evidence:
            raise FetchFailed("last30days returned no items with URLs")
        return Result(evidence=evidence)


def _items(data) -> list[tuple[str, list]]:
    if not isinstance(data, dict):
        return []
    by_source = data.get("items_by_source")
    if isinstance(by_source, dict):
        return [(str(k), v) for k, v in by_source.items() if isinstance(v, list)]
    if isinstance(data.get("items"), list):
        return [("items", data["items"])]
    return []
