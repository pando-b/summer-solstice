"""The R20 pro forma: deterministic unit economics from stated inputs, with
support time valued at the owner's rate from workspace config. All numbers
are synthetic."""

import json

import pytest

import factories as f
from solstice import proforma
from solstice.__main__ import main
from solstice.state import validate_record


def inputs(**over) -> dict:
    i = {
        "price_usd": 99,
        "billing": "monthly",
        "fee_rate": 0.07,
        "running_cost_usd_per_customer_month": 4,
        "support_minutes_per_customer_month": 2,
        "upfront_spend_usd": 30,
    }
    i.update(over)
    return i


def test_heavy_support_fails_the_margin_gate():
    out = proforma.compute(inputs(support_minutes_per_customer_month=20), owner_rate=100)
    pf = out["pro_forma"]
    assert pf["support_cost_usd_per_customer"] == 33.33
    assert pf["fees_usd_per_customer"] == 6.93
    assert pf["gross_margin"] == 0.5529
    assert out["r20"]["passes"] is False
    assert out["r20"]["gross_margin"]["result"] == "fail"
    assert "0.5529" in out["r20"]["reason"]


def test_light_support_passes_the_margin_gate():
    out = proforma.compute(inputs(), owner_rate=100)
    pf = out["pro_forma"]
    assert pf["gross_margin"] == 0.8559
    assert pf["break_even_customers"] == 1
    assert pf["customers_for_5k_mrr"] == 51
    assert pf["owner_rate_usd_per_hour"] == 100
    assert out["r20"]["passes"] is True


def test_unchanged_inputs_give_identical_output():
    a = proforma.compute(inputs(), owner_rate=100)
    b = proforma.compute(inputs(), owner_rate=100)
    assert json.dumps(a, sort_keys=True) == json.dumps(b, sort_keys=True)


def test_output_block_fits_the_decision_schema():
    pf = proforma.compute(inputs(channel_capacity_customers=300), owner_rate=100)["pro_forma"]
    assert pf["channel_capacity_customers"] == 300
    assert validate_record("decision", {**_ids(), **f.decision(pro_forma=pf)}) == []


def test_break_even_counts_customers_to_cover_upfront_spend():
    # contribution per monthly customer: 20 - 2 - 1 - 0 = 17; 120 / 17 -> 8
    pf = proforma.compute(inputs(price_usd=20, fee_rate=0.1, running_cost_usd_per_customer_month=1,
                                 support_minutes_per_customer_month=0, upfront_spend_usd=120),
                          owner_rate=100)["pro_forma"]
    assert pf["break_even_customers"] == 8
    assert pf["upfront_spend_usd"] == 120


def test_break_even_over_ten_fails_r20():
    out = proforma.compute(inputs(price_usd=20, fee_rate=0, running_cost_usd_per_customer_month=0,
                                  support_minutes_per_customer_month=0, upfront_spend_usd=280),
                           owner_rate=100)
    assert out["pro_forma"]["break_even_customers"] == 14
    assert out["r20"]["break_even"]["result"] == "fail"
    assert out["r20"]["passes"] is False


def test_negative_contribution_cannot_break_even():
    out = proforma.compute(inputs(price_usd=5, support_minutes_per_customer_month=30), owner_rate=100)
    assert out["pro_forma"]["break_even_customers"] is None
    assert out["r20"]["break_even"]["result"] == "fail"
    assert out["pro_forma"]["gross_margin"] < 0


def test_yearly_billing_normalizes_to_monthly():
    pf = proforma.compute(inputs(price_usd=120, billing="yearly", fee_rate=0,
                                 running_cost_usd_per_customer_month=1,
                                 support_minutes_per_customer_month=0, upfront_spend_usd=100),
                          owner_rate=100)["pro_forma"]
    # 10/month revenue, 1/month cost -> 0.9; one yearly charge contributes 108
    assert pf["gross_margin"] == 0.9
    assert pf["break_even_customers"] == 1
    assert pf["customers_for_5k_mrr"] == 500


def test_one_time_billing_needs_service_months():
    with pytest.raises(proforma.ProformaError) as exc:
        proforma.compute(inputs(billing="one_time"), owner_rate=100)
    assert any("service_months" in e for e in exc.value.details["errors"])
    pf = proforma.compute(inputs(price_usd=60, billing="one_time", service_months=12, fee_rate=0,
                                 running_cost_usd_per_customer_month=0.5,
                                 support_minutes_per_customer_month=0),
                          owner_rate=100)["pro_forma"]
    assert pf["gross_margin"] == 0.9


@pytest.mark.parametrize("bad", [
    {"price_usd": 0},
    {"price_usd": "99"},
    {"billing": "weekly"},
    {"fee_rate": 7},
    {"support_minutes_per_customer_month": -1},
    {"service_months": 12},  # only for one_time
    {"owner_rate_usd_per_hour": 10},  # comes from workspace config only
    {"unknown_field": 1},
])
def test_bad_inputs_are_refused_with_a_list_of_errors(bad):
    with pytest.raises(proforma.ProformaError) as exc:
        proforma.compute(inputs(**bad), owner_rate=100)
    assert exc.value.kind == "invalid_record"
    assert exc.value.details["errors"]


def test_missing_input_is_refused():
    body = inputs()
    del body["upfront_spend_usd"]
    with pytest.raises(proforma.ProformaError):
        proforma.compute(body, owner_rate=100)


def _ids():
    return {"id": "01HZZZZZZZZZZZZZZZZZZZZZZZ", "schema_version": 1,
            "created_at": "2026-01-05T12:00:00Z", "updated_at": "2026-01-05T12:00:00Z"}


# --- owner rate from config, CLI, and writing into a decision -------------------


@pytest.fixture
def cli(ws, monkeypatch, capsys, tmp_path, write_config):
    monkeypatch.setenv("SOLSTICE_WORKSPACE", str(ws))
    write_config(ws, "workspace_root: .\nbudgets:\n  owner_hourly_rate_usd: 60\n")

    def run(*argv, body=None):
        if body is not None:
            p = tmp_path / "body.json"
            p.write_text(json.dumps(body))
            argv = [a if a != "@body" else str(p) for a in argv]
        code = main(list(argv))
        cap = capsys.readouterr()
        return code, cap.out, cap.err

    return run


def test_owner_rate_reads_workspace_config(ws, write_config):
    write_config(ws, "budgets:\n  owner_hourly_rate_usd: 60\n")
    assert proforma.owner_rate(ws) == 60


def test_owner_rate_defaults_when_config_lacks_it(ws):
    assert proforma.owner_rate(ws) == proforma.DEFAULT_OWNER_RATE_USD


def test_cli_prints_pro_forma_at_the_configured_rate(cli):
    code, out, _ = cli("proforma", "--file", "@body", body=inputs(support_minutes_per_customer_month=6))
    assert code == 0
    data = json.loads(out)
    assert data["pro_forma"]["owner_rate_usd_per_hour"] == 60
    assert data["pro_forma"]["support_cost_usd_per_customer"] == 6.0


def test_cli_bad_inputs_print_the_envelope(cli):
    code, out, err = cli("proforma", "--file", "@body", body=inputs(price_usd=0))
    assert code == 1 and out == ""
    e = json.loads(err)["error"]
    assert e["kind"] == "invalid_record" and e["details"]["errors"]


def test_cli_writes_the_pro_forma_into_a_decision(cli):
    code, out, _ = cli("record", "create", "decision", "--file", "@body",
                       body=f.decision(verdict="no_go", reason="Synthetic pending margin."))
    did = json.loads(out)["id"]
    code, out, _ = cli("proforma", "--file", "@body", "--decision", did, body=inputs())
    assert code == 0
    assert json.loads(out)["decision_id"] == did
    rec = json.loads(cli("record", "get", "decision", did)[1])
    assert rec["pro_forma"]["gross_margin"] == json.loads(out)["pro_forma"]["gross_margin"]
    events = json.loads(cli("record", "events", "decision", did)[1])
    assert events[-1]["type"] == "proforma_computed"


def test_cli_refuses_a_failing_pro_forma_on_a_go_decision(cli):
    code, out, _ = cli("record", "create", "decision", "--file", "@body", body=f.decision())
    did = json.loads(out)["id"]
    before = json.loads(cli("record", "get", "decision", did)[1])
    code, out, err = cli("proforma", "--file", "@body", "--decision", did,
                         body=inputs(support_minutes_per_customer_month=40))
    assert code == 1
    assert json.loads(err)["error"]["kind"] == "invalid_record"
    assert json.loads(cli("record", "get", "decision", did)[1]) == before


def test_callers_cannot_forge_the_proforma_event(cli):
    code, out, _ = cli("record", "create", "decision", "--file", "@body",
                       body=f.decision(verdict="no_go", reason="Synthetic."))
    did = json.loads(out)["id"]
    code, _, err = cli("record", "event", "decision", did, "--file", "@body",
                       body={"type": "proforma_computed"})
    assert code == 1
