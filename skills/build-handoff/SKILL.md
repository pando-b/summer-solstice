---
name: build-handoff
description: >-
  Turn a validated idea into a shipped, agent-native v1 by orchestrating the compound-engineering plugin —
  with maximum automation and just three human checkpoints. Use this skill after the Demand Confidence Gate
  (Recipe #5) returns BUILD, whenever the user wants to "build it", "ship this", "start the build", "hand
  this to compound engineering", "run ce-brainstorm/ce-plan/lfg", or move an approved idea into development.
  This is Recipe #6 of the Summer Solstice recipe book. It does NOT replace compound engineering — it feeds
  and steers it: assembles a Build Brief, runs the CE loop with human gates at requirements and plan, lets
  /lfg build autonomously, and gates the human on an Evidence Pack (demo + release notes), not the PR diff.
  Runs in Claude Code where the CE plugin and build environment live.
---

# Build Handoff (Recipe #6)

Take an approved idea (a BUILD verdict from Recipe #5) and drive it to a shipped, agent-native, exit-ready v1 — fast, mostly hands-off, and on-spec. **This skill orchestrates compound engineering; it does not reimplement it.** CE does 100% of the building, reviewing, and demo/release-note generation. S6's value is the **Build Brief** (so CE builds the *right* thing), the **checkpoint sequence**, the **Evidence Pack gate**, and the **two-layer compounding**.

## Runtime & prerequisites (Claude Code)

This skill runs in Claude Code, not Cowork — it invokes CE commands and needs the real build environment:

- compound-engineering plugin installed: `ce-brainstorm`, `ce-plan`, `/lfg`, `ce-code-review`, `ce-compound`, `demo-reel`, `feature-video`, `ce-test-browser`.
- The product repo/worktree; `agent-browser` CLI, `gh` auth, and `ffmpeg` for the demo capture.
- `Operating-System.md` available as the `ce-strategy` `STRATEGY.md` anchor.

## Inputs

The Recipe #5 output: the candidate (problem/persona/venue/evidence from Recipe #1), the **pre-set "alive" metric**, the chosen distribution channel, and the maxims/constraints.

## Step 1 — Assemble the Build Brief (the value-add)

Compile one brief that front-loads everything CE needs to build the *right* thing. Without this, the autonomous run drifts to whatever CE defaults to. Include:

- **What & for whom:** the problem, persona, venue, and the evidence behind the BUILD verdict.
- **Success:** the pre-set alive metric + kill window (so Track 3 can later judge "alive") — plus the
  **W1/W4 cohort-retention instrumentation requirement** (it ships in v1, not later).
- **Distribution:** the pre-chosen $0 channel (so the build supports it — e.g., listing requirements).
- **Non-negotiables as build constraints:**
  - **Agent-native (our default product form):** architected so the agent is a first-class user — the agent can do anything the UI can (parity); atomic tools; features as prompts. Agent-native is a *form*; a CLI is a separate *technique* — being agent-native does **not** mean "ship a CLI."
  - **Not a thin wrapper:** real workflow ownership, a data moat, or switching cost.
  - **Owner-independent & transferable from day one:** SOPs, no key-person setup, documented — it's a sellable asset.
  - **Exit-first acquirability signals:** recurring-revenue-ready, sticky; include the **validated buyer map from S4** (buyer → evidencing portco/deal → thesis/size-class/venue → reachable-at milestone), not bare names from `Acquirer-Intelligence.md`.
  - **Budget:** within the <$2k pooled cap.
- **v1 pro-forma + margin guardrails (S6 rung of the economics ladder — build constraints, not commentary):**
  price point + billing rail from the S4 pricing corridor; COGS model (token spend at expected volume, infra,
  pass-throughs like SMS/data APIs; support-hrs budget separately as SDE); **GM target ~75–80%, 50% floor**;
  and the guardrails that keep it true as constraints CE must implement — cheapest-capable-model routing,
  prompt caching, metering/fair-use caps on the agent surface, optional BYO-key for heavy users. The retry/
  workflow brain stays deterministic; agent-native means the agent can OPERATE the tool, not that the tool
  IS the model.
- **CLI-leverage check (do NOT force a CLI as the product):** explicitly ask *where, if anywhere, a CLI raises quality* —
  1. **as the product interface** (when the users are power-users/agents),
  2. **as an agent-facing surface inside a GUI product** (the Van Horn/Steinberger pattern: a token-efficient CLI/MCP behind the UI, local-SQLite-mirror beats remote API, compound commands beat round-trips), or
  3. **only in building the product** (dev-time CLIs for the agent).
  Apply CLIs where they genuinely improve the user outcome or build quality; if none apply, don't add one. Record the decision and the reasoning in the brief.

## Step 2 — `ce-brainstorm` → requirements  🔲 GATE 1

Seed `ce-brainstorm` with the Build Brief to produce a right-sized requirements doc. **Human checkpoint:** you approve or edit the requirements. (This is where correction is cheapest.)

## Step 3 — `ce-plan` → implementation plan  🔲 GATE 2

Run `ce-plan` from the approved requirements. **Human checkpoint:** you approve or edit the plan.

## Step 4 — `/lfg` → autonomous build

Run `/lfg` for hands-off execution: build → **multi-agent `ce-code-review`** (different agents for security, architecture, quality) → tests → commit → PR → CI until green. No per-gate permission here; the gates are before (plan) and after (evidence).

## Step 5 — Evidence Pack → 🔲 GATE 3 (review the work, not the diff)

Generate the artifacts that let you judge what shipped:

- **Demo:** `demo-reel` for CLI products (captures CLI interactions) or `feature-video` for products with a UI (browser MP4). A 30–60s "here's what it does."
- **Release notes:** what shipped, in plain language.

Present the pack to the human. **You approve the evidence, never the PR diff.** (`feature-video` also embeds the video in the PR — that's just a record; your review surface is the pack.)

## Step 6 — Acceptance check (our lenses CE doesn't know)

A quick checklist before launch; fail any → loop back:

- Agent-native parity (agent can do what the UI can)?
- Not a thin wrapper (real workflow ownership / data moat / switching cost)?
- Owner-independent + documented (transferable asset)?
- Where a CLI was used, is it token-efficient and does it improve the outcome?
- The pre-set alive metric is instrumented?
- **Cohort retention instrumented (W1/W4 activation-retention wired before launch)?** Buyers price churn;
  a product that can't measure its own retention can't ever prove the exit case. Non-negotiable.
- **Support/ops budget written (est. hrs/week, who answers tickets, canned-response/triage doc)?** Every
  live product costs ~5–10 hrs/week post-launch; S15 needs this number to allocate honestly.
- **Per-customer COGS instrumented (token + infra cost per customer tracked from day one)?** S15 compares
  actuals vs. the pro-forma weekly; a product that can't measure its own gross margin can't prove it to a
  buyer. Non-negotiable, same class as retention instrumentation.
- Evidence Pack produced?

Run this as **parallel specialized reviewer subagents** where it helps, mirroring CE's multi-agent `ce-code-review`: an **acquirability reviewer** (recurring-revenue readiness, switching cost, owner-independence, fit to a named buyer in `Acquirer-Intelligence.md`) and a **transferability reviewer** (clean docs, no key-person dependencies, transferable stack/accounts). Each returns pass/fail + findings; aggregate them. Fall back to an inline check if subagents aren't available.

## Step 7 — Compound (both layers — don't skip)

- **Per-product / code-level:** run `ce-compound` so learnings are written into the product's repo and the next build of *it* is faster.
- **Cross-product / business-level:** append what we learned (about this build *and* the path that produced it) to the Compounding Log (M2) / `sourcing-log.md`, and fold real improvements back into the recipe-book skills. **This is how the whole system — sourcing, scoring, building, launching — compounds, not just one codebase.**

## Step 8 — Hand off to S11 (Launch)

Pass the built artifact + the chosen channel to Recipe #5/S11's launch step. **Reuse the Evidence Pack (demo + release notes) as launch & build-in-public content** — the gate artifact is also the marketing artifact.

## Output format

```
BUILD HANDOFF — <product / candidate>
Build Brief: <link/summary; CLI-leverage decision + reasoning>
Gate 1 (requirements): approved/edited — <notes>
Gate 2 (plan): approved/edited — <notes>
/lfg: <status — PR link, CI green?>
Evidence Pack: <demo link> + <release notes link>
Gate 3 (evidence): approved? — <notes>
Acceptance check: <pass/fail per item>
Compound: ce-compound done? + cross-product learnings logged?
Handoff to S11: channel + reused content
```

## Principles / anti-patterns

- **Don't rebuild CE.** Orchestrate it. If you're writing build logic here, stop.
- **Don't force a CLI as the product.** Agent-native is a capability; CLI is a technique used where it helps.
- **Review evidence, not diffs.** The human gate is the Evidence Pack.
- **Keep it to three human gates** (requirements, plan, evidence); everything else autonomous.
- **Never skip compounding.** A build that doesn't make the next build (and the recipe book) easier wasted half its value.
