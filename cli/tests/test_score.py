"""Demand score, rank, and rubric install (R3, R4, R5; KTD5, KTD22).

Volume and trend are measured from the problem's demand entries through the
rubric's bands; spend, channel reach, gap, and pain are anchored ratings that
must cite evidence or demand entries on the problem. Every number here is
synthetic."""

import json

import factories as f
import pytest

from solstice import score
from solstice.__main__ import main
from solstice.errors import SolsticeError
from solstice.state import new_ulid


def _entry(metric, value, *, unit="count", confidence="high", adapter="example_adapter", **over):
    return {**f.demand(metric=metric, value=value, unit=unit, adapter=adapter,
                       confidence=confidence), "id": new_ulid(), **over}


def _problem(store, entries, *, evidence_ids=None, status="found", **over):
    body = f.problem(demand=entries, **over)
    if evidence_ids:
        body["evidence_ids"] = evidence_ids
    body["status"] = status
    if status == "pending_evidence":
        body.pop("demand")
        body["pending_fetch"] = {"adapter": "example_adapter", "error": "timed out",
                                 "attempted_at": "2026-01-04T09:30:00Z"}
    return store.create_managed("problem", body)


def _rating(anchor, *cites):
    return {"anchor": anchor, "citations": list(cites)}


def _ratings(cite, *, spend=None, reach=0.5, gap=0.5, pain=0.5, spend_cite=None):
    return {"spend": _rating(0 if spend is None else spend, spend_cite or cite),
            "channel_reach": _rating(reach, cite), "gap": _rating(gap, cite),
            "pain": _rating(pain, cite)}


@pytest.fixture
def rubric(store):
    score.install_rubric(store)
    return json.loads((store.workspace / "rubric.json").read_text())


@pytest.fixture
def market(store, rubric):
    """A found problem with a keyword volume, a trend, an MRR entry, and an HN count."""
    kw = _entry("keyword_volume", 1200, unit="searches_per_month")
    trend = _entry("trend_change_pct", 20, unit="percent")
    mrr = _entry("mrr_usd", 4200, unit="usd_per_month", confidence="medium", adapter="trustmrr")
    hn = _entry("hn_stories_365d", 40, unit="stories", confidence="medium", adapter="hn_algolia")
    ev = store.create("evidence", f.evidence())
    p = _problem(store, [kw, trend, mrr, hn], evidence_ids=[ev["id"]])
    return {"problem": p, "kw": kw, "trend": trend, "mrr": mrr, "hn": hn, "ev": ev}


def _err(exc_info) -> SolsticeError:
    return exc_info.value


# --- determinism, gates ----------------------------------------------------------


def test_same_inputs_and_rubric_version_give_identical_score(store, market, clock):
    m = market
    r = _ratings(m["ev"]["id"], spend=0.75, spend_cite=m["mrr"]["id"])
    first = score.score_problem(store, m["problem"]["id"], r)["score"]
    clock.advance(hours=1)
    second = score.score_problem(store, m["problem"]["id"], r)["score"]
    strip = lambda s: {k: v for k, v in s.items() if k != "scored_at"}
    assert strip(first) == strip(second)
    assert first["scored_at"] != second["scored_at"]


def test_low_spend_with_high_total_is_gated_out_on_spend_floor(store, market):
    m = market
    r = _ratings(m["ev"]["id"], spend=0.25, spend_cite=m["mrr"]["id"], reach=1, gap=1, pain=1)
    s = score.score_problem(store, m["problem"]["id"], r)["score"]
    assert s["value"] >= 55
    gates = {g["id"]: g for g in s["gates"]}
    assert gates["spend_floor"]["result"] == "fail" and gates["spend_floor"]["actual"] == 0.25
    assert gates["score_floor"]["result"] == "pass"
    assert s["gates_passed"] is False


def test_score_is_written_with_demand_score_and_status_unchanged(store, market):
    m = market
    r = _ratings(m["ev"]["id"], spend=0.75, spend_cite=m["mrr"]["id"])
    out = score.score_problem(store, m["problem"]["id"], r)
    rec = store.get("problem", m["problem"]["id"])
    assert rec["status"] == "found"
    assert rec["demand_score"] == out["score"]["value"] == rec["score"]["value"]
    assert rec["score"]["rubric_version"] == "4.1"
    assert rec["score"]["ratings"]["spend"] == {"anchor": 0.75, "citations": [m["mrr"]["id"]]}
    assert set(rec["score"]["components"]) == {"volume", "trend", "spend", "channel_reach", "gap"}
    assert store.events("problem", m["problem"]["id"])[-1]["type"] == "scored"


def test_formula_follows_rubric_weights_and_pain_range(store, market, rubric):
    m = market
    r = _ratings(m["ev"]["id"], spend=0.75, spend_cite=m["mrr"]["id"], reach=0.5, gap=0.25,
                 pain=1)
    s = score.score_problem(store, m["problem"]["id"], r)["score"]
    c = s["components"]
    w = {x["id"]: x["weight"] for x in rubric["components"]}
    assert s["pain_multiplier"] == rubric["pain_multiplier"]["max"]
    expected = 100 * sum(w[k] * c[k] for k in w) * s["pain_multiplier"]
    assert s["value"] == round(expected, 2)
    s0 = score.score_problem(store, m["problem"]["id"], {**r, "pain": _rating(0, m["ev"]["id"])})
    assert s0["score"]["pain_multiplier"] == rubric["pain_multiplier"]["min"]


# --- rating refusals ------------------------------------------------------------------


@pytest.mark.parametrize("bad", [
    {"anchor": 0.5, "citations": []},
    {"anchor": 0.5},
])
def test_uncited_rating_is_refused(store, market, bad):
    m = market
    r = {**_ratings(m["ev"]["id"]), "gap": bad}
    with pytest.raises(SolsticeError) as ei:
        score.score_problem(store, m["problem"]["id"], r)
    assert _err(ei).kind == "invalid_record"
    assert "score" not in store.get("problem", m["problem"]["id"])


def test_citation_not_on_the_problem_is_refused(store, market):
    m = market
    stranger = store.create("evidence", f.evidence(url="https://example.com/thread/999"))
    for cite in (new_ulid(), stranger["id"]):
        r = {**_ratings(m["ev"]["id"]), "gap": _rating(0.5, cite)}
        with pytest.raises(SolsticeError) as ei:
            score.score_problem(store, m["problem"]["id"], r)
        assert _err(ei).kind == "invalid_record"
        assert cite in _err(ei).message


def test_evidence_linked_by_problem_id_counts_as_on_the_problem(store, market):
    m = market
    linked = store.create("evidence", f.evidence(url="https://example.com/thread/555",
                                                 problem_id=m["problem"]["id"]))
    r = {**_ratings(m["ev"]["id"]), "pain": _rating(0.75, linked["id"])}
    assert score.score_problem(store, m["problem"]["id"], r)["score"]["ratings"]["pain"][
        "citations"] == [linked["id"]]


@pytest.mark.parametrize("anchor", [0.3, 0.2, 1.5, -0.25, "0.5", None, True])
def test_rating_off_the_five_anchors_is_refused(store, market, anchor):
    m = market
    r = {**_ratings(m["ev"]["id"]), "channel_reach": _rating(anchor, m["ev"]["id"])}
    with pytest.raises(SolsticeError) as ei:
        score.score_problem(store, m["problem"]["id"], r)
    assert _err(ei).kind == "invalid_record"


@pytest.mark.parametrize("ratings", [
    "not an object",
    {"spend": {"anchor": 0, "citations": ["x"]}},  # missing components
])
def test_malformed_ratings_are_refused(store, market, ratings):
    with pytest.raises(SolsticeError) as ei:
        score.score_problem(store, market["problem"]["id"], ratings)
    assert _err(ei).kind == "invalid_record"


@pytest.mark.parametrize("extra", ["volume", "trend", "bonus"])
def test_caller_cannot_supply_a_measured_or_unknown_component(store, market, extra):
    m = market
    r = {**_ratings(m["ev"]["id"]), extra: _rating(1, m["kw"]["id"])}
    with pytest.raises(SolsticeError) as ei:
        score.score_problem(store, m["problem"]["id"], r)
    assert _err(ei).kind == "invalid_record" and extra in _err(ei).message


def test_spend_citing_only_a_mention_count_is_refused_and_mrr_is_accepted(store, market):
    m = market
    r = _ratings(m["ev"]["id"], spend=0.75, spend_cite=m["hn"]["id"])
    with pytest.raises(SolsticeError) as ei:
        score.score_problem(store, m["problem"]["id"], r)
    assert _err(ei).kind == "invalid_record" and "spend" in _err(ei).message
    ok = _ratings(m["ev"]["id"], spend=0.75, spend_cite=m["mrr"]["id"])
    assert score.score_problem(store, m["problem"]["id"], ok)["score"]["components"]["spend"] == 0.75


def test_spend_above_zero_accepts_spend_typed_evidence(store, rubric):
    rev = store.create("evidence", f.evidence(url="https://example.com/startup/abc",
                                              metric="mrr_usd", value=900, unit="usd"))
    kw = _entry("keyword_volume", 400, unit="searches_per_month")
    p = _problem(store, [kw], evidence_ids=[rev["id"]])
    r = _ratings(kw["id"], spend=0.5, spend_cite=rev["id"])
    assert score.score_problem(store, p["id"], r)["score"]["components"]["spend"] == 0.5


def test_spend_zero_needs_a_citation_but_not_a_spend_metric(store, market):
    m = market
    r = _ratings(m["ev"]["id"], spend=0, spend_cite=m["hn"]["id"])
    assert score.score_problem(store, m["problem"]["id"], r)["score"]["components"]["spend"] == 0


# --- measured components ----------------------------------------------------------------


def _band(rubric, component, metric, value):
    score_for = 0.0
    for step in rubric["measured"][component]["bands"][metric]["steps"]:
        if value >= step["at_least"]:
            score_for = step["score"]
    return score_for


def test_volume_prefers_search_volume_over_a_large_low_confidence_engagement_sum(store, rubric):
    kw = _entry("keyword_volume", 300, unit="searches_per_month")
    social = _entry("reddit_engagement_sum", 10_000_000, unit="engagement", confidence="low",
                    adapter="scrapecreators")
    p = _problem(store, [kw, social])
    s = score.score_problem(store, p["id"], _ratings(kw["id"]))["score"]
    vol = s["measured"]["volume"]
    assert vol["entry_id"] == kw["id"]
    assert s["components"]["volume"] == _band(rubric, "volume", "keyword_volume", 300) > 0


def test_only_low_confidence_entry_caps_volume_at_half(store, rubric):
    social = _entry("reddit_engagement_sum", 10_000_000, unit="engagement", confidence="low",
                    adapter="scrapecreators")
    assert _band(rubric, "volume", "reddit_engagement_sum", 10_000_000) > 0.5
    p = _problem(store, [social])
    s = score.score_problem(store, p["id"], _ratings(social["id"]))["score"]
    assert s["components"]["volume"] == 0.5
    assert s["measured"]["volume"]["capped"] is True
    assert s["measured"]["volume"]["entry_id"] == social["id"]


def test_keyword_volume_1200_lands_in_the_rubric_band(store, rubric):
    kw = _entry("keyword_volume", 1200, unit="searches_per_month")
    p = _problem(store, [kw])
    s = score.score_problem(store, p["id"], _ratings(kw["id"]))["score"]
    assert s["components"]["volume"] == _band(rubric, "volume", "keyword_volume", 1200)
    assert s["measured"]["volume"] == {"value": s["components"]["volume"], "entry_id": kw["id"],
                                       "metric": "keyword_volume", "entry_value": 1200,
                                       "confidence": "high", "capped": False}


def test_wporg_install_floor_alone_scores_and_is_cited(store, rubric):
    installs = _entry("active_installs_top", 10_000, unit="installs", adapter="wporg",
                      note="bucket floor")
    p = _problem(store, [installs])
    s = score.score_problem(store, p["id"], _ratings(installs["id"]))["score"]
    assert s["measured"]["volume"]["entry_id"] == installs["id"]
    assert s["components"]["volume"] == _band(rubric, "volume", "active_installs_top", 10_000) > 0


def test_entry_without_a_band_gives_zero_with_no_basis(store, rubric):
    odd = _entry("plugin_count", 300, unit="plugins")
    p = _problem(store, [odd])
    s = score.score_problem(store, p["id"], _ratings(odd["id"]))["score"]
    assert s["components"]["volume"] == 0 and s["components"]["trend"] == 0
    assert s["measured"]["volume"]["entry_id"] is None
    assert s["measured"]["trend"]["entry_id"] is None


def test_trend_comes_from_the_trend_band(store, rubric):
    t = _entry("trend_change_pct", -50, unit="percent")
    p = _problem(store, [t])
    s = score.score_problem(store, p["id"], _ratings(t["id"]))["score"]
    assert s["components"]["trend"] == _band(rubric, "trend", "trend_change_pct", -50) == 0
    t2 = _entry("trend_change_pct", 45, unit="percent")
    p2 = _problem(store, [t2])
    s2 = score.score_problem(store, p2["id"], _ratings(t2["id"]))["score"]
    assert s2["components"]["trend"] == _band(rubric, "trend", "trend_change_pct", 45) > 0.5


def test_pending_evidence_problem_is_not_scored(store, rubric):
    p = _problem(store, [], status="pending_evidence")
    with pytest.raises(SolsticeError) as ei:
        score.score_problem(store, p["id"], _ratings(new_ulid()))
    assert _err(ei).kind == "invalid_record" and "pending_evidence" in _err(ei).message


# --- rubric -----------------------------------------------------------------------------


def test_score_without_a_rubric_names_rubric_install(store):
    kw = _entry("keyword_volume", 500, unit="searches_per_month")
    p = _problem(store, [kw])
    with pytest.raises(SolsticeError) as ei:
        score.score_problem(store, p["id"], _ratings(kw["id"]))
    assert _err(ei).kind == "workspace" and "solstice rubric install" in _err(ei).message


def test_score_with_an_old_rubric_names_rubric_install(store):
    (store.workspace / "rubric.json").write_text(json.dumps({"version": "4.0"}))
    kw = _entry("keyword_volume", 500, unit="searches_per_month")
    p = _problem(store, [kw])
    with pytest.raises(SolsticeError) as ei:
        score.score_problem(store, p["id"], _ratings(kw["id"]))
    assert _err(ei).kind == "workspace" and "solstice rubric install" in _err(ei).message


def test_rubric_install_replaces_older_and_refuses_equal_or_newer(store):
    (store.workspace / "rubric.json").write_text(json.dumps({"version": "4.0"}))
    out = score.install_rubric(store)
    assert out["version"] == "4.1" and out["replaced"] == "4.0"
    assert json.loads((store.workspace / "rubric.json").read_text())["version"] == "4.1"
    with pytest.raises(SolsticeError) as ei:
        score.install_rubric(store)
    assert _err(ei).kind == "workspace"
    (store.workspace / "rubric.json").write_text(json.dumps({"version": "4.10"}))
    with pytest.raises(SolsticeError):
        score.install_rubric(store)
    assert json.loads((store.workspace / "rubric.json").read_text())["version"] == "4.10"


def test_packaged_rubric_is_4_1_with_bands_anchors_and_spend_metrics():
    r = score.packaged_rubric()
    assert r["version"] == "4.1"
    assert set(r["rated"]["anchors"]) == {0, 0.25, 0.5, 0.75, 1}
    assert {"mrr_usd", "revenue_30d_usd"} <= set(r["rated"]["spend_metrics"])
    assert "hn_stories_365d" not in r["rated"]["spend_metrics"]
    assert {"keyword_volume", "active_installs_top"} <= set(r["measured"]["volume"]["bands"])
    assert "trend_change_pct" in r["measured"]["trend"]["bands"]
    assert r["measured"]["volume"]["low_confidence_cap"] == 0.5


def test_edited_rubric_changes_score_only_through_score_and_stamps_version(store, market):
    m = market
    r = _ratings(m["ev"]["id"], spend=0.75, spend_cite=m["mrr"]["id"])
    before = score.score_problem(store, m["problem"]["id"], r)["score"]
    path = store.workspace / "rubric.json"
    rub = json.loads(path.read_text())
    rub["version"] = "4.2"
    for c in rub["components"]:
        c["weight"] = {"volume": 0.10, "gap": 0.30}.get(c["id"], c["weight"])
    path.write_text(json.dumps(rub))
    assert store.get("problem", m["problem"]["id"])["score"] == before  # nothing moves by itself
    after = score.score_problem(store, m["problem"]["id"], r)["score"]
    assert after["rubric_version"] == "4.2" and after["value"] != before["value"]
    with pytest.raises(SolsticeError) as ei:
        store.update("problem", m["problem"]["id"], {"demand_score": 99})
    assert _err(ei).kind == "invalid_record"
    with pytest.raises(SolsticeError):
        store.update("problem", m["problem"]["id"], {"score": before})


# --- rank --------------------------------------------------------------------------------


def test_rank_lists_scored_found_problems_highest_first(store, rubric):
    rows = []
    for vol in (300, 6000):
        kw = _entry("keyword_volume", vol, unit="searches_per_month")
        p = _problem(store, [kw], title=f"Synthetic problem {vol}")
        score.score_problem(store, p["id"], _ratings(kw["id"]))
        rows.append(p["id"])
    _problem(store, [], status="pending_evidence")
    _problem(store, [_entry("keyword_volume", 9000, unit="searches_per_month")])  # unscored
    ranked = score.rank(store)
    assert [r["id"] for r in ranked] == [rows[1], rows[0]]
    assert ranked[0]["demand_score"] > ranked[1]["demand_score"]
    assert ranked[0]["rank"] == 1 and ranked[0]["rubric_version"] == "4.1"
    assert set(ranked[0]) >= {"id", "title", "demand_score", "gates_passed", "scored_at"}


# --- CLI ---------------------------------------------------------------------------------


@pytest.fixture
def cli(ws, monkeypatch, capsys, tmp_path):
    monkeypatch.setenv("SOLSTICE_WORKSPACE", str(ws))

    def run(*argv, body=None):
        if body is not None:
            p = tmp_path / "ratings.json"
            p.write_text(json.dumps(body))
            argv = [a if a != "@body" else str(p) for a in argv]
        code = main(list(argv))
        cap = capsys.readouterr()
        return code, cap.out, cap.err

    return run


def test_cli_score_rank_and_rubric_install(cli, store):
    code, out, err = cli("rubric", "install")
    assert code == 0 and json.loads(out)["version"] == "4.1"
    code, out, err = cli("rubric", "install")
    assert code == 2 and json.loads(err)["error"]["kind"] == "workspace"

    kw = _entry("keyword_volume", 1200, unit="searches_per_month")
    p = _problem(store, [kw])
    code, out, err = cli("score", p["id"], "--ratings", "@body", body=_ratings(kw["id"]))
    assert code == 0, err
    assert json.loads(out)["score"]["rubric_version"] == "4.1"

    code, out, err = cli("score", p["id"], "--ratings", "@body",
                         body={**_ratings(kw["id"]), "gap": _rating(0.5)})
    assert code == 1 and out == ""
    assert json.loads(err)["error"]["kind"] == "invalid_record"

    code, out, _ = cli("rank")
    assert code == 0 and [r["id"] for r in json.loads(out)] == [p["id"]]


def test_cli_score_without_rubric_is_workspace_envelope(cli, store):
    kw = _entry("keyword_volume", 1200, unit="searches_per_month")
    p = _problem(store, [kw])
    code, out, err = cli("score", p["id"], "--ratings", "@body", body=_ratings(kw["id"]))
    e = json.loads(err)["error"]
    assert out == ""
    assert code == 2 and e["kind"] == "workspace" and "solstice rubric install" in e["message"]
