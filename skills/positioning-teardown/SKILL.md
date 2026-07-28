---
name: positioning-teardown
description: >-
  Competitive and positioning teardown for a candidate opportunity — the evidence behind the Competitive
  Wedge score. Use this skill for any Scorecard finalist BEFORE its Wedge score is trusted, whenever the
  user asks "who are the incumbents", "is this market crowded", "what's our wedge", "positioning teardown",
  "competitive analysis for this candidate", or when a candidate is about to enter the Demand Confidence
  Gate. This is S4 of the Summer Solstice recipe book. It exists because Wedge is 10% of the rubric and was
  previously scored on vibes (External Review #01): the rehearsal assigned Wedge=2 and Wedge=3 with no
  teardown behind them. Time-boxed to half a day per candidate.
---

# Positioning Teardown (S4)

Produce the evidence that makes a **Competitive Wedge score defensible** — and, if a wedge exists, the
positioning that exploits it. Anchored in April Dunford's *Obviously Awesome* method, compressed to a
half-day, single-candidate pass. Input: a scored candidate from S2 (problem, persona, venue, evidence).
Output: a teardown the Wedge score must cite, plus the S5 switch-test target list.

## Time box

**Half a day per candidate, maximum.** This runs only on finalists (top 1–3 per week), not the whole
shortlist. If half a day can't surface a wedge, that *is* the finding: Wedge ≤ 2.

## Step 1 — Map the incumbents (2 hrs)

For the candidate's job-to-be-done, list every solution the persona actually uses today:

- **Direct competitors** — named tools solving the same job. Per tool: pricing model + price points,
  review volume (app-store reviews, G2/Capterra count), visible traction (customers claimed, installs),
  and their 1–3★ review themes (the complaint mine).
- **Indirect/status-quo** — spreadsheets, manual process, hiring someone, doing nothing. What does the
  workaround cost in time/money?
- **Density verdict:** how many funded/established incumbents? Is the category consolidating (acquisitions
  happening — check `Acquirer-Intelligence.md`) or fragmenting?

## Step 2 — Find the gap (1 hr)

From the 1–3★ reviews, forum complaints (S1 evidence), and pricing pages:

- **Underserved segment:** who do incumbents serve badly? (Too enterprise, too expensive at low volume,
  GMV-priced, wrong platform, ignores a sub-persona.)
- **Underserved job:** what part of the workflow do they all skip or do badly? (The accuracy complaints,
  the missing integration, the report nobody trusts.)
- **Structural openings:** pricing-model misfit (flat vs usage), platform shift, regulation/why-now the
  incumbents are slow to absorb, agent-native surface none of them expose.

## Step 2.5 — Pricing corridor + buyer-map validation (1 hr)

Two S4-fidelity upgrades of what S0/S2 asserted (rubric v3.1 directives — economics ladder + buyer map):

- **Pricing corridor (the S4 rung of the economics ladder):** from the Step 1 incumbent price points,
  state the corridor we can defensibly charge (floor = the cheapest credible incumbent/workaround, ceiling
  = the value anchor, e.g., dollars recovered). Refine the S2 mini pro-forma at the corridor floor: COGS/unit
  (tokens at realistic model routing, infra, pass-throughs) → GM% — **re-check the ≥50% margin-floor gate at
  the corridor FLOOR, not the hoped-for price.** If the wedge is "cheaper than incumbents," this is where
  cheap-enough-to-win meets margin-enough-to-sell.
- **Buyer-map validation:** verify each buyer the Scorecard named — does a *specific portfolio asset or deal*
  evidence appetite for this exact asset class? Reclassify each as **thesis-buyer** (portfolio-adjacent,
  cited) / **size-class buyer** (buys our shape at some scale, no thesis fit) / **plan-of-record venue**
  (Acquire/Flippa on TTM profit), with the MRR/age milestone at which each becomes reachable. A famous name
  that survives only as "size-class" is not Acquirability-bonus evidence — re-score S2 if the map changed.

## Step 3 — State the wedge (1 hr)

Dunford-style, one page:

```
TEARDOWN — <candidate>
Incumbent map: <table: tool | price | traction proxy | top 1-3★ complaint themes>
Status-quo alternative: <what non-buyers do + what it costs them>
Market density: <count + consolidation trend>  → suggested Wedge score: <1-5, with the rule:
  1-2 = entrenched incumbents, no exploitable gap; 3 = real gap but incumbents could close it fast;
  4-5 = clear underserved segment/job + a reason incumbents won't follow>
The wedge (if any): <for [underserved segment], unlike [incumbents], we [gap] because [structural reason]>
Positioning: <category frame + differentiated value, 2-3 lines>
Pricing corridor: <floor–ceiling + basis>  → GM at corridor floor: <%>  → margin_floor gate: PASS/FAIL
Buyer map (validated): <buyer → evidencing portco/deal → thesis/size-class/venue → reachable at <milestone>>
Switch-test targets: <the exact complainers/reviewers who voiced the gap — feed S5's warm probe>
Confidence: <High/Med/Low + what would change it>
```

## Rules

- **The Wedge score in S2/`rubric.json` must cite this document.** No teardown → no trusted Wedge → no S5.
- **A wedge invented after scoring doesn't count.** If the teardown finds a wedge the Scorecard didn't
  reflect, re-score in S2 (that's the system working); don't retro-fit the narrative.
- **"Agent-native" alone is not a wedge** unless the teardown shows the persona *wants* an agent surface
  and incumbents structurally can't ship one. Differentiation must be priced by the buyer, not by us.
- **Feed S5:** the switch-test target list (named complainers with links) is a required output — it makes
  the mandatory switch test executable in hours instead of days.
- **The Acquirability score must cite the validated buyer map** (like Wedge must cite this teardown). If
  validation demotes a named buyer to size-class-only, S2 re-scores — don't let a name-drop keep its bonus.
- **Margin verdicts use the corridor floor.** A candidate that only clears 50% GM at an aspirational price
  hasn't cleared it.

## Compounding

Log to `sourcing-log.md`: teardown verdict vs. later reality (did the wedge hold post-launch? did an
incumbent close the gap?). M2 uses this to calibrate how much Wedge predicts traction.
