---
name: launch-distribution
description: >-
  Get a shipped product in front of buyers through a pre-chosen, $0 channel — fast. Use this skill right
  after a product is built (Recipe #6), whenever the user wants to launch, "go to market", "get users",
  "where do I post this", "distribution plan", "launch on Product Hunt / Shopify / the skill stores", or
  decide which channel to focus. This is Recipe S11 of the Summer Solstice recipe book. It picks ONE or two
  channels with a Traction-style bullseye (never sprays), reuses the S6 Evidence Pack as the hero asset,
  instruments the "alive" metric, and hands results to the Grow/Sell/Kill gate. Distribution is chosen
  BEFORE the build (maxim #4) — this skill executes and measures it.
---

# Launch & Distribution (S11)

Turn a shipped v1 into real users/buyers via the channel we picked *before* building. The job is focus and speed, not spray-and-pray: pick the 1–2 channels where this product's audience already is, launch with assets we already have, and read the one metric that decides whether it lives.

## Principles

- **Distribution before build** (maxim #4): the channel should already be chosen — this skill executes it. If it wasn't, pick it now before launching.
- **$0 channels only** (budget): earned/owned/ecosystem distribution, not paid acquisition.
- **Go where the audience already is** — the seed's persona+venue tells you; ride existing ecosystems.
- **Bullseye, not buckshot** (Weinberg & Mares, *Traction*): rank candidate channels, bet on the top 1–2, focus.

## Inputs

From S6: the built artifact + the **Evidence Pack** (demo + release notes) + the pre-set **alive metric**. From upstream: the seed's persona/venue, pricing (S8).

## Step 1 — Channel bullseye

List candidate channels, rank by fit for *this* product + audience, pick the top 1–2, and focus. **For each
candidate channel, record its clock: review/moderation latency (Shopify App Store: 2–4+ weeks in practice —
"build Tuesday, launch Friday" is fiction for app stores), whether a payment rail exists in-channel, and
expected time-to-first-100-qualified-users.** These numbers should already be on the Scorecard (Free
Reachability sub-signals); verify them now against reality. The free-channel menu:

- **Agent skill stores / registries** — Claude Code marketplace, OpenClaw/ClawHub, Hermes, the Printing Press Library, MCP registries, `npx skills add`. **Hypothesis-under-test, not proven GTM:** these channels have **no payment rail** (top earners on third-party skill markets report ~$500–3k/mo), and the pattern's proof case (Van Horn) converted stars into reputation, not revenue. Use as top-of-funnel/credibility for dev-facing products — but a product distributed here must have a **named monetization mechanism elsewhere** (it's a Scorecard kill gate), and installs→paid conversion gets logged to M2 with its own kill bar.
- **Platform app stores** — Shopify, WooCommerce, Chrome, Slack, Salesforce AppExchange. Built-in distribution (Walling's existing-ecosystem); leans on any warm ecosystem hook you declared at S0.
- **Owned audience / build-in-public** — your strongest owned channels (LinkedIn/X/newsletter). Post the Evidence Pack demo as the launch.
- **Timed launches** — Product Hunt, Show HN — for products that suit them; one-shot, prepare properly.
- **Warm direct outreach** — reach the *exact* people who voiced the pain (found in Recipe #1) via a contact-lookup CLI (`contact-goat`). Compliance guardrail: personal, CAN-SPAM/GDPR-aware, respect platform ToS, run legal `compliance-check` before any scale — hand-written, not blasts. Never depend on cold-community standing (Reddit karma is slow/unreliable).
- **SEO / programmatic** — slower; a later compounding channel, not a launch-day move.

## Step 2 — Launch motion (fast)

1. Prep the listing/page with the **Evidence Pack as the hero asset** (demo + release notes — don't recreate assets).
2. Pricing live (from S8) — charge from day one where possible.
3. **Instrument the alive metric** (S10) before you drive traffic.
4. Publish to the chosen channel(s).
5. Run the warm outreach (compliant) and the build-in-public post.

## Step 3 — Measure & hand off

Read the **alive metric within its pre-set window** (e.g., first paying customer / ≥X activations in 14 days). **The window starts when the channel goes *live* (listing approved, indexed, installable) — never when the build ends.** Killing a product because its app-store review queue hasn't cleared is a channel-latency artifact, not market feedback, and it mis-calibrates M2. Read W1 activation-retention alongside first dollars. Pass the result to **S15 (Grow / Sell / Kill)** for the weekly verdict.

## Compounding (every launch)

Log channel → activation/revenue by product type in the Compounding Log (M2). Re-weight the channel bullseye next time toward what actually converted for this kind of product. Over the sprint this turns channel selection from guesswork into a calibrated default.

## Output format

```
LAUNCH — <product>
Channel bullseye: <candidates → chosen 1–2 + why; per channel: review latency / payment rail / time-to-100-users>
Assets: <Evidence Pack links reused>
Pricing: <live? tiers>
Alive metric: <instrumented? definition + window — window starts at channel-live>
Launched: <links/dates per channel> | Warm outreach: <count, compliant?>
Result (in window): <metric reading>
Handoff to S15: <keep / double-down / kill signal>
```

## Anti-patterns

- **Spraying every channel.** Bullseye = focus 1–2.
- **Depending on cold-community standing.** Use warm/owned access.
- **Launching without the alive metric instrumented.** Then you can't judge it.
- **Recreating assets.** Reuse the S6 Evidence Pack.
- **Picking the channel at launch.** It should have shaped the build.
