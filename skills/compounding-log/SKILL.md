---
name: compounding-log
description: >-
  Make the whole venture system compound — capture what worked and failed across products and fold concrete
  improvements back into the recipe-book skills, so each week is faster and sharper. Use this skill for the
  weekly review/retro, when the user says "what did we learn", "update the recipe book", "compound the
  learnings", "calibrate the gates", "weekly compounding", or at the end of a build/launch cycle. This is the
  M2 meta-skill of the Summer Solstice recipe book — the business-level twin of compound engineering's
  `ce-compound` (which compounds one codebase). Without it, the sprint is 12 disconnected attempts; with it,
  it's a learning system.
---

# Compounding Log (M2)

The engine behind "the recipe book gets better every week." `ce-compound` makes a single *codebase* compound; this makes the *whole system* compound — sourcing, scoring, demand-testing, building, launching — by comparing what we predicted to what actually happened and editing the skills accordingly.

## Cadence

Run weekly (the Sunday "Compound" step of the conveyor). Can be wired to a scheduled task. Also run after any product hits a milestone or dies.

## Step 1 — Log the cycle (per product)

Append to `compounding-log.md` (and keep `sourcing-log.md` in sync):

- **Seed (S0):** the seed + its market-attractiveness score.
- **Sourcing (S1):** which probes/sources yielded the candidate.
- **Scoring (S2):** the Scorecard scores + verdict.
- **Demand gate (S5):** the *predicted* confidence (High/Med/Low) — to be compared with reality.
- **Build (S6):** notable build notes + the CLI-leverage decision.
- **Launch (S11):** channel(s) + result.
- **Traction (S15):** current alive metric / MRR / retention.

## Step 2 — Calibration loops (the heart)

Compare **predicted vs actual** and turn the gaps into edits:

- **S5 confidence vs outcome:** did "High" ideas actually get usage/revenue? If High-confidence ideas keep dying, the kill bar is too loose — tighten it. If killed ideas later succeed elsewhere, it's too tight.
- **S0 attractiveness vs winners:** which seed *lenses* produced products that got traction? Re-weight the lenses toward those.
- **S2 scores vs traction:** which Scorecard criteria actually predicted success? Re-weight; retire criteria that don't discriminate.
- **S1 probes vs yield:** which probe patterns surfaced real candidates? Promote them; drop dead ones.
- **S11 channels vs activation:** which channels converted for which product types? Update the channel bullseye defaults.

This is Pincus's point made systematic: sharpen instinct with feedback, don't trust it blindly.

## Step 3 — Fold improvements back into the skills

For each calibration finding, produce a concrete edit and apply it:

- re-weight the rubric — edit **`rubric.json` first** (via S2, its keeper), then regenerate the mirrors (xlsx, OS-doc §7, S2's tables),
- promote/retire probe patterns in Opportunity Sourcing (S1),
- adjust the Demand Confidence Gate kill bar (S5),
- update the channel bullseye defaults in Launch (S11),
- add a new skill if the same manual work recurred three times (the agent-native latent-demand rule).

**Human gate:** propose the edits with rationale; the human approves significant changes (light touch — small re-weights can be auto-applied, structural changes get a yes).

**Anti-overfit guardrails (External Review #01):** rubric weight edits require **n≥3** logged product
outcomes pointing the same way; structural changes (gates or criteria added/removed) require **n≥5** or an
unambiguous external fact (e.g., a channel's payment rail doesn't exist). One rehearsal is a flag, not a
trend — log it and wait.

**Rubric-sync check (run every week, non-negotiable):** verify `rubric.json` agrees with all mirrors —
`Opportunity-Scorecard.xlsx` weights/gates, operating-system doc §7, and the tables in the
`opportunity-scoring` skill. Also verify no *other* skill restates the rubric (S1 once drifted to v1
silently — that's how External Review #01 found it). Any mismatch is a bug: fix it now and log it.

## Step 4 — Publish the recipe-book changelog

Write a short "what changed in the recipe book this week and why" entry. This is the visible proof the system is compounding — and the running record of how the playbook was earned.

## Output format

```
COMPOUNDING LOG — week of <date>
Cycles logged: <products>
Calibration findings:
  • <predicted vs actual> → <edit>
Edits applied / proposed: <skill → change → rationale>  [✓ applied | 🔲 needs approval | ⏸ awaiting min-n]
Rubric-sync check: <rubric.json vs xlsx vs OS-doc vs S2 tables — PASS/FAIL + fixes>
Recipe-book changelog: <1–3 lines>
Next-week bias: <what we'll do differently>
```

## Anti-patterns

- **Logging without acting.** A log that doesn't change a skill is journaling, not compounding.
- **Recency bias.** Use the full history, not just last week.
- **Over-fitting to one product.** Re-weight on patterns across several, not a single outlier.
- **Skipping the human gate on structural changes** — small re-weights auto-apply; rubric/skill restructures get a yes.
