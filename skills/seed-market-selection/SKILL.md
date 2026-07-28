---
name: seed-market-selection
description: >-
  Pick the right market to hunt in BEFORE sourcing opportunities. Use this skill at the very start of
  venture discovery whenever the user wants to choose which market/niche/audience to pursue, decide where to
  point research, find a space for a cheap, bootstrapped, acquirable product, or asks "what market should I
  go after", "where should we look", "help me pick a niche", "seed the pipeline", "what should I build"
  (at a market level), or "where is AI under-served but people still pay". It runs five proven lenses
  (Proven·Better·New, existing-ecosystem, reachable-audience / Sales Safari, AI-thin vertical, and
  acquirer-adjacent), scores candidate spaces on a market-attractiveness rubric, and outputs ranked SEEDS
  (persona + pain + venue) ready to feed the Opportunity Sourcing skill. This is Recipe #0 of the Summer
  Solstice recipe book — the front of the conveyor. Use it even when the user is thinking at a market level
  rather than a specific product.
---

# Seed / Market Selection (Recipe #0)

Generate intelligent **seeds** — the markets/niches we point Opportunity Sourcing (Recipe #1) at. Seed quality bounds everything downstream: a generic seed ("CRM software") yields generic candidates; a sharp seed (**persona + pain + venue**) yields scoreable, buildable, *sellable* opportunities. This skill exists because choosing *where to look* is the highest-leverage upstream decision in the whole sprint.

The output is a ranked set of seeds, each formatted to drop straight into Recipe #1's `seed` input.

## What a good seed is

**persona + pain + venue** — *who* has the problem, *what* the friction is, and *where* they congregate.

- Weak (a category): "project management", "AI for marketing", "CRM software".
- Strong (a seed): "independent HVAC contractors losing jobs to slow quoting (r/HVAC, Facebook trade groups)"; "solo bookkeepers reconciling messy client books (r/Bookkeeping, QuickBooks community)".

## Prerequisites & context

- Read `Operating-System.md` for the fixed constraints (agent-native, <$2k, ~6-month sellable, $0 distribution) and the maxims — every seed must respect them.
- Read `Acquirer-Intelligence.md` for the live list of active sub-$10M buyers — this powers the acquirer-adjacent lens and the scoring.
- Optional engines: `last30days` (to sense what's shifting/painful in a space and sanity-check spend & reachability) and web search / market reports. Keep research **light** here — deep pain-mining is Recipe #1's job. Recipe #0 only needs enough evidence to score the rubric and pick where to point.

## Inputs

- **Theme** (optional): an industry, interest, or founder hook to bias toward — your domain expertise, industry background, or a warm contact inside an ecosystem (declare your hooks in your operating-system doc). If none given, run wide.
- **N** (optional): number of seeds to return. Default 6–8.

The hard constraints (<$2k, fast revenue, sellable, a named way to charge) are always on — they are filters, not inputs. Agent-native is our default *architecture*, not a market filter (per External Review #01): don't drop a space because its buyers wouldn't pay extra for agent-nativeness. Favor spaces with **naturally recurring jobs** (feeds the rubric's Natural Retention criterion) over one-shot tasks.

## The five lenses (generate candidate spaces)

Generate ~15–25 candidate market-spaces by running each lens. Lenses overlap — the best seeds score well on several.

1. **Proven · Better · New** (Pincus — "all new fails"). Where is there *proven* demand we can copy and out-execute, then add something new? Bias hard toward proven; novelty is a garnish, not the meal.
2. **Existing-ecosystem** (Walling stair-step). Which platform's app store / registry gives built-in $0 distribution? Shopify, WooCommerce, Slack, Chrome, Salesforce AppExchange, the Printing Press Library. Riding an ecosystem is the fastest fix to the GTM problem.
3. **Reachable-audience / Sales Safari** (Hoy, Kahl). Which audiences congregate *observably* online (subreddits, Slacks, Discords, FB groups, forums) where we can both research and reach them for free? If you can't name the venue, it's not a seed.
4. **AI-thin vertical.** Which low-AI-adoption sectors still have real budget and reachable buyers — construction, skilled trades, local services, food service, hospitality, education? **Trap warning:** low adoption sometimes means "no real use case" or un-digitizable work. Only keep an AI-thin space if you can also show *existing spend* and a *reachable audience*.
5. **Acquirer-adjacent** (exit-first). Which spaces sit next to an active sub-$10M buyer (see `Acquirer-Intelligence.md`)? A space adjacent to a named aggregator, vertical roll-up, or strategic gap raises exit odds. Begin with the end in mind.

## Score each candidate (Market-Attractiveness rubric)

This is a **coarse filter** to choose where to point sourcing — lighter than Recipe #1's per-opportunity Scorecard. Score each 1 (weak) to 5 (strong).

| # | Criterion | Weight | 5 = strong when… |
|---|---|---|---|
| 1 | Reachable audience | 18 | a named, observable, $0-reachable community exists |
| 2 | Evidence of existing spend | 18 | people already pay for tools/workarounds here (proven demand) |
| 3 | AI gap | 14 | under-served by agent-native tooling, yet digitizable |
| 4 | Acquirer presence | 16 | a named active sub-$10M buyer is adjacent |
| 5 | Fit to constraints | 16 | agent-native-able, <$2k, fast to revenue, sellable in ~6 mo |
| 6 | Proven·Better·New headroom | 12 | a proven model exists to copy and improve |
| 7 | Founder hook (bonus) | 6 | leans on a real edge (e.g., fintech / WooCommerce) |

Market-attractiveness = Σ(weight × score) ÷ 5 → 0–100.

**Drop a candidate (don't seed) if any of these are true:**
- It's a **broad category**, not a persona+pain+venue.
- It's an **AI-thin space with no evidence of existing spend or no reachable audience** (the AI-gap trap).
- The only plausible product is an **undifferentiated AI wrapper** (no workflow ownership, data moat, or switching cost) — these don't sell (see `Acquirer-Intelligence.md`). Seed toward spaces where a defensible, sticky product is possible.
- It **structurally can't clear ~50% gross margin** (rubric v3.1 margin-floor gate): every unit of value would be frontier tokens, the economics are pass-through-dominated, or a **free incumbent caps the price** (e.g., VC-funded free tools giving the exact product away). Cheap-to-serve pain with paid-tool anchors passes; token-burning pain with free anchors doesn't.

**Margin sanity (S0 rung of the economics ladder — coarse, one line per seed).** Classify each seed's likely product by COGS intensity and note the price anchor: **inference-light workflow** (event-driven engine, LLM as garnish — tokens <$5/customer/mo; GM set by price) · **per-unit document parsing** (COGS scales with volume; model per page/doc) · **inference-core** (every unit of value = frontier tokens — margin-fragile AND a wrapper-gate suspect). Fidelity rises downstream: S2 runs a mini pro-forma, S4 a pricing corridor, S6 a v1 pro-forma, S15 tracks actuals.

## Output format

**A. Ranked seed shortlist** — a markdown table:

| Rank | Seed (persona + pain + venue) | Mkt-attractiveness | Why now | Likely acquirer(s) |
|---|---|---|---|---|

**B. Per-seed brief** — for each seed:

```
Seed: <persona + pain + venue>   ← paste this straight into Opportunity Sourcing (Recipe #1)
Why now: <the shift/trigger making this live>
Audience venue: <where they congregate — the $0 channel>
Existing spend: <what they already pay for / hack around>
AI gap: <how under-served, and why it's digitizable>
Margin sanity: <COGS-intensity class + price anchor + rough GM band — must clear the ~50% floor>
Likely acquirers: <OPPORTUNITY-SPECIFIC buyer map, not name-drops: each named buyer cites the specific
  portfolio asset or deal that evidences appetite for THIS asset class (e.g., Visma via its Link My Books
  acquisition for an e-commerce accounting tool — NOT "saas.group" bare), classified thesis-buyer /
  size-class buyer / plan-of-record venue (usually Acquire/Flippa on TTM profit), with the MRR/age
  milestone at which each becomes reachable>
Market-attractiveness: <score> (lens scores: 1=.. 2=.. ...)
```

**C. The recommended seed** to run through Recipe #1 next, with the exact handoff string and one line on why it's the strongest bet this week.

### Worked mini-example (abbreviated)

```
A. Ranked shortlist
| 1 | Solo bookkeepers reconciling messy client books (r/Bookkeeping, QuickBooks ProAdvisor community) | 84 | AI cleanup now reliable; tax-season pain | saas.group, Valsoft, Acquire.com buyers |

B. Per-seed brief
Seed: Solo bookkeepers reconciling messy client books (r/Bookkeeping, QuickBooks ProAdvisor community)
Why now: LLM data-cleanup crossed the reliability bar in the last ~year; bookkeepers drowning at scale.
Audience venue: r/Bookkeeping, QuickBooks ProAdvisor forums, accounting Twitter.
Existing spend: already pay for Dext, Hubdoc, LedgerSync — proven budgets.
AI gap: accounting is AI-thin operationally but highly digitized (data lives in QBO/Xero) — digitizable, not a trap.
Likely acquirers: saas.group / Valsoft (vertical SaaS), or an accounting-suite strategic (Visma bought Link My Books).
Market-attractiveness: 84 (1:5 2:5 3:4 4:4 5:5 6:4 7:2)

C. Recommended: run the bookkeeping seed through Recipe #1 first — proven spend + reachable venue + named acquirers, all inside an existing ecosystem.
```

## Quality bar (verify before returning)

- ≥6 seeds, every one in **persona + pain + venue** form (no bare categories).
- Each seed has ≥1 evidence point for **existing spend** and a **named reachable venue**, plus a **named likely acquirer justified by a specific portco/deal** (buyer map, not a name-drop).
- Each seed has a **margin-sanity line** (COGS class + price anchor + GM band) clearing the ~50% floor.
- No AI-gap-without-spend traps; no wrapper-only spaces; no free-incumbent price-ceiling spaces.
- A single recommended seed is identified with its exact Recipe #1 handoff string.

## Compounding (do this every run)

Append to `sourcing-log.md`: which seeds were generated and chosen, and later, how they performed downstream (did Recipe #1 find strong candidates? did any reach a demand test or a build?). Re-weight the lenses toward what actually converts — next month's seeding should beat this month's.

## Anti-patterns

- **Categories, not seeds.** "Fintech" is not a seed; "compliance officers at sub-$50M fintechs drowning in SAR filings (r/AML, ACAMS forums)" is.
- **Novelty worship.** Honor "all new fails" — start from proven demand.
- **AI-gap mirage.** Low AI adoption ≠ opportunity unless there's spend + reachability + something digitizable.
- **Ignoring the exit.** A seed with no plausible buyer is a worse seed — weight acquirer adjacency.
- **Famous-buyer name-dropping.** "saas.group / Tiny" attached to every seed is noise. A buyer belongs on a seed only with a cited portfolio asset/deal proving appetite for this exact asset class (a hard-earned lesson: a well-known aggregator was once named on a candidate whose category it had zero portfolio presence in — that's a size-class buyer at best, and it counts as no named buyer).
- **Token-blind seeding.** A space whose only product burns frontier tokens per unit of value fails the margin floor before it fails anything else. Ask "what's the COGS class?" at seed time, not at build time.
