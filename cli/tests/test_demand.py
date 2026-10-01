"""Demand adapters, fetch orchestration, run spend ledger, and budgets
(R3, R5, R16, R22, R26). Every response replayed here is a hand-built
synthetic fixture; no test touches the network. Fake keys are built at
runtime."""

import json
import multiprocessing
import re
from pathlib import Path

import pytest

import factories as f
from solstice import demand
from solstice.__main__ import main
from solstice.adapters import REGISTRY
from solstice.adapters.base import Request, Response, TransportError
from solstice.errors import SolsticeError

FIX = Path(__file__).parent / "fixtures" / "adapters"
ULID_RE = re.compile(r"^[0-9A-HJKMNP-TV-Z]{26}$")


def _fake(name: str) -> str:
    return "fake" + "-" + name.lower().replace("_", "-") + "-" + "0123456789abcdef"


KEYS = {k: _fake(k) for k in ("DATAFORSEO_LOGIN", "DATAFORSEO_PASSWORD", "TRUSTMRR_API_KEY",
                             "SCRAPECREATORS_API_KEY")}


def fixture(name: str) -> Response:
    data = json.loads((FIX / name).read_text())
    return Response(status=data["status"], headers=data["headers"],
                    body=json.dumps(data["body"]).encode())


def status_only(code: int, headers=None) -> Response:
    return Response(status=code, headers=headers or {}, body=b"{}")


class FakeTransport:
    def __init__(self, *responses):
        self.queue = list(responses)
        self.requests: list[Request] = []

    def __call__(self, req: Request) -> Response:
        self.requests.append(req)
        item = self.queue.pop(0)
        if isinstance(item, Exception):
            raise item
        return item


class FakeRunner:
    def __init__(self, stdout: str = "", code: int = 0):
        self.stdout, self.code, self.calls = stdout, code, []

    def __call__(self, argv, timeout):
        self.calls.append(argv)
        return self.code, self.stdout, ""


def _config(ws, *, monthly=50, per_run=5, adapters=None):
    cfg = ws / ".solstice" / "config.yaml"
    cfg.parent.mkdir(parents=True, exist_ok=True)
    cfg.write_text(json.dumps({  # JSON is valid YAML
        "workspace_root": ".",
        "budgets": {"factory_monthly_cap_usd": monthly, "per_run_cap_usd": per_run,
                    "launch_spend_limit_usd": 50},
        "adapters": adapters or {},
    }))


@pytest.fixture
def deps_for(tmp_path, clock):
    def make(*responses, env=KEYS, runner=None):
        t = FakeTransport(*responses)
        d = demand.Deps(transport=t, runner=runner or FakeRunner(), env=dict(env), now=clock,
                        clock=lambda: 1_000_000.0, sleep=lambda s: None,
                        home=tmp_path / "home")
        return d, t

    return make


@pytest.fixture
def cfg(ws):
    _config(ws)
    return ws


def q(*queries, **kw) -> demand.Params:
    return demand.Params(queries=list(queries), **kw)


def _err(exc_info) -> SolsticeError:
    return exc_info.value


# --- adapters parse recorded responses into the normalized shape -----------


def _entries_ok(entries, adapter, method, confidence):
    assert entries
    for e in entries:
        assert e["adapter"] == adapter and e["method"] == method
        assert e["confidence"] == confidence
        assert ULID_RE.match(e["id"])
        assert e["url"].startswith("https://")
        assert e["fetched_at"] == f.ts(f.T0)


def test_wporg_installs_are_bucket_floors_with_the_bucket_noted(store, cfg, deps_for):
    deps, t = deps_for(fixture("wporg_query_plugins.json"), env={})
    out = demand.fetch(store, "wporg", q("example widget"), deps=deps)
    _entries_ok(out["entries"], "wporg", "api", "high")
    by = {e["metric"]: e for e in out["entries"]}
    assert by["active_installs_top"]["value"] == 10000
    assert "lower bound" in by["active_installs_top"]["note"]
    assert by["active_installs_sum"]["value"] == 12000  # "2,000+" floors to 2000
    assert by["plugin_count"]["value"] == 64
    assert "request%5Bsearch%5D=example+widget" in t.requests[0].url
    assert len(out["evidence_ids"]) == 3
    ev = store.get("evidence", out["evidence_ids"][1])
    assert ev["url"] == "https://wordpress.org/plugins/example-widget-alerts/"
    assert ev["value"] == 2000 and ev["data"]["active_installs_bucket"] == "2,000+"


def test_hn_counts_stories_and_engagement_medium_confidence(store, cfg, deps_for):
    deps, t = deps_for(fixture("hn_search.json"), env={})
    out = demand.fetch(store, "hn_algolia", q("widget restock"), deps=deps)
    _entries_ok(out["entries"], "hn_algolia", "api", "medium")
    by = {e["metric"]: e["value"] for e in out["entries"]}
    assert by == {"hn_stories_365d": 137, "hn_points_top": 100, "hn_comments_top": 44}
    assert "numericFilters=created_at_i%3E" in t.requests[0].url
    assert store.get("evidence", out["evidence_ids"][0])["url"] == \
        "https://news.ycombinator.com/item?id=1000001"


def test_dataforseo_volume_three_queries_is_one_task_three_entries(store, cfg, deps_for):
    deps, t = deps_for(fixture("dataforseo_volume_ok.json"))
    out = demand.fetch(store, "dataforseo_volume",
                       q("example widget tracker", "example widget restock", "example widget alerts"),
                       deps=deps)
    assert len(t.requests) == 1
    body = json.loads(t.requests[0].body)
    assert len(body) == 1 and len(body[0]["keywords"]) == 3
    assert t.requests[0].headers["Authorization"].startswith("Basic ")
    _entries_ok(out["entries"], "dataforseo_volume", "api", "high")
    assert [(e["query"], e["value"]) for e in out["entries"]] == [
        ("example widget tracker", 1300), ("example widget restock", 0),
        ("example widget alerts", 480)]
    assert out["cost_usd"] == pytest.approx(0.075)
    run = store.get("run", out["run_id"])
    assert run["spend_usd"] == pytest.approx(0.075)


def test_dataforseo_trends_values_are_relative(store, cfg, deps_for):
    deps, _ = deps_for(fixture("dataforseo_trends_ok.json"))
    out = demand.fetch(store, "dataforseo_trends", q("example widget tracker"), deps=deps)
    _entries_ok(out["entries"], "dataforseo_trends", "api", "high")
    by = {e["metric"]: e for e in out["entries"]}
    assert by["trend_interest_recent"]["value"] == 50  # mean of the last half: 40, 60
    assert by["trend_interest_recent"]["unit"] == "relative_0_100"
    assert by["trend_change_pct"]["value"] == pytest.approx(100.0)  # 25 -> 50


def test_dataforseo_trends_takes_exactly_one_query(store, cfg, deps_for):
    deps, t = deps_for()
    with pytest.raises(SolsticeError) as exc:
        demand.fetch(store, "dataforseo_trends", q("a", "b"), deps=deps)
    assert exc.value.kind == "usage" and t.requests == []


def test_trustmrr_records_revenue_in_dollars(store, cfg, deps_for):
    deps, t = deps_for(fixture("trustmrr_startup.json"))
    out = demand.fetch(store, "trustmrr", q("example-widget-co"), deps=deps)
    _entries_ok(out["entries"], "trustmrr", "api", "medium")
    by = {e["metric"]: e["value"] for e in out["entries"]}
    assert by == {"mrr_usd": 12345.0, "revenue_30d_usd": 13000.0}
    assert t.requests[0].headers["Authorization"] == "Bearer " + KEYS["TRUSTMRR_API_KEY"]
    assert t.requests[0].url.endswith("/startups/example-widget-co")


@pytest.mark.parametrize("platform,fix,posts,engagement", [
    ("reddit", "scrapecreators_reddit.json", 2, 179),
    ("tiktok", "scrapecreators_tiktok.json", 2, 5000 + 300 + 20 + 5 + 10 + 900 + 40 + 2 + 0 + 1),
    ("youtube", "scrapecreators_youtube.json", 2, 15000 + 400 + 35 + 2100),
])
def test_scrapecreators_keyword_search_low_confidence(store, cfg, deps_for, platform, fix, posts,
                                                      engagement):
    deps, t = deps_for(fixture(fix))
    out = demand.fetch(store, "scrapecreators", q("example widget", platform=platform), deps=deps)
    _entries_ok(out["entries"], "scrapecreators", "api", "low")
    by = {e["metric"]: e["value"] for e in out["entries"]}
    assert by == {f"{platform}_post_count": posts, f"{platform}_engagement_sum": engagement}
    assert len(out["evidence_ids"]) == posts
    assert t.requests[0].headers["x-api-key"] == KEYS["SCRAPECREATORS_API_KEY"]
    assert "query=example+widget" in t.requests[0].url


def test_scrapecreators_x_reads_a_handle_never_a_keyword(store, cfg, deps_for):
    deps, t = deps_for(fixture("scrapecreators_x.json"))
    out = demand.fetch(store, "scrapecreators", demand.Params(platform="x", handle="example_creator"),
                       deps=deps)
    by = {e["metric"]: e for e in out["entries"]}
    assert by["x_post_count"]["value"] == 2
    assert by["x_engagement_sum"]["value"] == 210 + 14 + 30 + 9 + 12000 + 5 + 1 + 800
    assert by["x_post_count"]["query"] == "@example_creator"
    assert "handle=example_creator" in t.requests[0].url


def test_scrapecreators_x_with_query_and_no_handle_is_usage(store, cfg, deps_for):
    deps, t = deps_for()
    with pytest.raises(SolsticeError) as exc:
        demand.fetch(store, "scrapecreators", q("example widget", platform="x"), deps=deps)
    assert exc.value.kind == "usage" and t.requests == []


def test_last30days_stores_evidence_only_never_a_demand_number(store, cfg, deps_for, tmp_path):
    raw = json.loads((FIX / "last30days_raw.json").read_text())
    runner = FakeRunner(stdout=json.dumps(raw))
    _config(cfg, adapters={"last30days": {"command": ["example-engine", "--flag"],
                                          "usd_per_run": 0.2}})
    deps, t = deps_for(runner=runner)
    prob = store.create_managed("problem", f.problem())
    out = demand.fetch(store, "last30days", q("example widget restocks"), problem_id=prob["id"],
                       deps=deps)
    assert out["entries"] == [] and t.requests == []
    assert runner.calls == [["example-engine", "--flag", "example widget restocks",
                             "--emit=json", "--json-profile=raw"]]
    evs = [store.get("evidence", i) for i in out["evidence_ids"]]
    assert len(evs) == 2  # the item without a URL is skipped
    assert {e["metric"] for e in evs} == {"engagement"}
    assert sorted(e["value"] for e in evs) == [39, 67]
    got = store.get("problem", prob["id"])
    assert got["demand"] == prob["demand"]
    assert set(out["evidence_ids"]) <= set(got["evidence_ids"])
    assert store.get("run", out["run_id"])["spend_usd"] == pytest.approx(0.2)


def test_last30days_refuses_new_problem(store, cfg, deps_for):
    _config(cfg, adapters={"last30days": {"command": ["example-engine"]}})
    deps, _ = deps_for()
    with pytest.raises(SolsticeError) as exc:
        demand.fetch(store, "last30days", q("x"), new_problem="Example", deps=deps)
    assert exc.value.kind == "usage"


def test_last30days_with_cap_spent_is_budget_and_engine_not_started(store, ws, deps_for):
    _config(ws, monthly=1, adapters={"last30days": {"command": ["example-engine"],
                                                    "usd_per_run": 0.5}})
    _spend(store, 1.0)
    runner = FakeRunner(stdout="{}")
    deps, _ = deps_for(runner=runner)
    prob = store.create_managed("problem", f.problem())
    with pytest.raises(SolsticeError) as exc:
        demand.fetch(store, "last30days", q("x"), problem_id=prob["id"], deps=deps)
    assert exc.value.kind == "budget" and runner.calls == []


def test_manual_entry_is_manual_low_and_needs_a_url(store, cfg, deps_for):
    deps, t = deps_for(env={})
    params = demand.Params(queries=["example widget"], metric="marketplace_reviews", value=212,
                           unit="reviews", url="https://example.com/listing/1",
                           source="example-marketplace")
    out = demand.fetch(store, "manual", params, new_problem="Example manual problem", deps=deps)
    (e,) = out["entries"]
    assert (e["method"], e["confidence"], e["value"]) == ("manual", "low", 212)
    assert out["problem"]["status"] == "found" and t.requests == []
    with pytest.raises(SolsticeError) as exc:
        demand.fetch(store, "manual", demand.Params(queries=["x"], metric="m", value=1, unit="u",
                                                    source="s"), deps=deps)
    assert exc.value.kind == "usage"


# --- keys (KTD17, R26) -------------------------------------------------------


def test_missing_key_is_unavailable_without_a_network_call(store, cfg, deps_for):
    deps, t = deps_for(env={})
    run = demand.start_run(store, "find")
    with pytest.raises(SolsticeError) as exc:
        demand.fetch(store, "scrapecreators", q("x", platform="reddit"), run_id=run["id"],
                     new_problem="Example", deps=deps)
    e = exc.value
    assert e.kind == "adapter"
    assert e.details["status"] == "unavailable"
    assert e.details["reason"] == "missing key SCRAPECREATORS_API_KEY"
    assert t.requests == []
    st = store.get("run", run["id"])["adapter_status"]["scrapecreators"]
    assert st["status"] == "unavailable" and st["reason"] == "missing key SCRAPECREATORS_API_KEY"
    assert store.list("problem") == []


def test_key_only_in_config_or_dotfile_is_still_unavailable(store, ws, deps_for, monkeypatch):
    key = KEYS["SCRAPECREATORS_API_KEY"]
    _config(ws, adapters={"scrapecreators": {"api_key": key, "SCRAPECREATORS_API_KEY": key}})
    (ws / ".env").write_text(f"SCRAPECREATORS_API_KEY={key}\n")
    monkeypatch.chdir(ws)
    deps, t = deps_for(env={})
    src = {s["name"]: s for s in demand.sources(store, deps)["sources"]}
    assert src["scrapecreators"]["status"] == "unavailable"
    assert src["scrapecreators"]["reason"] == "missing key SCRAPECREATORS_API_KEY"
    with pytest.raises(SolsticeError):
        demand.fetch(store, "scrapecreators", q("x", platform="reddit"), deps=deps)
    assert t.requests == []


def test_error_text_with_the_key_is_redacted_when_stored_and_raised(store, cfg, deps_for):
    key = KEYS["SCRAPECREATORS_API_KEY"]
    deps, _ = deps_for(TransportError(f"timed out calling https://api.example.com?token=tok123456 "
                                      f"with {key}"))
    with pytest.raises(SolsticeError) as exc:
        demand.fetch(store, "scrapecreators", q("x", platform="reddit"), new_problem="Example",
                     deps=deps)
    shown = json.dumps(exc.value.details) + exc.value.message
    stored = json.dumps(store.list("problem")) + json.dumps(store.list("run"))
    for text in (shown, stored):
        assert key not in text and "tok123456" not in text
        assert "[redacted]" in text


# --- failures are pending, never zero (R5, AE1) ------------------------------


def test_timeout_on_new_problem_is_pending_evidence(store, cfg, deps_for):
    deps, _ = deps_for(TransportError("timed out"), env={})
    with pytest.raises(SolsticeError) as exc:
        demand.fetch(store, "wporg", q("x"), new_problem="Example", deps=deps)
    assert exc.value.kind == "adapter" and exc.value.details["status"] == "failed"
    (prob,) = store.list("problem")
    assert prob["status"] == "pending_evidence" and "demand" not in prob
    assert prob["pending_fetch"]["adapter"] == "wporg"
    assert "timed out" in prob["pending_fetch"]["error"]
    assert exc.value.details["problem_id"] == prob["id"]


def test_429_on_problem_without_demand_fails_after_bounded_retries(store, cfg, deps_for):
    deps, t = deps_for(*[status_only(429) for _ in range(demand.MAX_RETRIES + 1)], env={})
    with pytest.raises(SolsticeError) as exc:
        demand.fetch(store, "hn_algolia", q("x"), new_problem="Example", deps=deps)
    assert exc.value.details["status"] == "failed"
    assert len(t.requests) == demand.MAX_RETRIES + 1
    (prob,) = store.list("problem")
    assert prob["status"] == "pending_evidence"
    run = store.get("run", exc.value.details["run_id"])
    assert run["adapter_status"]["hn_algolia"]["status"] == "failed"
    assert run["status"] == "failed"


def test_429_then_success_is_one_entry_and_ok(store, cfg, deps_for):
    deps, t = deps_for(status_only(429, {"Retry-After": "2"}), fixture("wporg_query_plugins.json"),
                       env={})
    slept = []
    deps.sleep = slept.append
    out = demand.fetch(store, "wporg", q("x"), new_problem="Example", deps=deps)
    assert len(t.requests) == 2 and 2.0 in slept
    assert out["problem"]["status"] == "found"
    run = store.get("run", out["run_id"])
    assert run["adapter_status"]["wporg"]["status"] == "ok"


def test_dataforseo_rate_limit_task_code_is_retried(store, cfg, deps_for):
    deps, t = deps_for(fixture("dataforseo_rate_limited.json"), fixture("dataforseo_volume_ok.json"))
    out = demand.fetch(store, "dataforseo_volume", q("example widget tracker"), deps=deps)
    assert len(t.requests) == 2 and out["entries"]


def test_dataforseo_task_error_on_http_200_is_failed_never_zero(store, cfg, deps_for):
    deps, _ = deps_for(fixture("dataforseo_task_error.json"))
    with pytest.raises(SolsticeError) as exc:
        demand.fetch(store, "dataforseo_volume", q("x"), new_problem="Example", deps=deps)
    assert exc.value.details["status"] == "failed"
    assert "40501" in exc.value.details["error"]
    (prob,) = store.list("problem")
    assert prob["status"] == "pending_evidence" and "demand" not in prob


def test_second_adapter_failing_on_found_problem_keeps_it_found(store, cfg, deps_for):
    deps, _ = deps_for(fixture("wporg_query_plugins.json"), TransportError("timed out"), env={})
    run = demand.start_run(store, "find")
    out = demand.fetch(store, "wporg", q("x"), run_id=run["id"], new_problem="Example", deps=deps)
    pid = out["problem"]["id"]
    with pytest.raises(SolsticeError):
        demand.fetch(store, "hn_algolia", q("x"), run_id=run["id"], problem_id=pid, deps=deps)
    got = store.get("problem", pid)
    assert got["status"] == "found" and got["demand"] == out["problem"]["demand"]
    assert "pending_fetch" not in got
    st = store.get("run", run["id"])["adapter_status"]
    assert st["wporg"]["status"] == "ok" and st["hn_algolia"]["status"] == "failed"
    assert demand.finish_run(store, run["id"])["status"] == "partial"


def test_success_on_pending_problem_moves_it_to_found(store, cfg, deps_for):
    deps, _ = deps_for(TransportError("timed out"), fixture("hn_search.json"), env={})
    with pytest.raises(SolsticeError):
        demand.fetch(store, "hn_algolia", q("x"), new_problem="Example", deps=deps)
    (prob,) = store.list("problem")
    out = demand.fetch(store, "hn_algolia", q("x"), problem_id=prob["id"], deps=deps)
    got = out["problem"]
    assert got["status"] == "found" and "pending_fetch" not in got
    assert [e["type"] for e in store.events("problem", prob["id"])][-1] == "transition"


def test_success_on_new_problem_is_found_with_entry_ids(store, cfg, deps_for):
    deps, _ = deps_for(fixture("hn_search.json"), env={})
    out = demand.fetch(store, "hn_algolia", q("x"), new_problem="Example problem", deps=deps)
    prob = store.get("problem", out["problem"]["id"])
    assert prob["status"] == "found" and prob["title"] == "Example problem"
    assert all(ULID_RE.match(e["id"]) for e in prob["demand"])
    assert len({e["id"] for e in prob["demand"]}) == len(prob["demand"])
    assert set(prob["evidence_ids"]) == set(out["evidence_ids"])
    assert main_validate(store) == []


def main_validate(store):
    return store.validate_all()[1]


def test_same_evidence_url_twice_on_one_day_is_one_record(store, cfg, deps_for, clock):
    deps, _ = deps_for(fixture("hn_search.json"), fixture("hn_search.json"), env={})
    a = demand.fetch(store, "hn_algolia", q("x"), new_problem="Example", deps=deps)
    clock.advance(hours=2)
    b = demand.fetch(store, "hn_algolia", q("x"), problem_id=a["problem"]["id"], deps=deps)
    assert a["evidence_ids"] == b["evidence_ids"]
    assert len(store.list("evidence")) == 2
    assert len(store.get("problem", a["problem"]["id"])["evidence_ids"]) == 2


# --- spend, runs, budgets (R22) -----------------------------------------------


def _spend(store, usd):
    """Book `usd` on a finished run this month, through the ledger."""
    run = demand.start_run(store, "find")
    roomy = {"budgets": {"factory_monthly_cap_usd": 1000, "per_run_cap_usd": 1000}}
    demand.reserve(store, run["id"], REGISTRY["dataforseo_volume"], usd, roomy)
    demand.finish_run(store, run["id"])


def test_paid_fetch_without_run_opens_and_finishes_an_implicit_run(store, cfg, deps_for):
    deps, _ = deps_for(fixture("scrapecreators_reddit.json"))
    out = demand.fetch(store, "scrapecreators", q("x", platform="reddit"), deps=deps)
    run = store.get("run", out["run_id"])
    assert run["status"] == "complete" and run["finished_at"]
    assert run["spend_usd"] == pytest.approx(0.002)
    st = run["adapter_status"]["scrapecreators"]
    assert st["status"] == "ok" and st["calls"] == 1


def test_monthly_cap_spent_refuses_paid_and_keyless_still_run(store, ws, deps_for):
    _config(ws, monthly=1)
    _spend(store, 1.0)
    deps, t = deps_for(fixture("hn_search.json"))
    with pytest.raises(SolsticeError) as exc:
        demand.fetch(store, "scrapecreators", q("x", platform="reddit"), new_problem="Example",
                     deps=deps)
    assert exc.value.kind == "budget" and t.requests == []
    assert store.list("problem") == []
    run = store.get("run", exc.value.details["run_id"])
    assert run["adapter_status"]["scrapecreators"] == {
        "status": "unavailable", "reason": "budget", "calls": 0, "ok": 0, "failures": 0,
        "spend_usd": 0}
    src = {s["name"]: s for s in demand.sources(store, deps)["sources"]}
    for paid in ("dataforseo_trends", "dataforseo_volume", "trustmrr", "scrapecreators"):
        assert (src[paid]["status"], src[paid]["reason"]) == ("unavailable", "budget")
    assert src["wporg"]["status"] == src["hn_algolia"]["status"] == "available"
    assert demand.fetch(store, "hn_algolia", q("x"), new_problem="Example", deps=deps)["entries"]


def test_spend_in_an_earlier_month_does_not_count(store, ws, deps_for, clock):
    _config(ws, monthly=1)
    _spend(store, 1.0)
    clock.advance(days=31)
    deps, _ = deps_for(fixture("scrapecreators_reddit.json"))
    assert demand.fetch(store, "scrapecreators", q("x", platform="reddit"), deps=deps)["entries"]


def test_per_run_cap_reached_mid_run_skips_paid_calls_and_run_is_partial(store, ws, deps_for):
    _config(ws, per_run=0.1)
    deps, t = deps_for(fixture("dataforseo_volume_ok.json"), fixture("dataforseo_volume_ok.json"))
    run = demand.start_run(store, "find")
    kw = q("example widget tracker")
    demand.fetch(store, "dataforseo_volume", kw, run_id=run["id"], deps=deps)  # 0.09 reserved
    with pytest.raises(SolsticeError) as exc:
        demand.fetch(store, "dataforseo_volume", kw, run_id=run["id"], deps=deps)
    assert exc.value.kind == "budget" and len(t.requests) == 1
    assert "per-run cap" in exc.value.message
    assert demand.finish_run(store, run["id"])["status"] == "partial"


def test_scrapecreators_402_is_out_of_credits_and_later_calls_skip(store, cfg, deps_for):
    deps, t = deps_for(fixture("scrapecreators_out_of_credits.json"))
    run = demand.start_run(store, "find")
    with pytest.raises(SolsticeError) as exc:
        demand.fetch(store, "scrapecreators", q("x", platform="reddit"), run_id=run["id"], deps=deps)
    assert exc.value.details == {**exc.value.details, "status": "unavailable",
                                 "reason": "out of credits"}
    with pytest.raises(SolsticeError) as again:
        demand.fetch(store, "scrapecreators", q("y", platform="tiktok"), run_id=run["id"], deps=deps)
    assert again.value.details["reason"] == "out of credits"
    assert len(t.requests) == 1
    st = store.get("run", run["id"])["adapter_status"]["scrapecreators"]
    assert (st["status"], st["reason"]) == ("unavailable", "out of credits")


def test_fetch_into_a_finished_run_is_refused(store, cfg, deps_for):
    deps, t = deps_for(env={})
    run = demand.start_run(store, "find")
    demand.finish_run(store, run["id"])
    with pytest.raises(SolsticeError):
        demand.fetch(store, "wporg", q("x"), run_id=run["id"], deps=deps)
    assert t.requests == []


def _reserve_in_child(ws, run_id, usd, barrier, results):
    from solstice.state import Store

    store = Store(ws, lock_wait=10)
    barrier.wait()
    try:
        demand.reserve(store, run_id, REGISTRY["dataforseo_volume"], usd,
                       demand.load_config(ws))
        results.put("ok")
    except SolsticeError as exc:
        results.put(exc.kind)


@pytest.mark.parametrize("usd,expect", [(0.6, ["budget", "ok"]), (0.4, ["ok", "ok"])])
def test_parallel_reservations_near_the_cap(ws, usd, expect):
    from solstice.state import Store

    _config(ws, monthly=1, per_run=5)
    store = Store(ws)
    run = demand.start_run(store, "find")
    ctx = multiprocessing.get_context("fork")
    barrier, results = ctx.Barrier(2), ctx.Queue()
    procs = [ctx.Process(target=_reserve_in_child, args=(ws, run["id"], usd, barrier, results))
             for _ in range(2)]
    for p in procs:
        p.start()
    for p in procs:
        p.join(30)
    assert sorted(results.get(timeout=5) for _ in procs) == expect
    booked = expect.count("ok") * usd
    assert store.get("run", run["id"])["spend_usd"] == pytest.approx(booked)


# --- sources -----------------------------------------------------------------


def test_sources_with_no_keys_lists_only_keyless_as_available(store, cfg, deps_for):
    deps, _ = deps_for(env={})
    out = demand.sources(store, deps)
    available = [s["name"] for s in out["sources"] if s["status"] == "available"]
    assert available == ["wporg", "hn_algolia"]
    by = {s["name"]: s for s in out["sources"]}
    assert by["manual"]["status"] == "manual"
    assert by["last30days"]["status"] == "unavailable"
    assert by["dataforseo_volume"]["keys"] == [{"name": "DATAFORSEO_LOGIN", "set": False},
                                               {"name": "DATAFORSEO_PASSWORD", "set": False}]
    assert by["last30days"]["cost"]["estimated"] is True
    assert by["scrapecreators"]["cost"]["model"] == "per_credit"
    assert out["budget"]["monthly_cap_usd"] == 50 and out["budget"]["spent_this_month_usd"] == 0
    assert out["mode"] == "keyless"


def test_sources_cost_comes_from_workspace_config(store, ws, deps_for):
    _config(ws, adapters={"scrapecreators": {"usd_per_credit": 0.001}})
    deps, _ = deps_for()
    by = {s["name"]: s for s in demand.sources(store, deps)["sources"]}
    assert by["scrapecreators"]["cost"]["usd"] == 0.001
    assert by["scrapecreators"]["cost"]["source"] == "config"
    assert by["scrapecreators"]["status"] == "available"


def test_last30days_discovered_from_the_skill_install(store, cfg, deps_for, tmp_path):
    script = tmp_path / "home" / ".claude" / "skills" / "last30days" / "scripts" / "last30days.py"
    script.parent.mkdir(parents=True)
    script.write_text("# synthetic\n")
    deps, _ = deps_for()
    by = {s["name"]: s for s in demand.sources(store, deps)["sources"]}
    assert by["last30days"]["status"] == "available"
    keyless, _ = deps_for(env={})
    assert demand.sources(store, keyless)["mode"] == "keyless"  # no key-backed source is set
    assert demand.sources(store, deps)["mode"] == "keyed"


# --- rate pacing ---------------------------------------------------------------


def test_pacing_spaces_calls_to_the_documented_interval(ws):
    slept, now = [], [100.0]
    pacer = demand.Pacer(ws, clock=lambda: now[0], sleep=slept.append)
    pacer.wait("example_adapter", 5.0)
    pacer.wait("example_adapter", 5.0)  # a second caller in the same instant waits a slot
    pacer.wait("example_adapter", 5.0)
    assert slept == [5.0, 10.0]
    assert (ws / ".solstice" / "rate" / "example_adapter.slot").is_file()


# --- CLI ---------------------------------------------------------------------


@pytest.fixture
def cli(ws, monkeypatch, capsys, tmp_path):
    monkeypatch.setenv("SOLSTICE_WORKSPACE", str(ws))
    monkeypatch.setenv("HOME", str(tmp_path / "home"))
    for k in KEYS:
        monkeypatch.delenv(k, raising=False)
    _config(ws)

    def run(*argv):
        code = main(list(argv))
        cap = capsys.readouterr()
        return code, cap.out, cap.err

    return run


def test_cli_sources_with_no_keys(cli):
    code, out, _ = cli("demand", "sources")
    assert code == 0
    data = json.loads(out)
    assert [s["label"] for s in data["sources"] if s["status"] == "available"] == [
        "WordPress.org", "Hacker News"]


def test_cli_keyless_fetch_new_problem_writes_valid_demand(cli, monkeypatch):
    t = FakeTransport(fixture("hn_search.json"))
    monkeypatch.setattr("solstice.adapters.base.http_transport", t)
    code, out, _ = cli("demand", "fetch", "hn_algolia", "--query", "widget restock",
                       "--new-problem", "--title", "Example problem")
    assert code == 0
    data = json.loads(out)
    assert data["problem"]["status"] == "found"
    code, out, _ = cli("validate")
    assert code == 0 and json.loads(out)["ok"] is True


def test_cli_fetch_failure_is_adapter_envelope(cli, monkeypatch):
    t = FakeTransport(TransportError("timed out"))
    monkeypatch.setattr("solstice.adapters.base.http_transport", t)
    code, out, err = cli("demand", "fetch", "wporg", "--query", "x", "--new-problem",
                         "--title", "Example")
    assert code == 1 and out == ""
    e = json.loads(err)["error"]
    assert e["kind"] == "adapter" and e["details"]["status"] == "failed"


def test_cli_x_with_query_is_usage_64(cli):
    code, out, err = cli("demand", "fetch", "scrapecreators", "--platform", "x", "--query", "x")
    assert code == 64 and out == ""
    assert json.loads(err)["error"]["kind"] == "usage"


def test_cli_run_start_and_finish(cli):
    code, out, _ = cli("run", "start", "--stage", "find")
    run = json.loads(out)
    assert code == 0 and run["status"] == "running" and run["spend_usd"] == 0
    code, out, _ = cli("run", "finish", run["id"])
    assert code == 0 and json.loads(out)["status"] == "complete"
    code, _, err = cli("run", "finish", run["id"])
    assert code == 1


@pytest.mark.parametrize("patch", [{"spend_usd": 0}, {"adapter_status": {}}, {"status": "failed"}])
def test_cli_record_update_cannot_rewrite_the_run_ledger(cli, tmp_path, patch):
    _, out, _ = cli("run", "start", "--stage", "find")
    run = json.loads(out)
    body = tmp_path / "patch.json"
    body.write_text(json.dumps(patch))
    code, _, err = cli("record", "update", "run", run["id"], "--file", str(body))
    assert code == 1 and json.loads(err)["error"]["kind"] == "invalid_record"
