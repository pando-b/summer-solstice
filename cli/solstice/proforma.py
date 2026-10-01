"""The R20 pro forma: unit economics from stated inputs, computed exactly.

Inputs (JSON object; every other key is refused):

- `price_usd` (> 0) and `billing` (`monthly`, `yearly`, or `one_time`)
- `service_months` (integer >= 1): required for `one_time`, refused otherwise;
  the months one purchase is expected to be served
- `fee_rate` (0..1, share of each charge) and `fee_fixed_usd` (per charge,
  default 0): payment and marketplace fees
- `running_cost_usd_per_customer_month`: hosting, APIs, tokens per customer
- `support_minutes_per_customer_month`: valued at the owner's hourly rate,
  read from workspace config `budgets.owner_hourly_rate_usd` (never from the
  inputs, so the rate cannot drift per candidate)
- `upfront_spend_usd`: new spend to reach channel-live
- `channel_capacity_customers` (optional): customers the channel can
  plausibly deliver, set beside `customers_for_5k_mrr`

Every `*_usd_per_customer` figure in the output is per customer per month.
Revenue per month is the price (monthly), price / 12 (yearly), or price /
service_months (one-time). Break-even customers is the number of first
charges whose contribution covers the upfront spend; it is null when a
customer contributes nothing, which can never break even.

Arithmetic runs on exact fractions of the input values and rounds only on
output (USD to cents, margin to 4 places), so the same inputs always give
the same block.
"""

from __future__ import annotations

import math
from fractions import Fraction
from pathlib import Path

from solstice.errors import SolsticeError
from solstice.lifecycle import BREAK_EVEN_MAX, MARGIN_FLOOR, fmt_ts
from solstice.workspace import budget, load_config

DEFAULT_OWNER_RATE_USD = 100.0
MRR_TARGET_USD = 5000
BILLINGS = ("monthly", "yearly", "one_time")

_NUMBERS = {
    "price_usd": "positive",
    "fee_rate": "fraction",
    "fee_fixed_usd": "nonneg",
    "running_cost_usd_per_customer_month": "nonneg",
    "support_minutes_per_customer_month": "nonneg",
    "upfront_spend_usd": "nonneg",
}
_REQUIRED = ("price_usd", "billing", "fee_rate", "running_cost_usd_per_customer_month",
             "support_minutes_per_customer_month", "upfront_spend_usd")
_ALLOWED = set(_NUMBERS) | {"billing", "service_months", "channel_capacity_customers"}
EVENT = "proforma_computed"


class ProformaError(SolsticeError):
    """The inputs cannot be computed; `details.errors` lists why."""

    kind = "invalid_record"


def owner_rate(workspace: Path) -> float:
    return budget(load_config(workspace), "owner_hourly_rate_usd", DEFAULT_OWNER_RATE_USD)


def _is_num(v) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool) and math.isfinite(v)


def _is_int(v) -> bool:
    return isinstance(v, int) and not isinstance(v, bool)


def _check(inputs) -> list[str]:
    if not isinstance(inputs, dict):
        return ["pro forma inputs must be a JSON object"]
    errs = [f"{k}: unknown input" + (" (the owner rate comes from workspace config "
                                     "budgets.owner_hourly_rate_usd)" if k.startswith("owner_rate")
                                     else "")
            for k in sorted(set(inputs) - _ALLOWED)]
    errs += [f"{k}: required" for k in _REQUIRED if k not in inputs]
    for k, rule in _NUMBERS.items():
        if k not in inputs:
            continue
        v = inputs[k]
        if not _is_num(v):
            errs.append(f"{k}: must be a number")
        elif rule == "positive" and v <= 0:
            errs.append(f"{k}: must be greater than 0")
        elif rule == "nonneg" and v < 0:
            errs.append(f"{k}: must be 0 or more")
        elif rule == "fraction" and not 0 <= v <= 1:
            errs.append(f"{k}: must be a share between 0 and 1 (7% is 0.07)")
    billing = inputs.get("billing")
    if "billing" in inputs and billing not in BILLINGS:
        errs.append(f"billing: must be one of {', '.join(BILLINGS)}")
    if billing == "one_time":
        sm = inputs.get("service_months")
        if not (_is_int(sm) and sm >= 1):
            errs.append("service_months: one_time billing needs the whole number of months "
                        "one purchase is served")
    elif "service_months" in inputs:
        errs.append("service_months: applies only to one_time billing")
    cap = inputs.get("channel_capacity_customers")
    if "channel_capacity_customers" in inputs and not (_is_int(cap) and cap >= 0):
        errs.append("channel_capacity_customers: must be a whole number, 0 or more")
    return errs


def _q(v) -> Fraction:
    return Fraction(str(v))


def _usd(x: Fraction) -> float:
    return float(round(x, 2))


def compute(inputs: dict, *, owner_rate: float) -> dict:
    """{"pro_forma": <decision schema block>, "r20": <gate results>}."""
    errs = _check(inputs)
    if errs:
        raise ProformaError(f"pro forma inputs refused: {'; '.join(errs)}",
                            details={"errors": errs})
    price = _q(inputs["price_usd"])
    billing = inputs["billing"]
    months = {"monthly": 1, "yearly": 12}.get(billing) or inputs["service_months"]
    rate = _q(owner_rate)

    revenue_m = price / months
    fees_m = (_q(inputs["fee_rate"]) * price + _q(inputs.get("fee_fixed_usd", 0))) / months
    running_m = _q(inputs["running_cost_usd_per_customer_month"])
    support_m = _q(inputs["support_minutes_per_customer_month"]) / 60 * rate
    margin_m = revenue_m - fees_m - running_m - support_m
    gross_margin = margin_m / revenue_m
    upfront = _q(inputs["upfront_spend_usd"])
    per_charge = margin_m * months
    if upfront == 0:
        break_even = 0
    elif per_charge > 0:
        break_even = math.ceil(upfront / per_charge)
    else:
        break_even = None

    pf = {
        "price_usd": _usd(price),
        "billing": billing,
        "fees_usd_per_customer": _usd(fees_m),
        "running_cost_usd_per_customer": _usd(running_m),
        "support_cost_usd_per_customer": _usd(support_m),
        "owner_rate_usd_per_hour": float(rate),
        "upfront_spend_usd": _usd(upfront),
        "gross_margin": float(round(gross_margin, 4)),
        "break_even_customers": break_even,
        "customers_for_5k_mrr": math.ceil(MRR_TARGET_USD / revenue_m),
    }
    if "channel_capacity_customers" in inputs:
        pf["channel_capacity_customers"] = inputs["channel_capacity_customers"]
    basis = (f"per customer per month; fees {inputs['fee_rate']:g} of each charge"
             f" + {inputs.get('fee_fixed_usd', 0):g} USD; support "
             f"{inputs['support_minutes_per_customer_month']:g} min at {float(rate):g} USD/h")
    if billing != "monthly":
        basis += f"; one charge covers {months} months"
    pf["notes"] = basis
    return {"pro_forma": pf, "r20": gates(pf)}


def gates(pf: dict) -> dict:
    gm, be = pf["gross_margin"], pf["break_even_customers"]
    margin_ok = gm >= MARGIN_FLOOR
    be_ok = be is not None and be <= BREAK_EVEN_MAX
    reasons = []
    if not margin_ok:
        reasons.append(f"gross margin {gm} is below {MARGIN_FLOOR}")
    if not be_ok:
        reasons.append("a customer contributes nothing, so it never breaks even" if be is None
                       else f"break-even needs {be} customers, more than {BREAK_EVEN_MAX}")
    return {
        "passes": margin_ok and be_ok,
        "gross_margin": {"result": "pass" if margin_ok else "fail", "value": gm,
                         "floor": MARGIN_FLOOR},
        "break_even": {"result": "pass" if be_ok else "fail", "value": be,
                       "max": BREAK_EVEN_MAX},
        "reason": "; ".join(reasons) or "passes R20",
    }


def run(store, inputs: dict, decision_id: str | None = None) -> dict:
    """Compute at the workspace's owner rate; with `decision_id`, write the
    block into that decision under the lock (validation applies: a go whose
    new pro forma fails R20 is refused and left unchanged)."""
    out = compute(inputs, owner_rate=owner_rate(store.workspace))
    if decision_id is None:
        return out
    with store.lock():
        rec = store.get("decision", decision_id)
        now = fmt_ts(store.now())
        store.put_locked("decision", {**rec, "pro_forma": out["pro_forma"]},
                         {"at": now, "type": EVENT, "gross_margin": out["pro_forma"]["gross_margin"],
                          "break_even_customers": out["pro_forma"]["break_even_customers"]})
    return {**out, "decision_id": decision_id}
