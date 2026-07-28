---
name: demand-confidence-gate
description: >-
  Decide fast whether an idea earns a build week — by killing most of them. Use this skill after an
  opportunity has been scored and you're deciding whether to build, whenever the user asks "should I build
  this", "is this worth building", "validate this idea", "demand test", "will anyone pay", "kill or build",
  or needs a pre-build go/no-go. This is Recipe #5 of the Summer Solstice recipe book — the gate between
  scoring and building. Its default verb is KILL: it earns confidence from data you already have (revealed
  preference, existing spend, engagement intensity) in hours, not weeks, and only lets insanely-high-confidence
  ideas through. Use it instead of slow "validation" theater (smoke pages, week-long waitlists, cold-community
  posting), which is too slow for a one-week build cycle.
---

# Demand Confidence Gate (Recipe #5)

The gate between *scoring* (Recipe #2) and *building* (Recipe #6). A high Scorecard score says a problem is real and painful; it does **not** say anyone will pay. This skill's job is to earn — fast and cheaply — a real signal of demand, and to **kill most ideas** so only the highest-confidence ones consume a precious build week.

## Philosophy (why this works)

Mark Pincus's bar: **a click is not validation — retention, usage, and an emphatic "10 out of 10 would use this" are.** And "your instincts are right ~95% of the time, but your ideas are wrong ~75% of the time" — so we don't trust the idea, we look for evidence the *demand already exists*. In the AI era the build is nearly free and fast, which flips the old logic: faking demand with a smoke page often costs more time than just building the thin real thing and watching whether people use it.

So this gate is **falsification-first** (try hard to kill the idea) and **signal-first** (use data you already have before running any new test). Confidence must be *earned*; the default outcome is *kill*.

## When to use

After a candidate clears the Scorecard (≥75) and before it enters a build week. Input: the scored candidate from Recipe #1 — problem, persona, venue, and the evidence already gathered.

## The three tiers

Run them in order. Most ideas die in Tier 1. Escalate only when needed.

### Tier 1 — Signal proof (default; hours; ~$0)

Look for **revealed preference**, not opinions. Reuse `last30days` and targeted pulls to check, with dated, linkable evidence:

- **Existing spend:** are people already paying for inferior tools or hacking workarounds? (Competitor pricing pages, revenue/Latka, install counts, app-store review volume, "I pay for X and it still sucks.") Money already moving is the strongest signal.
- **Demand intensity & recency:** high-engagement complaints in the last ~30 days (upvotes, comments, views) — and is it emphatic, the Pincus "10/10 fuck-yes," or merely lukewarm?
- **Search/market pull:** keyword/"alternatives to X" demand, rising interest.
- **Spend-by-proxy:** people hiring or doing the task manually = budget exists.

Convergent, strong, recent signals → **High** confidence. Anything thin or lukewarm → **kill**. This tier alone should kill most candidates.

**Hard cap (External Review #01): category evidence can never clear the gate alone in a crowded market.**
Competitor spend proves the *category* wins — A2X's 13k customers validate A2X, not a new entrant. In any
market with entrenched incumbents (**Competitive Wedge ≤ 3 on the Scorecard**), Tier 1 caps at **Medium**
regardless of how strong the category signals are, and the **switch test** (Tier 2) is mandatory. In a
crowded space, heavy existing spend is evidence *against* an easy entry, not for one.

### Tier 2 — One warm probe (if Tier 1 is ambiguous, or mandatory as the switch test; 1–2 days max)

**The switch test (mandatory when Wedge ≤ 3):** find **≥3 target-persona humans who currently pay a
competitor** and get a real commitment from each — a pre-order, a paid pilot, or an explicit, specific
"I'd switch because ___" in a Mom-Test-style conversation. Politeness doesn't count; a named reason to
switch or money does. Fewer than 3 commitments within 2 days → **kill**. This is the only cheap signal
that de-risks *your* build rather than the incumbent's category.

Use access you **already** have — never gate on building new community standing (earning Reddit karma is slow and unreliable; don't depend on it).

- **Pre-sell / paid pilot** to known prospects — take a deposit or a card. Money committed is the cleanest signal.
- **Targeted warm outreach to the exact people who voiced the pain.** Recipe #1 already surfaced specific complainers; a contact-lookup CLI (e.g., Printing Press's `contact-goat`: LinkedIn → warm-intro graph → verified email) can reach them. Send a short, specific, personal offer of a fix — not a blast.
  - **Compliance guardrail (do not skip):** cold email to found contacts is regulated. Keep it permission-aware and personal, honor CAN-SPAM (identify yourself, easy opt-out) and GDPR/region rules, and respect each platform's ToS on scraping/automation. Before doing this at any scale, run the legal `compliance-check`. A handful of hand-written, relevant messages is fine; an automated blast is both legally risky and a weaker signal.
- **Offer to your own audience** (LinkedIn/email/network) where you already have reach.

A real commitment (a pre-order, a paid pilot, a "yes, take my money / when can I have it") → pass. Silence or politeness → kill.

### Tier 3 — Build-as-the-test (the AI-era move)

For ideas that are **high-confidence on pain but unproven on willingness-to-pay**, the cheapest *real* test is to build the thin real thing (one week, agent-native) and launch it where the audience already lives — an existing app store/ecosystem, the Printing Press Library, or your own audience — then measure the only signals that count: **usage, retention, and first dollars**. Building beats faking when building is this cheap. (This hands off directly into Recipe #6 with a pre-set "alive" metric.)

**Tier-3 eligibility rule (added 2026-07-07, owner directive — the no-outreach path).** Tier 3 REPLACES
outreach as the demand test when ALL of these hold:
1. The pre-chosen channel has **organic discovery** (directory/store search, SEO surface) — buyers find the
   product without us messaging anyone. Build-as-the-test measures *our* demand, not the category's, which
   is the very failure the switch test protects against — but only if discovery is organic.
2. An **instant payment rail** exists — charge from day one; first dollars are the zero-interpretation signal.
3. The **pre-registered alive metric + kill window ship in v1** (instrumented, read in Week B). The
   falsification discipline moves post-launch; it does not disappear. No bar → no Tier-3 pass.
4. The build is cheap and inference-light/within the build week (true by construction after S2's gates).

**Boundary (External Review #01 protection stands):** at **Wedge ≤ 3 the switch test remains mandatory and
Tier 3 cannot substitute for it.** A Wedge ≤ 3 candidate whose channel is **outreach-dependent** (forum-DM,
FB-group, 1:1 motions — no organic discovery) is **BANKED** for a cell where outreach is accepted — never
rationalized through the no-outreach path.

**No-outreach demand tactics (use in place of, or alongside, warm probes):**
- **Upgrade-intent doors:** free tier ships with Pro visible; a click on "Upgrade" before Pro is finished is
  purchase-intent telemetry from a real user inside a real workflow — stronger than any stated "I'd pay."
- **Real checkout from day one:** a hosted checkout (Stripe, Paddle, or whatever billing rail your channel
  supports) costs about an hour to add.
- **Self-qualifying lead magnet:** a free diagnostic whose output quantifies the user's own pain
  ("this is costing you $X a month") — discovery converts itself into demand measurement.
- **Public revealed-preference data:** competitor install/download curves (most app stores and package
  registries publish counts), competitor waitlists (a waitlist IS a demand queue), search volume. Zero
  contact, already public.
- **Async broadcast ≠ outreach:** one launch post or demo video in the venue is publishing (S11's job),
  not 1:1 solicitation — the channel pulls or it doesn't.

## Gate logic

1. **Pre-register the kill bar** before looking (e.g., "needs ≥2 independent proofs of existing spend + emphatic intensity"). This stops you rationalizing later.
2. Score confidence **High / Medium / Low** from Tier 1. **If Wedge ≤ 3, Tier 1 caps at Medium — no exceptions, no "signal proof may clear it without a test."**
   - **High →** advance to build (Tier 3), with a pre-set alive-metric and kill window.
   - **Medium →** one Tier 2 warm probe (the switch test, if Wedge ≤ 3); pass → build, fail → kill.
   - **Low →** kill, log why.
3. **Bias to kill.** The sprint's scarce resource is build-weeks; protect them. Killing fast is winning.

## Output format

```
DEMAND CONFIDENCE GATE — <candidate / persona>
Wedge score (from Scorecard): <n>  → switch test mandatory? <Y/N>
Pre-registered kill bar: <what would have to be true to pass>
Tier 1 signals:
  • Existing spend: <evidence + link + date>
  • Intensity/recency: <evidence + engagement metric + link>
  • Search/market pull: <evidence>
  • Spend-by-proxy: <evidence>
Economics check (S5 rung): <does what these people ACTUALLY pay today support the S4 pricing corridor?
  If the revealed spend sits below the corridor floor, the margin_floor PASS is stale — flag before BUILD>
Confidence: High | Medium | Low
Decision: BUILD | ONE WARM PROBE | KILL
If BUILD → pre-set "alive" metric + kill window: <e.g., ≥1 paying customer or ≥X activations within 14 days>
If WARM PROBE → exact probe + pass/fail threshold + deadline (≤2 days)
If SWITCH TEST → the 3+ named prospects, what each currently pays for, and each one's commitment/reason
Rationale: <2–3 lines>
```

## Speed rules / anti-patterns

- **No smoke pages as proof.** A click measures curiosity, not demand.
- **No week-long waitlists.** They burn the build week they're meant to protect.
- **No cold-community standing-building.** If a probe needs karma/clout you don't have, it's not fast — skip it.
- **Cap the whole gate at ~1–2 days.** If you can't get to High or a clean warm-probe result quickly, the answer is kill.
- **Don't rationalize a weak signal into a build.** When unsure, kill — there's another candidate behind it.

## Compounding (do this every run)

Log the predicted confidence vs. the actual outcome (did built ideas get usage/retention/revenue? did killed ideas turn out to be missed winners elsewhere?) in `sourcing-log.md`. Over time this calibrates the gate — Pincus's whole point is to sharpen instinct with feedback, not to trust it blindly.
