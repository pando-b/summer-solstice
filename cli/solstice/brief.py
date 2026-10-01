"""The Build Brief: a go decision's `build_brief` block, rendered as a
compound-engineering settled-decisions brief for `ce-brainstorm` (R7, KTD9).

The brief carries a direction, settled decisions, open areas, and the IDs of
the evidence records and demand entries behind the go. Each settled entry
needs the decision, its provenance class (`user-directed` or
`user-approved`), the rejected alternative, and a one-line reason. An entry
that cannot name a rejected alternative is not settled: the validator
refuses it, and the skill demotes it to an open area.

Every string in the brief is skill-written. `render` refuses a brief that
repeats a stretch of a cited evidence record's fetched quote, so fetched
text (and any instruction inside it) never reaches the build.
"""

from __future__ import annotations

import re

from solstice.errors import SolsticeError

PROVENANCE = ("user-directed", "user-approved")
STEM = "session-settled:"
_PLACEHOLDERS = {"", "none", "n/a", "na", "-", "--", "nothing", "no alternative", "tbd"}
QUOTE_WINDOW = 40  # characters of a fetched quote that may not appear in the brief
STANDING_LINE = ("If you find evidence that a settled decision cannot work, report it as a "
                 "conflict; do not suppress it.")


class BriefError(SolsticeError):
    kind = "invalid_record"


def validate_brief(b: dict) -> list[str]:
    """Rules the schema cannot express. The schema already requires each field."""
    errs = []
    for i, entry in enumerate(b.get("settled") or []):
        alt = entry.get("rejected_alternative")
        if not isinstance(alt, str) or alt.strip().lower().rstrip(".") in _PLACEHOLDERS:
            errs.append(f"decision build_brief/settled/{i}: a settled entry needs a real rejected "
                        f"alternative (got {alt!r}); without one, move it to open_areas")
    return errs


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def _strings(value):
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for v in value.values():
            yield from _strings(v)
    elif isinstance(value, list):
        for v in value:
            yield from _strings(v)


def _quotes(ev: dict) -> list[str]:
    data = ev.get("data") or {}
    return [q for q in _strings(data.get("quote")) if len(_norm(q)) >= QUOTE_WINDOW]


def _leaks(text: str, quote: str) -> bool:
    t, q = _norm(text), _norm(quote)
    if len(t) < QUOTE_WINDOW:
        return False
    return any(t[i:i + QUOTE_WINDOW] in q for i in range(len(t) - QUOTE_WINDOW + 1))


def _fields(b: dict, readiness: dict | None):
    yield from _strings(b.get("direction"))
    for entry in b.get("settled") or []:
        yield from _strings({k: v for k, v in entry.items() if k != "provenance"})
    yield from _strings(b.get("open_areas"))
    yield from _strings((readiness or {}).get("summary"))
    yield from _strings((readiness or {}).get("blockers"))


def _resolve(store, dec: dict, b: dict) -> list[dict]:
    from solstice.state import RecordError

    evidence = []
    for eid in b.get("evidence_ids") or []:
        try:
            evidence.append(store.get("evidence", eid))
        except RecordError as exc:
            if exc.kind == "not_found":
                raise RecordError(f"build_brief evidence {eid} does not resolve", kind="not_found",
                                  details={"entity": "evidence", "id": eid}) from None
            raise
    entry_ids = b.get("demand_entry_ids") or []
    if entry_ids:
        known = set()
        if dec.get("problem_id"):
            prob = store.get("problem", dec["problem_id"])
            known = {e.get("id") for e in prob.get("demand") or []}
        missing = [d for d in entry_ids if d not in known]
        if missing:
            raise RecordError(
                f"build_brief demand entries {', '.join(missing)} are not on the decision's problem",
                kind="not_found", details={"entity": "demand_entry", "ids": missing,
                                           "problem_id": dec.get("problem_id")})
    return evidence


def render(store, decision_id: str) -> str:
    dec = store.get("decision", decision_id)
    b = dec.get("build_brief")
    if dec["verdict"] != "go" or not b:
        raise BriefError(f"decision {decision_id} has no Build Brief (verdict {dec['verdict']}); "
                         f"only a go decision carries one", details={"id": decision_id})
    readiness = dec.get("agent_readiness")
    evidence = _resolve(store, dec, b)
    for ev in evidence:
        for quote in _quotes(ev):
            for text in _fields(b, readiness):
                if _leaks(text, quote):
                    raise BriefError(
                        f"the Build Brief repeats fetched text from evidence {ev['id']}; rewrite "
                        f"that field as a summary in your own words",
                        details={"id": decision_id, "evidence_id": ev["id"]})

    title = b.get("title") or dec.get("reason")
    lines = [f"# Build Brief: {title}", "", f"Decision: {decision_id}", "",
             "## Direction", "", b["direction"].strip(), "", "## Settled decisions", ""]
    for s in b["settled"]:
        lines.append(f"- {s['decision'].strip()} ({STEM} {s['provenance']} — chosen over "
                     f"{s['rejected_alternative'].strip()}: {s['reason'].strip()})")
    lines += ["", "## Open areas", ""]
    lines += [f"- {a.strip()}" for a in b.get("open_areas") or []] or ["- none"]
    if readiness:
        surfaces = ", ".join(readiness.get("surfaces") or []) or "none"
        can = "yes" if readiness["core_job_without_human"] else "no"
        lines += ["", "## Agent readiness", "",
                  f"- Agent completes the core job without a human in the browser: {can}",
                  f"- Agent surfaces: {surfaces}",
                  f"- {readiness['summary'].strip()}"]
        lines += [f"- Blocker: {x.strip()}" for x in readiness.get("blockers") or []]
    ids = [f"- evidence {e}" for e in b.get("evidence_ids") or []]
    ids += [f"- demand entry {d}" for d in b.get("demand_entry_ids") or []]
    if ids:
        src = f" (problem {dec['problem_id']})" if dec.get("problem_id") else ""
        lines += ["", f"## Evidence{src}", "", *ids]
    lines += ["", STANDING_LINE, ""]
    return "\n".join(lines)
