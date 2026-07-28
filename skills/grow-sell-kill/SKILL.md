---
name: grow-sell-kill
description: >-
  The weekly portfolio verdict across every live product — double down, maintain, position for sale, or kill.
  Use this skill for the weekly Track-3 review, when the user asks "which products do we keep or kill", "what
  should I focus on this week", "portfolio review", "is this one ready to sell", "should I keep working on X",
  or "grow/sell/kill". This is Recipe S15 of the Summer Solstice recipe book — the decision gate that actually
  produces the win, because the $1M outcome comes from concentrating on the one breakout, not from shipping.
  Run it weekly; it feeds the Compounding Log (M2) and triggers Exit Prep (S19).
---

# Grow / Sell / Kill (S15)

Shipping isn't success — what you do *after* launch is. Each week this gate looks at every live product and gives exactly one verdict per product, then reallocates the week's effort and the pooled budget toward the breakout. Killing fast is winning: it frees the scarce resource (build-weeks and attention) for the product that can actually reach a $1M outcome.

## Portfolio rules (External Review #01 — the concentration discipline)

- **Live-product cap: 3–4.** The conveyor may not feed a new build while the cap is full — kill or sell something first. A solo founder's attention is the real pooled budget; twelve orphans lose to five watered bets.
- **Breakout-halt rule:** the moment any product crosses its pre-set breakout bar (default: **$2k MRR + W4 retention ≥ 40%**), the conveyor **halts** — no new builds; all build-weeks and budget concentrate on the breakout until it either stalls (bar re-set) or fires the exit trigger.
- **Channel-aware windows:** a product's kill window starts at *channel-live*, not build-done. Never kill into an unresolved app-store review queue.

## Cadence

Weekly (the Saturday review of the conveyor). Also run on demand when a product hits a milestone or clearly stalls.

## Inputs (per live product)

The alive metric (from S11/S10), MRR, **W1/W4 cohort retention** (instrumented at build time — an S6 acceptance item), week-over-week growth, weekly cost/effort **including the support/ops hours actually consumed vs. the S6 budget**, **unit-economics actuals vs. the S6 pro-forma (GM%, token+infra cost per customer — instrumented at build time; GM drifting below ~75% target or toward the 50% floor is a verdict input)**, age since *channel-live*, and the product's **pre-set thresholds**. Exit triggers and acquirer context come from the operating-system doc + `Acquirer-Intelligence.md` (S20).

## The four verdicts

Apply against thresholds set *in advance* (no rationalizing after the fact):

- **KILL** — missed its pre-set "alive" bar in the window, or flat/declining with no credible path. Kill cleanly; capture why (→ M2). Most products end here, and that's the system working.
- **MAINTAIN** — alive but modest. Keep on minimal effort, monitor; don't pour time in yet.
- **DOUBLE DOWN** — hitting growth + retention milestones (e.g., ~$1k MRR within 30 days, low churn, Rule-of-40-ish). Concentrate time and the pooled budget here.
- **POSITION FOR SALE** — crosses the exit trigger (~$15–20k MRR, clean/transferable, growing, **with cohort-retention history**). Run **S19 Exit Prep** and match to buyers from the acquirer list (S20) — **checking their minimums against our TTM reality** (buyers price ~3–4x *trailing* profit; XO Capital's floor is $30k MRR; most aggregators want $1M+ ARR — see the reality flags in `Acquirer-Intelligence.md`). At $15–20k MRR the realistic near-term venue is marketplace buyers at TTM-profit multiples ($200–500k class); the $1M-class sale matures with ~6 months of retention proof. Engineer toward the financial-buyer profile; strategic adjacency is upside.

## Method

1. Rank the portfolio by traction (against each product's own thresholds, not against each other in raw terms).
2. Assign one verdict per product.
3. **Concentrate:** allocate next week's build-time and budget to the top 1–2 (double-downs); put maintainers on autopilot; execute the kills.
4. Fire any exit triggers → S19.

## Output format

```
PORTFOLIO VERDICT — week of <date>
| Product | Key metric (trend) | Age | Verdict | Next action |
|---------|--------------------|-----|---------|-------------|
Resource allocation this week: <where the build-week + budget go>
Exit triggers fired: <product → S19?>
Kills (with learnings → M2): <product → why>
```

## Compounding

Send every verdict — especially kills and double-downs — to the Compounding Log (M2): which seed/score/demand-confidence profiles became winners vs. zombies? That calibrates S0/S2/S5 over time so future picks are better.

## Anti-patterns

- **Zombie products.** Sunk cost is not a reason to keep a flat product alive; kill it.
- **Spreading effort evenly.** The whole point is to concentrate on the breakout.
- **No pre-set thresholds.** Decide the bar before you look, or you'll talk yourself into keeping losers.
- **Killing without capturing the lesson.** A kill that doesn't teach M2 anything was waste.
