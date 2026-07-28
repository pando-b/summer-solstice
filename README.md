# Summer Solstice

**An open-source, agent-native venture system: 9 chained skills that take you from "what should I build?" to a shipped, revenue-generating, *sellable* product — with a scoring rubric that gets smarter every time anyone runs it.**

Built for solo founders and tiny teams running bootstrapped sprints with Claude Code. No VC, no permission, under $2k.

---

## Why this exists

Most indie products fail before they're built — wrong market, invented demand, no path to buyers, no way to charge, unsellable by design. Summer Solstice is a **disciplined, evidence-gated pipeline** that attacks each failure mode with a codified skill, and — the part that compounds — **logs its own predictions vs. outcomes and re-weights itself**.

It was built (and is used, live) to run a real venture sprint. Its calibration history is public: every rubric change traces to logged evidence, not vibes. It has already killed its own ideas — the worked examples in `examples/` show it happening.

## The method in one paragraph

Pick where to hunt (**S0**) → mine dated, engagement-backed pain with [last30days](https://github.com/mvanhorn/last30days-skill) (**S1**) → score against a canonical machine-readable rubric with 7 kill gates: free channel, one-week build, legal, budget, no-wrapper, payment rail, ≥50% margin floor (**S2**) → tear down the incumbents so the "wedge" score is evidence, not vibes (**S4**) → prove demand for *you*, not the category — in crowded markets that means a switch test: 3 humans who pay a competitor commit (**S5**) → build an agent-native v1 in a week via [compound engineering](https://github.com/EveryInc/compound-engineering-plugin), with cohort retention instrumented from day one (**S6**) → launch into a pre-chosen $0 channel (**S11**) → weekly portfolio verdict: double-down / maintain / sell / kill, with a 3–4 live-product cap and a breakout-halt rule (**S15**) → log predicted-vs-actual and re-weight the rubric (**M2**). Exit-first throughout: every candidate is scored on what an actual sub-$10M acquirer would pay for, on the trailing-profit basis they really use.

## The 9 skills

| Skill | Stage | What it does |
|---|---|---|
| `seed-market-selection` | S0 | Ranked market seeds (persona + pain + venue) via 5 lenses + margin sanity |
| `opportunity-sourcing` | S1 | Mines dated, engagement-backed pain; anti-hallucination evidence gate |
| `opportunity-scoring` | S2 | Scores against `rubric.json` (the canonical, community-calibrated rubric) |
| `positioning-teardown` | S4 | Half-day incumbent teardown — the evidence behind every Wedge score |
| `demand-confidence-gate` | S5 | Kill-first demand gate; switch test mandatory in crowded markets |
| `build-handoff` | S6 | Orchestrates compound engineering; 3 human gates; retention instrumented in v1 |
| `launch-distribution` | S11 | $0-channel bullseye; channel-clock aware (review latency, payment rail) |
| `grow-sell-kill` | S15 | Weekly portfolio verdict; product cap; breakout-halt; TTM-honest exit triggers |
| `compounding-log` | M2 | The engine: predicted-vs-actual → rubric/skill edits, with min-n governance |

## Install (2 commands)

```
/plugin marketplace add pando-b/summer-solstice
/plugin install summer-solstice@summer-solstice-marketplace
```

Then set up your working directory: **copy the contents of `templates/` — plus `acquirer-intelligence/Acquirer-Intelligence.md` — to your project root.** The skills read `rubric.json`, `Opportunity-Scorecard.xlsx`, `Operating-System.md`, `Acquirer-Intelligence.md`, and the two logs from wherever you run Claude Code, so all six sit flat at the root. Fill in the placeholders in `Operating-System.md` — your goal, budget, founder hooks — and run:

> "Seed the pipeline — run seed-market-selection."

Dependencies: [compound-engineering](https://github.com/EveryInc/compound-engineering-plugin) (for S6 builds) and [last30days](https://github.com/mvanhorn/last30days-skill) (for S1 sourcing; free sources work with zero keys).

## The community calibration loop (what makes this different)

`rubric.json` is not a static opinion — it's a **living instrument with a changelog**, and the M2 skill defines how it changes: log a prediction, log the actual, propose an edit with evidence. This repo opens that loop to everyone:

- Run your own sprint. When your predicted-vs-actual diverges — a probe pattern that over/under-delivers, a channel whose latency killed a launch, a criterion that didn't predict traction — submit a **calibration entry** (template in `CONTRIBUTING.md`). **No opportunity-specific data required**: you contribute what the *system* got wrong, never what you're building.
- Weight changes merge when pooled evidence clears the governance bar (**n≥3** independent outcomes for re-weights, **n≥5** or an unambiguous external fact for structural changes) — the same anti-overfit rule the system applies to itself.
- Every merged change lands in the `rubric.json` changelog with its evidence. The rubric you install is the sum of every sprint that came before yours.

The same loop applies to `acquirer-intelligence/` — buyer criteria drift constantly; row-level updates with a source link and a `last-verified` date are the easiest first contribution.

## What's in the repo

```
.claude-plugin/          plugin + marketplace manifests
skills/                  the 9 skills (SKILL.md each)
templates/               rubric.json · blank Scorecard · Operating-System doc · blank logs
acquirer-intelligence/   the sub-$10M buyer database (criteria, minimums, TTM/age reality flags)
examples/                real worked examples — including the system killing its own candidate
CONTRIBUTING.md          calibration-entry format + governance + PR checklist
```

## Honest limitations

- The exit math is stated on the basis micro-acquirers actually use (~3–4x **trailing** profit, not run-rate ARR). Products need months of retention history before $1M-class outcomes are realistic. The system optimizes for getting there without lying to you en route.
- "Ship fast" survivorship bias is real. This system's answer is kill-gates and pre-registered thresholds, not optimism. Expect most candidates to die at S5 — that's the design.
- Skill-store distribution has no payment rail; it's treated as a hypothesis under test here, not proven GTM.

## Provenance & license

Extracted from a live 90-day venture sprint (started June 2026). The rubric's changelog is the audit trail of how it was earned — including an adversarial external review that found and fixed the system's own worst assumptions. MIT license. Maintained by [Ben Armstrong](https://github.com/pando-b).
