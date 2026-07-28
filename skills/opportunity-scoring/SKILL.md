---
name: opportunity-scoring
description: >-
  Score a candidate opportunity against the canonical Summer Solstice rubric and return a go/no-go verdict.
  Use this skill whenever an opportunity needs grading or ranking — after Opportunity Sourcing surfaces
  candidates, when the user asks "score this idea", "rate this opportunity", "run the scorecard", "which of
  these should we pursue", "is this above the bar", or wants to compare candidates. This is Recipe #2 (S2) of
  the Summer Solstice recipe book and the KEEPER of the canonical rubric file (rubric.json at the project
  root — the machine-readable single source of truth for gates, criteria, and weights). Sourcing (S1) emits
  candidates for it; the Compounding Log (M2) re-weights rubric.json through it. It writes results into
  Opportunity-Scorecard.xlsx.
---

# Opportunity Scoring (S2)

The canonical scoring step. Take a candidate opportunity (from Recipe #1, or entered by hand) and return a weighted score + verdict, with every criterion backed by evidence.

**The rubric lives in ONE machine-readable file: `rubric.json` at the project root.** This skill is its keeper: read `rubric.json` at the start of every scoring run and score against *it*, not against any prose table (including the one below, which is a mirror for human convenience). When M2 calibrates the rubric, the edit is made in `rubric.json` first; then the mirrors (`Opportunity-Scorecard.xlsx`, the operating-system doc §7, the table below) are regenerated to match, and M2's sync check verifies they agree. Prose replication with a "please sync" instruction is what caused drift v2.1→v3.0 — the JSON file + sync check is the fix.

## Inputs

A candidate with: problem statement, persona, venue, and the dated/linked evidence gathered in Recipe #1 (existing spend, engagement intensity, etc.). For any finalist, also the **S4 positioning-teardown** output — the Competitive Wedge score must cite it. Score one candidate or a batch.

## Step 1 — Kill gates (from rubric.json; auto-reject if ANY is true)

Mirror of `rubric.json` v3.1:

1. No free ($0) path to buyers.
2. Can't ship a usable v1 within one build week.
3. Needs licensing/approval we can't obtain (or unacceptable legal risk).
4. Build + launch cost exceeds the pooled <$2k budget.
5. **Undifferentiated AI wrapper** — no workflow ownership, data moat, or switching cost (acquirers treat these as invisible).
6. **No viable payment mechanism** — the chosen channel/product has no named way to charge money. (Agent skill stores have no payment rail; a skill-store-distributed candidate must name its monetization mechanism to pass.)
7. **Margin floor (v3.1)** — structurally cannot clear **≥50% gross margin** at realistic pricing: COGS-heavy inference relative to what the market bears, pass-through-dominated economics, or a free-incumbent price ceiling. Judged from the Step 2.5 mini pro-forma. 50% is the floor; **~75–80% GM is the design target** (Flippa lists want GM>75%; financial buyers price margin).

Any gate failed → **REJECT**, no scoring needed.

*Note: agent-native is no longer a kill gate. It is the **default architecture** we build in (agent parity, atomic tools, features-as-prompts) and is scored inside Build Feasibility and Acquirability — we don't auto-reject opportunities whose buyers don't price it. (Owner decision, July 2026, External Review #01.)*

## Step 2 — Weighted criteria (score each 1 = weak to 5 = strong)

Mirror of `rubric.json` v3.1 (sum = 100):

| # | Criterion | Weight | 5 = strong when… |
|---|---|---|---|
| 1 | Pain & Urgency | 16 | acute, "now" problem people actively complain about (high engagement) |
| 2 | Willingness to Pay | 16 | buyers already pay for inferior tools/workarounds |
| 3 | Free Reachability | 12 | a precise $0 channel reaches buyers at scale **with a fast channel clock** — record review/moderation latency (e.g., Shopify App Store 2–4+ weeks), whether a payment rail exists in-channel, and expected time-to-first-100-qualified-users |
| 4 | Time-to-First-Dollar | 8 | can charge within days of *channel-live* (not build-done) |
| 5 | Build Feasibility | 10 | trivially agent-native (our default build form), v1 well within a build week |
| 6 | **Natural Retention** | 10 | recurring job-to-be-done (weekly/monthly), accumulates data or workflow lock-in — the category retains by nature; **1–2 = one-shot job** (migration, generator). Buyers gate on churn; this selects for categories that *can* retain before we can measure it |
| 7 | Market Adequacy | 4 | enough buyers to reach ~$250k+ ARR, niche enough to win |
| 8 | Acquirability | 14 | recurring revenue + high switching cost + owner-independent/transferable + clean asset; bonus if adjacent to a named acquirer **whose minimums we can realistically meet and whose appetite is evidenced by a specific portco/deal** (opportunity-specific buyer map — check the age/TTM reality flags in `Acquirer-Intelligence.md`; a famous name without portfolio adjacency = no named buyer) |
| 9 | Competitive Wedge | 10 | clear underserved gap + defensible angle, **cited from an S4 positioning-teardown, not vibes**; 1–2 = saturated, entrenched incumbents, no wedge |

Each score needs a one-line justification and its strongest evidence link. **Weighted score = Σ(weight × score) ÷ 5 → 0–100.**

## Step 2.5 — Margin floor check (mini pro-forma; required for every candidate)

The S2 rung of the **economics ladder** (rubric.json v3.1 note; each gate raises fidelity: S0 coarse class → S2 this → S4 pricing corridor → S6 v1 pro-forma → S15 actuals). Five lines, evidence-anchored:

```
PRO-FORMA (S2 fidelity) — <candidate>
Price anchor: <$X/mo — from NAMED competitor price points or the workaround's cost, not aspiration>
COGS-intensity class: <inference-light workflow | per-unit document parsing | inference-core>
COGS/unit/mo: <$ — tokens (model×volume est.) + infra + per-unit pass-throughs (SMS, data APIs)>
Gross margin at anchor: <%>   → margin_floor gate: PASS (≥50%) | FAIL
Margin risks: <what moves it — e.g., support hours (SDE, not GM), parsing maintenance, metering needed on the agent surface>
```

Rules of thumb: **inference-light workflow** products (event-driven engines where LLMs draft text or power an agent interface) run <$5/customer/mo in tokens — GM is set by price, not COGS. **Per-unit document parsing** scales with volume — model it per page/doc at the cheapest capable model. **Inference-core** products (every unit of value = frontier tokens) are margin-fragile AND usually wrapper-gate suspects — double-check gate 5.

## Step 3 — Verdict

- **≥ 75** and all gates pass → **STRONG**; advance to the Demand Confidence Gate (S5).
- **60–74** → **CONDITIONAL**; pursue only if the pipeline is thin.
- **< 60** → **KILL**.

A passing score is necessary but not sufficient — it still must clear S5 before earning a build week. **Hard rule: any candidate with Wedge ≤ 3 can NEVER clear S5 on Tier-1 category evidence alone — the switch test is mandatory** (see `demand-confidence-gate`).

## Step 4 — Write to the Scorecard

Enter the candidate into `Opportunity-Scorecard.xlsx` (candidates are columns: 6 gate Y/N values, then the 9 scores 1–5). The sheet computes the weighted score and verdict automatically — use it as the canonical calculator.

## Output format

```
SCORING — <candidate / persona>
Rubric version: <from rubric.json>
Gates: NoFreePath=N | NoV1InBuildWeek=N | NeedsLicensing=N | OverBudget=N | Wrapper=N | NoPaymentRail=N | MarginFloor=N
Pro-forma (S2 fidelity): price anchor $X | COGS class | COGS $/unit | GM % | risks
Scores (1-5, with evidence):
  Pain&Urgency=5  — <why + link>
  WillingnessToPay=4 — <why + link>
  FreeReachability=4 — <why + link; channel latency = X, payment rail = Y/N>
  TimeToFirstDollar=4 — <why>
  BuildFeasibility=5 — <why>
  NaturalRetention=4 — <recurring JTBD / data accumulation / lock-in — why>
  MarketAdequacy=3 — <why>
  Acquirability=4 — <why + buyer map: named buyer + the portco/deal evidencing appetite + thesis/size-class/venue + reachable-at milestone>
  CompetitiveWedge=3 — <cite the S4 teardown>
Weighted score: <0–100>   Verdict: STRONG | CONDITIONAL | KILL
If Wedge <= 3: flag "S5 switch test MANDATORY"
```

For a batch, also return a ranked table and flag the top candidates for S5.

## Maintaining the rubric (for M2)

1. Edit **`rubric.json`** (weights, anchors, gates) with the changelog entry.
2. Regenerate the mirrors: `Opportunity-Scorecard.xlsx`, operating-system doc §7, and the tables in this file.
3. M2's sync check verifies all mirrors agree with `rubric.json` — a mismatch is a bug, fix it immediately.
4. **Anti-overfit guardrails:** weight edits require **n≥3** logged product outcomes; structural changes (gates added/removed, criteria added/retired) require **n≥5** or an unambiguous external fact. One rehearsal is not a trend.

## Anti-patterns

- **Scoring without evidence.** Every criterion needs a real, dated, linked reason — no vibes.
- **Wedge by intuition.** Wedge scores cite an S4 teardown or they don't count.
- **Skipping the gates.** A failed gate rejects regardless of an attractive score.
- **Letting the rubric drift.** `rubric.json` first, then regenerate mirrors, then verify. Never hand-edit a mirror alone.
