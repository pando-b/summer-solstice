# The qualify checks

Run the checks in this order. Each one ends `pass`, `fail`, or `pending`, and each result cites its basis in `check_basis.<check>`: an evidence record ID, a demand entry ID, a `namecheck` result line, or an approval ID. A check you did not reach stays `pending` with no basis.

Stop at the first `fail` or `pending`, with one exception: upfront spend over the launch limit does not stop the run (see check 8).

| # | check | decision key | passes when | fails when |
|---|---|---|---|---|
| 1 | demand gates | `demand_score` | the problem's `score.gates_passed` is true | any gate in `score.gates` failed |
| 2 | existing spend | `proof_of_spend` | at least one evidence record or demand entry shows money already spent on this job: a revenue figure, a paid install or sales count, a published price with reviews or sales | only engagement, mentions, or stated intent |
| 3 | channel | `channel` | the shape's channel has built-in discovery (a plugin or extension directory, a marketplace with search), or a named distribution path carries a machine-fetched reach number | a web tool or digital product whose path has no fetched reach number: reason "no measured distribution path"; a path that needs cold outreach to strangers |
| 4 | payment rail | `payment_rail` | the channel or a hosted checkout can charge from day one | there is no way to take money in the channel |
| 5 | name/slug | `name_available` | the intended name is free in every place the shape needs | it is taken anywhere it is needed |
| 6 | operator load | `operator_load` | the rating below is `low` | the rating is `medium` or `high` |
| 7 | pro forma | (the pro forma itself) | `solstice proforma` reports `r20.passes` true | gross margin under 0.80 or break-even over 10 customers |
| 8 | upfront spend | `upfront_cash` | spend to channel-live is within the launch limit, or over it and routed to a pay-before-spend test | never fails on its own |
| 9 | owner prerequisites | `owner_prereqs` | every needed account, key, licensed file, or artwork is in place or queued as an approval | the owner declines a prerequisite the product cannot ship without |

## Notes per check

**1. Demand gates.** Read `score` from `solstice record get problem <id>`. Do not re-rate. A problem without a `score` block goes back to find.

**3. Channel.** A reach number enters only through `solstice demand fetch ... --problem <id>`, for example keyword volume for the query the product's main page will target. Cite the demand entry ID. Owner work on the path is fine when it is short (a listing, one launch post); finding contact details for strangers and messaging them fails the check.

**5. Name/slug.** Check every place the shape needs:

- WordPress.org plugin: `solstice namecheck --wporg <slug>`.
- Domain for a web tool or landing page: `solstice namecheck --domain <name>`.
- Chrome Web Store: there is no lookup API. Search the store for the name, then save what you saw with `solstice record create evidence --file -` carrying `kind` `store_search`, the search page `url`, `fetched_at`, `adapter` `web`, `method` `manual`, a one-line `summary`, and `data.query` and `data.matches`. Cite that evidence ID.

`taken` anywhere → verdict `no_go_until_renamed`. Propose two or three alternatives, check each the same way, and list only the free ones in `slug_candidates`. `pending` (timeout or no answer) is never a pass; retry once later, then stop with the check `pending`.

**6. Operator load.** Rate each line, and take the highest:

| line | low | medium | high |
|---|---|---|---|
| support tickets per 100 customers per month | under 5 | 5 to 20 | over 20 |
| payments | uses a merchant or marketplace checkout | — | stores card data, is the merchant of record itself, or moves money |
| health, finance, or personal data | email address only | names and usage data | health, financial records, or other sensitive personal data |
| recurring hands-on work | none | a monthly task under an hour | anything weekly, or any task a customer waits on |

Triggering a charge through a merchant's own gateway does not count as touching payments. Record `operator_load.rating` and the three text fields (`support_volume`, `compliance_exposure`, `hands_on`).

**7. Pro forma.** Pipe the inputs to `solstice proforma --file -` and copy its `pro_forma` block into the decision exactly as printed. Never type a pro forma number yourself. Inputs: `price_usd`, `billing`, `fee_rate`, optional `fee_fixed_usd`, `running_cost_usd_per_customer_month`, `support_minutes_per_customer_month`, `upfront_spend_usd`, optional `channel_capacity_customers`, and `service_months` for one-time sales. The owner's hourly rate comes from workspace config. Base the price on a price you saw on an evidence page, not on a hope. A failing pro forma is a `no_go` whose reason quotes `r20.reason`.

**8. Upfront spend.** Compare `upfront_spend_usd` with `budgets.launch_spend_limit_usd` in workspace config. Within the limit → `pass`. Over it → still `pass`, with the basis "over the launch limit: pay-before-spend test (R21)", and the go follows [pay-before-spend](pay-before-spend.md).

**9. Owner prerequisites.** List what the product needs that only the owner can get. Each becomes an `owner_prereq` approval (step 6 of the skill). Queued counts as `pass`; a missing merchant-of-record account does not block a go.

## Verdicts

- every check `pass` and R20 passes → `go`
- name taken → `no_go_until_renamed`, with `slug_candidates`
- any other `fail` → `no_go`; the reason names the check and its basis; transition the problem to `rejected`
- a `pending` check → `no_go` whose reason starts with `pending:` and names what to recheck; the problem stays `found`
