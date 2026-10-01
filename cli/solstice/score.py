"""`solstice score`, `solstice rank`, and `solstice rubric install` (KTD5, KTD22).

The demand score is::

    score = 100 * sum(weight_c * component_c) * pain_multiplier

with weights, bands, anchors, and gates read from the workspace `rubric.json`
(4.1 or newer). Two kinds of component:

- **Measured** (volume, trend): computed here from the problem's demand
  entries. Each metric has its own bands; an entry scores the highest step it
  reaches. The component takes the best entry, where `low`-confidence entries
  count only when no medium or high entry has a band for that component, and
  then cap at the rubric's `low_confidence_cap`. A caller never supplies them.
- **Rated** (spend, channel_reach, gap, pain): the skill picks one of the
  rubric's anchors and cites at least one demand-entry ID or evidence ID on
  the problem. A spend rating above 0 must cite an entry or evidence record
  whose metric is one of the rubric's `spend_metrics`. The pain anchor maps
  linearly onto the rubric's pain-multiplier range.

The result (value, components, measured basis, ratings with citations, gate
outcomes, rubric version, scored time) is written to the problem's `score`
block and `demand_score` under the workspace lock. Status is never changed:
rejecting is Qualify's call.
"""

from __future__ import annotations

import json
import operator
import os
import re
from importlib import resources
from pathlib import Path

from solstice.state import RecordError, Store, fmt_ts
from solstice.workspace import WorkspaceError

MIN_RUBRIC = (4, 1)
RUBRIC_FILE = "rubric.json"
MEASURED = ("volume", "trend")
RATED = ("spend", "channel_reach", "gap", "pain")
# Rated components that carry a weight; pain is a multiplier instead.
WEIGHTED_RATED = ("spend", "channel_reach", "gap")
INSTALL = "run `solstice rubric install`"
_CONF_RANK = {"low": 0, "medium": 1, "high": 2}
_OPS = {">": operator.gt, ">=": operator.ge, "<": operator.lt, "<=": operator.le,
        "==": operator.eq}

__all__ = ["compute", "install_rubric", "load_rubric", "packaged_rubric", "rank", "score_problem"]


# --- rubric ------------------------------------------------------------------------


def _version(raw) -> tuple[int, ...] | None:
    if not isinstance(raw, str) or not re.fullmatch(r"\d+(\.\d+)*", raw):
        return None
    return tuple(int(p) for p in raw.split("."))


def packaged_rubric() -> dict:
    text = (resources.files("solstice") / "templates" / "workspace" / RUBRIC_FILE).read_text()
    return json.loads(text)


def load_rubric(workspace: Path) -> dict:
    path = Path(workspace) / RUBRIC_FILE
    if not path.is_file():
        raise WorkspaceError(f"{path} is missing; {INSTALL}", details={"path": str(path)})
    try:
        rubric = json.loads(path.read_text())
    except ValueError as exc:
        raise WorkspaceError(f"{path} is not valid JSON ({exc})", details={"path": str(path)})
    version = _version(rubric.get("version")) if isinstance(rubric, dict) else None
    if version is None or version < MIN_RUBRIC:
        found = rubric.get("version") if isinstance(rubric, dict) else None
        raise WorkspaceError(
            f"{path} is version {found!r}; scoring needs rubric "
            f"{'.'.join(map(str, MIN_RUBRIC))} or newer, so {INSTALL}",
            details={"path": str(path), "version": found,
                     "required": ".".join(map(str, MIN_RUBRIC))})
    return rubric


def install_rubric(store: Store) -> dict:
    """Copy the packaged rubric to the workspace root; refuse to overwrite an
    equal or newer one (or one whose version cannot be read)."""
    new = packaged_rubric()
    path = store.workspace / RUBRIC_FILE
    with store.lock():
        old = None
        if path.exists():
            try:
                old = json.loads(path.read_text()).get("version")
            except (ValueError, AttributeError):
                old = None
            old_v = _version(old)
            if old_v is None:
                raise WorkspaceError(f"{path} has no readable version; move it aside to install "
                                     f"rubric {new['version']}", details={"path": str(path)})
            if old_v >= _version(new["version"]):
                raise WorkspaceError(
                    f"{path} is already version {old} (packaged: {new['version']}); "
                    f"not overwriting an equal or newer rubric",
                    details={"path": str(path), "version": old, "packaged": new["version"]})
        tmp = path.with_suffix(".json.tmp")
        tmp.write_text(json.dumps(new, indent=2) + "\n")
        os.replace(tmp, path)
    return {"path": str(path), "version": new["version"], "replaced": old}


def _parts(rubric: dict) -> dict:
    """The pieces scoring reads, or a workspace error naming what is missing."""
    try:
        weights = {c["id"]: float(c["weight"]) for c in rubric["components"]}
        parts = {
            "weights": weights,
            "bands": {k: rubric["measured"][k]["bands"] for k in MEASURED},
            "caps": {k: float(rubric["measured"][k].get("low_confidence_cap", 0.5))
                     for k in MEASURED},
            "anchors": [float(a) for a in rubric["rated"]["anchors"]],
            "spend_metrics": set(rubric["rated"]["spend_metrics"]),
            "pain": (float(rubric["pain_multiplier"]["min"]),
                     float(rubric["pain_multiplier"]["max"])),
            "gates": list(rubric.get("gates") or []),
            "version": rubric["version"],
        }
    except (KeyError, TypeError, ValueError) as exc:
        raise WorkspaceError(f"rubric.json is malformed ({type(exc).__name__}: {exc}); "
                             f"fix it or {INSTALL} over an older copy") from None
    missing = [c for c in (*MEASURED, *WEIGHTED_RATED) if c not in weights]
    if missing:
        raise WorkspaceError(f"rubric.json has no weight for {', '.join(missing)}")
    return parts


# --- measured components -----------------------------------------------------------------


def _band_score(steps: list, value: float) -> float:
    got = 0.0
    for step in steps:
        if value >= float(step["at_least"]):
            got = float(step["score"])
    return got


def _measure(entries: list[dict], bands: dict, cap: float) -> dict:
    scored = []
    for e in entries:
        band = bands.get(e.get("metric"))
        if band is None:
            continue
        conf = e.get("confidence") or "low"  # unknown confidence is treated as the weakest
        scored.append((_band_score(band["steps"], float(e["value"])), _CONF_RANK.get(conf, 0),
                       e.get("id") or "", e, conf))
    strong = [s for s in scored if s[1] > 0]
    pool = strong or scored
    if not pool:
        return {"value": 0.0, "entry_id": None}
    value, _, _, e, conf = max(pool, key=lambda s: (s[0], s[1], s[2]))
    capped = not strong and value > cap
    return {"value": min(value, cap) if not strong else value, "entry_id": e.get("id"),
            "metric": e["metric"], "entry_value": e["value"], "confidence": conf,
            "capped": capped}


# --- rated components ---------------------------------------------------------------------


def _evidence_on(store: Store, problem: dict) -> dict[str, dict]:
    """Evidence on the problem: listed in `evidence_ids`, or pointing back
    through `problem_id`. A listed ID with no record maps to {}."""
    listed = {ev["id"]: ev for ev in store.list("evidence")}
    out = {eid: listed.get(eid, {}) for eid in problem.get("evidence_ids") or []}
    for eid, ev in listed.items():
        if ev.get("problem_id") == problem["id"]:
            out[eid] = ev
    return out


def _check_ratings(ratings, problem: dict, evidence: dict[str, dict], parts: dict) -> list[str]:
    if not isinstance(ratings, dict):
        return ["ratings must be a JSON object {component: {anchor, citations}}"]
    errs = []
    for k in ratings:
        if k in MEASURED:
            errs.append(f"{k} is measured from the problem's demand entries; it cannot be rated")
        elif k not in RATED:
            errs.append(f"unknown component {k!r}; rate {', '.join(RATED)}")
    entries = {e["id"]: e for e in problem.get("demand") or [] if e.get("id")}
    anchors = parts["anchors"]
    for comp in RATED:
        r = ratings.get(comp)
        if r is None:
            errs.append(f"{comp}: rating missing")
            continue
        if not isinstance(r, dict):
            errs.append(f"{comp}: rating must be an object {{anchor, citations}}")
            continue
        extra = sorted(set(r) - {"anchor", "citations"})
        if extra:
            errs.append(f"{comp}: unknown fields {', '.join(extra)}")
        a = r.get("anchor")
        if isinstance(a, bool) or not isinstance(a, (int, float)) or float(a) not in anchors:
            errs.append(f"{comp}: anchor {a!r} is not one of "
                        f"{', '.join(f'{x:g}' for x in anchors)}")
            a = None
        cites = r.get("citations")
        if not isinstance(cites, list) or not cites:
            errs.append(f"{comp}: cite at least one evidence ID or demand-entry ID on the problem")
            continue
        bad = [c for c in cites if not isinstance(c, str)
               or (c not in entries and not evidence.get(c))]
        if bad:
            errs.append(f"{comp}: citations not on this problem: {', '.join(map(str, bad))}")
            continue
        if comp == "spend" and a is not None and a > 0:
            def metric(c: str) -> str | None:
                return (entries.get(c) or evidence.get(c) or {}).get("metric")

            if not any(metric(c) in parts["spend_metrics"] for c in cites):
                errs.append(f"spend {a} needs at least one citation whose metric is a spend type "
                            f"({', '.join(sorted(parts['spend_metrics']))}); engagement and "
                            f"mention counts never justify spend")
    return errs


# --- scoring ---------------------------------------------------------------------------------


def compute(problem: dict, ratings: dict, rubric: dict, *, scored_at: str,
            parts: dict | None = None) -> dict:
    """The score block for a problem whose ratings were already checked.
    `parts` is `_parts(rubric)` when the caller has already parsed it."""
    parts = _parts(rubric) if parts is None else parts
    measured = {k: _measure(problem.get("demand") or [], parts["bands"][k], parts["caps"][k])
                for k in MEASURED}
    components = {k: measured[k]["value"] for k in MEASURED}
    components.update({k: float(ratings[k]["anchor"]) for k in WEIGHTED_RATED})
    lo, hi = parts["pain"]
    pain = lo + float(ratings["pain"]["anchor"]) * (hi - lo)
    weighted = sum(w * components[c] for c, w in parts["weights"].items() if c in components)
    value = round(100 * weighted * pain, 2)

    gates = []
    for g in parts["gates"]:
        field, op = g.get("field"), g.get("op")
        actual = value if field == "score" else components.get(field)
        if actual is None or op not in _OPS:
            raise WorkspaceError(f"rubric gate {g.get('id')!r} has an unknown field or op "
                                 f"({field!r} {op!r})")
        ok = _OPS[op](float(actual), float(g["value"]))
        gates.append({"id": g["id"], "field": field, "op": op, "threshold": g["value"],
                      "actual": actual, "result": "pass" if ok else "fail"})
    return {
        "value": value, "rubric_version": parts["version"], "scored_at": scored_at,
        "components": components, "pain_multiplier": pain, "measured": measured,
        "ratings": {k: {"anchor": ratings[k]["anchor"],
                        "citations": list(dict.fromkeys(ratings[k]["citations"]))}
                    for k in RATED},
        "gates": gates, "gates_passed": all(g["result"] == "pass" for g in gates),
    }


def score_problem(store: Store, problem_id: str, ratings) -> dict:
    rubric = load_rubric(store.workspace)
    parts = _parts(rubric)
    with store.lock():
        problem = store.get("problem", problem_id)
        if problem["status"] != "found":
            raise RecordError(
                f"problem {problem_id} is {problem['status']}; only a found problem (one with "
                f"fetched demand) is scored", details={"problem_id": problem_id,
                                                      "status": problem["status"]})
        errs = _check_ratings(ratings, problem, _evidence_on(store, problem), parts)
        if errs:
            raise RecordError(f"ratings refused: {'; '.join(errs)}",
                              details={"problem_id": problem_id, "errors": errs})
        block = compute(problem, ratings, rubric, scored_at=fmt_ts(store.now()), parts=parts)
        return store.put_locked("problem", {**problem, "score": block,
                                            "demand_score": block["value"]},
                                {"type": "scored", "value": block["value"],
                                 "rubric_version": block["rubric_version"],
                                 "gates_passed": block["gates_passed"]})


def rank(store: Store) -> list[dict]:
    """Scored `found` problems, highest score first (pending_evidence and
    unscored problems are left out)."""
    scored = [p for p in store.list("problem", status="found") if p.get("score")]
    scored.sort(key=lambda p: (-p["score"]["value"], p["id"]))
    rows = []
    for n, p in enumerate(scored, 1):
        s = p["score"]
        row = {"rank": n, "id": p["id"], "title": p["title"], "demand_score": s["value"],
               "gates_passed": s["gates_passed"],
               "gates_failed": [g["id"] for g in s["gates"] if g["result"] == "fail"],
               "components": s["components"], "rubric_version": s["rubric_version"],
               "scored_at": s["scored_at"]}
        for k in ("lens", "shape"):
            if p.get(k):
                row[k] = p[k]
        rows.append(row)
    return rows
