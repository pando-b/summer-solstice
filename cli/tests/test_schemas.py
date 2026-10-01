"""Record schemas and validator rules (R3, R5, R6, R19, R20; AE1, AE4)."""

import json

import pytest
from jsonschema import Draft202012Validator

import factories as f
from solstice.__main__ import main
from solstice.state import ENTITIES, SCHEMA_VERSION, load_schema, validate_record


def _errors(entity, body):
    rec = {"id": "01JAAAAAAAAAAAAAAAAAAAAAAA", "schema_version": SCHEMA_VERSION,
           "created_at": "2026-01-05T12:00:00Z", "updated_at": "2026-01-05T12:00:00Z"}
    rec.update(body)
    if entity == "evidence":
        rec.setdefault("idempotency_key", "https://example.com/thread/123|2026-01-04")
    return validate_record(entity, rec)


@pytest.mark.parametrize("entity", sorted(ENTITIES))
def test_every_schema_is_valid_draft_2020_12(entity):
    schema = load_schema(entity)
    assert schema["$schema"] == "https://json-schema.org/draft/2020-12/schema"
    Draft202012Validator.check_schema(schema)
    assert "schema_version" in schema["required"]


SYNTHETIC_VALID = {
    "problem": f.problem(),
    "evidence": f.evidence(),
    "decision": f.decision(),
    "product": f.product(),
    "approval": f.approval(),
    "content_item": {"product_id": "01JBBBBBBBBBBBBBBBBBBBBBBB", "channel": "example-forum",
                     "kind": "launch_post", "status": "draft", "body": "Synthetic post."},
    "revenue_snapshot": {"product_id": "01JBBBBBBBBBBBBBBBBBBBBBBB", "provider": "example-pay",
                         "fetched_at": "2026-01-05T00:00:00Z", "mrr_usd": 0, "currency": "USD",
                         "method": "api"},
    "run": {"stage": "find", "status": "partial", "started_at": "2026-01-05T00:00:00Z",
            "checkpoint": {"cursor": "lens-2"}, "spend_usd": 0.4,
            "adapter_status": {"example_adapter": {"status": "failed", "error": "timeout"}}},
}


@pytest.mark.parametrize("entity", sorted(ENTITIES))
def test_synthetic_fixture_validates(entity):
    assert _errors(entity, SYNTHETIC_VALID[entity]) == []


# --- problem demand (R3, R5, AE1) ------------------------------------------


def test_demand_value_without_fetched_at_or_url_is_rejected():
    d = f.demand()
    del d["fetched_at"], d["url"]
    errs = _errors("problem", f.problem(demand=[d]))
    joined = " ".join(errs)
    assert "fetched_at" in joined and "url" in joined


@pytest.mark.parametrize("field", ["metric", "value", "unit", "source", "query",
                                   "fetched_at", "url", "adapter", "method"])
def test_each_demand_provenance_field_is_required(field):
    d = f.demand()
    del d[field]
    assert _errors("problem", f.problem(demand=[d]))


def test_demand_method_model_is_rejected():
    assert _errors("problem", f.problem(demand=[f.demand(method="model")]))


def test_demand_value_zero_with_full_provenance_is_accepted():
    assert _errors("problem", f.problem(demand=[f.demand(value=0)])) == []


def test_found_problem_without_any_demand_is_rejected():
    assert _errors("problem", f.problem(demand=[]))
    body = f.problem()
    del body["demand"]
    assert _errors("problem", body)


def test_pending_evidence_problem_records_the_fetch_failure_not_zero():
    body = f.problem(status="pending_evidence", pending_fetch={
        "adapter": "example_adapter", "error": "timeout", "attempted_at": "2026-01-05T10:00:00Z"})
    del body["demand"]
    assert _errors("problem", body) == []
    del body["pending_fetch"]
    assert _errors("problem", body)


def test_demand_fetched_at_must_be_a_timestamp():
    assert _errors("problem", f.problem(demand=[f.demand(fetched_at="last week")]))


# --- decision (R6, R19, R20, AE4) ------------------------------------------


def test_go_without_pro_forma_is_rejected():
    body = f.decision()
    del body["pro_forma"]
    assert any("pro_forma" in e for e in _errors("decision", body))


def test_go_with_gross_margin_below_80_percent_is_rejected():
    errs = _errors("decision", f.decision(pro_forma=f.pro_forma(gross_margin=0.79)))
    assert any("gross margin" in e for e in errs)


def test_go_with_break_even_beyond_ten_customers_is_rejected():
    errs = _errors("decision", f.decision(pro_forma=f.pro_forma(break_even_customers=11)))
    assert any("break-even" in e for e in errs)


def test_go_with_a_failing_or_pending_check_is_rejected():
    checks = dict(f.ALL_PASS, name_available="pending")
    assert _errors("decision", f.decision(checks=checks))


def test_go_with_operator_load_not_low_is_rejected():
    body = f.decision()
    body["operator_load"]["rating"] = "medium"
    assert _errors("decision", body)


def test_no_go_until_renamed_is_accepted():
    checks = dict(f.ALL_PASS, name_available="fail")
    assert _errors("decision", f.decision(verdict="no_go_until_renamed", checks=checks)) == []


def test_no_go_needs_no_pro_forma():
    body = f.decision(verdict="no_go", checks=dict(f.ALL_PASS, demand_score="fail"))
    del body["pro_forma"]
    assert _errors("decision", body) == []


def test_unknown_verdict_and_check_value_rejected():
    assert _errors("decision", f.decision(verdict="maybe"))
    assert _errors("decision", f.decision(checks=dict(f.ALL_PASS, channel="ok")))


# --- approvals, runs --------------------------------------------------------


def test_approval_subtypes():
    for sub in ("outbound", "owner_prereq", "irreversible"):
        assert _errors("approval", f.approval(subtype=sub)) == []
    assert _errors("approval", f.approval(subtype="other"))


def test_run_status_enum():
    body = dict(SYNTHETIC_VALID["run"], status="done")
    assert _errors("run", body)


def test_unknown_top_level_field_is_rejected():
    assert _errors("product", f.product(chanel_live_at="2026-01-01T00:00:00Z"))


# --- CLI: solstice schema ---------------------------------------------------


def test_cli_schema_prints_the_schema(capsys):
    assert main(["schema", "problem"]) == 0
    out = json.loads(capsys.readouterr().out)
    assert out == load_schema("problem")


def test_cli_schema_unknown_entity_fails(capsys):
    with pytest.raises(SystemExit) as exc:
        main(["schema", "nonsense"])
    assert exc.value.code != 0


def test_pending_operator_load_is_accepted_on_a_non_go_decision():
    checks = dict(f.ALL_PASS, name_available="fail", operator_load="pending")
    body = f.decision(verdict="no_go_until_renamed", checks=checks)
    body["operator_load"]["rating"] = "pending"
    assert _errors("decision", body) == []


def test_go_with_pending_operator_load_is_rejected():
    body = f.decision()
    body["operator_load"]["rating"] = "pending"
    assert any("operator_load" in e for e in _errors("decision", body))


def test_check_basis_cites_each_check():
    body = f.decision(check_basis={"proof_of_spend": ["https://example.com/pricing"]})
    assert _errors("decision", body) == []
    body = f.decision(check_basis={"not_a_check": ["https://example.com"]})
    assert _errors("decision", body)
