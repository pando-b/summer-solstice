# Contributing to Summer Solstice

Two kinds of contributions make this system better. Both are welcome; the first is the special one.

## 1. Calibration entries (the community flywheel)

You ran the system. Something it predicted didn't match what happened. That divergence — not your product idea — is the contribution.

**What to share:** the system's error. **What never to share:** your market, candidate, evidence links, or anything that identifies what you're building. Calibration entries are *about the instrument, not the opportunity* — every field below can be filled at the process level.

Open an issue or PR titled `calibration: <one-line finding>` using this format:

```markdown
## Calibration entry

**Stage:** S0 | S1 | S2 | S4 | S5 | S6 | S11 | S15
**Predicted:** <what the system/rubric/skill said would happen — e.g., "S2 scored the
  candidate 82 (STRONG)", "S5 Tier-1 gave High confidence", "channel latency estimated <1wk">
**Actual:** <what happened — e.g., "died at switch test 0/5", "channel review took 5 weeks",
  "W4 retention 8% despite Natural Retention scored 4">
**Sample:** <n = how many independent candidates/launches this pattern covers in YOUR runs>
**Proposed edit:** <specific: which weight/anchor/gate/skill-line, from what, to what>
**Evidence class:** <process-level only — e.g., "3 candidates across 2 markets", never links
  to your pipeline>
**Context that matters:** <product type, channel type, market maturity — categories, not names>
```

### Governance (how edits merge — same rules the system applies to itself)

- **Weight/anchor re-weights:** pooled evidence across contributors must reach **n≥3 independent outcomes** pointing the same way.
- **Structural changes** (gates or criteria added/removed, skill-logic changes): **n≥5**, or an unambiguous external fact (e.g., "this channel has no payment rail" — verifiable, no sample needed).
- Every merged change gets a `rubric.json` changelog entry citing the pooled evidence (issue links).
- Maintainer holds the merge; disagreements argue evidence, not vibes — that's the house style.

Under the bar? Still submit. Entries accumulate; three people's n=2 is the community's n=6.

## 2. Skill, template, and database improvements

- **Acquirer-intelligence rows** — the easiest first PR. Buyer criteria drift constantly: update a row with a source link and set its `last-verified` date. New buyers welcome (public-source citations required; confidence-rate them).
- **Skill improvements** — sharper probe patterns (S1), teardown methods (S4), channel-clock data (S11), anti-patterns you hit. Keep the house style: evidence-gated, kill-first, time-boxed.
- **Templates/docs** — clarity fixes, setup friction, worked examples from *your* killed candidates (kills teach; live pipelines stay private — yours too).

## PR checklist (every PR)

- [ ] **No secrets, keys, tokens, or personal data** — yours or anyone's.
- [ ] **No live pipeline intelligence** — no active candidates, seed scores, S1–S5 outputs, or buyer maps for things you're currently pursuing. (Killed/archived candidates are welcome as examples.)
- [ ] Claims carry evidence (a link, a sample size, or a citation) — this repo's core rule.
- [ ] Skill edits keep each SKILL.md self-contained and under ~200 lines.
- [ ] If you touched `rubric.json`: changelog entry included, governance bar met, and the mirrors regenerated (Scorecard template + any skill tables that restate it).

## House principles (read before writing)

Data over opinion. Kill-first. Category evidence never proves entrant demand. Buyers price trailing profit. A rubric change without evidence is vandalism; with evidence, it's the whole point of the repo.
