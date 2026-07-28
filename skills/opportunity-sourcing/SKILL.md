---
name: opportunity-sourcing
description: >-
  Find product/business opportunities by mining real, recent, engagement-validated pain. Use this skill
  whenever the user wants to source startup or product ideas, discover unmet needs or pain points, decide
  what to build, run weekly market/opportunity discovery, validate that a problem is real before building,
  or turn a niche/market/persona into a ranked, evidence-backed candidate list. Triggers on "source
  opportunities", "find problems worth solving", "what should I build", "opportunity sourcing", "mine pain
  points", "find me ideas in [market]", "is this problem real", or any Track 1 discovery work for the Summer
  Solstice venture sprint. It drives the last30days skill with pain-shaped probes and outputs candidates
  pre-scored on the canonical rubric (rubric.json, owned by the opportunity-scoring skill). Use it even when
  the user doesn't name "last30days" or a "scorecard" — if they want to know what to build or what's painful
  in a market, this is the skill.
---

# Opportunity Sourcing

Turn "go look at the market" into a ranked list of **candidate problems** that are real, recent, and
**validated by what people actually engage with** — pre-scored so they drop straight into
`Opportunity-Scorecard.xlsx`. This is recipe #1 of the Summer Solstice recipe book; it feeds Track 1
(Discover & Validate).

The engine underneath is the **`last30days`** skill. The whole point of this skill is to use it *well*:
`last30days` tells you the current truth about a topic — it does not, on its own, hand you problems worth
building. So most of the work here is **asking it the right pain-shaped questions** and then **extracting,
qualifying, and scoring** the problems that surface.

## Prerequisites

- **`last30days`** installed (https://github.com/mvanhorn/last30days-skill). Reddit, Hacker News,
  Polymarket, and GitHub work with no keys; adding X and YouTube keys sharply improves signal for most
  niches. If a high-signal source has no API, mint an agent-native CLI for it with Printing Press.
- **`rubric.json`** (project root) — the canonical rubric (gates, criteria, weights), owned by the
  `opportunity-scoring` skill (S2). **This skill does not restate the rubric.** Read `rubric.json` at run
  time and score against it; if it's missing, stop and say so rather than scoring from memory. (A stale
  restated copy in this file is exactly the drift that External Review #01 caught.)
- The **Opportunity Scorecard** (`Opportunity-Scorecard.xlsx`) for the live weighted calc.
- If present, read `Operating-System.md` for the maxims and targets this output serves.

## Inputs

- **Seed** (required): a niche, persona, market, or product category — or `wide net` to scan broadly.
- **N** (optional): how many candidates to return. Default 12.
- **Mode** (optional): `targeted` (one niche, go deep) or `wide-net` (scan many adjacent spaces).

## The pipeline

Work through these as atomic steps. Each is a primitive you compose with judgment; the loop continues until
you have a scored, evidence-backed shortlist.

### 1 — Frame the hunt (probe design)

From the seed, write **8–15 pain-shaped probes** to feed `last30days`. *How you query determines what pain
surfaces* — generic topics return generic briefs, so shape probes toward friction, churn, spend, and unmet
need. `last30days` v3 resolves the right communities and handles itself, so write natural-language topics,
not keyword soup.

Probe patterns that reliably surface pain:

- **Churn / switching:** "switching away from [tool]", "[tool] alternatives", "leaving [tool] for"
- **Complaints / venting:** "[persona] biggest frustrations 2026", "why [workflow] is broken", "[tool] I hate"
- **Spend pain (signals willingness to pay):** "[category] too expensive", "[tool] pricing complaints"
- **Gaps / buying intent:** "best [category] for [niche]", "is there a tool that [job-to-be-done]"
- **Forced urgency:** "[new regulation/policy/platform change] impact on [industry]"
- **Emerging shifts:** GitHub issue/PR churn in a space; Polymarket odds on relevant outcomes
- **Competitor reviews:** "[competitor] reviews", "[competitor] vs" (mines the 1–3★ truth)

**Loud-niche bias correction.** `last30days` samples people who complain online — developers, e-commerce
operators, indie hackers — the most-served, most-competed niches on the internet. Observable pain
anti-correlates with underserved pain. For AI-thin / offline verticals (trades, local services, logistics,
food service), supplement with venue-native sources: trade forums, Facebook groups, job boards, review
sites (G2/Capterra 1–3★), and hiring posts ("we're hiring someone to do X manually" = spend-by-proxy). If
the seed is an offline vertical and all your evidence is Reddit/HN, your sample is wrong — say so.

### 2 — Harvest (fan out)

Run `/last30days <probe>` for each probe. For more than a few probes, **delegate in parallel: spawn one
research subagent per probe (or per small cluster of probes).** Each subagent runs `last30days` in its own
context and does the follow-up extraction there — so it still benefits from `last30days` becoming a session
expert — and returns only the structured signals. This keeps the main thread clean and runs probes
concurrently. **Cap parallelism and batch probes per subagent to control `last30days` cost**, and fall back
to serial/inline if subagents aren't available. Start with the free sources; enable keyed sources (X,
YouTube, TikTok) where the audience lives; optionally `--emit=html` to keep briefs.

Each subagent (or the inline run) follows up to pull structured signals:

> For each distinct pain point in that brief, give me: the problem in one line, who has it, the single best
> evidence link, its engagement metric (upvotes / likes / views / Polymarket odds / stars), and the date.

Reject anything without a real, dated, resolving link and an engagement number. Evidence over assertion —
this is the anti-hallucination discipline that keeps the whole sprint honest.

### 3 — Cluster

Merge signals across probes and sources into candidate **problems** at the theme level (dedupe; the same
story on Reddit + X + YouTube is one candidate, not three). For each candidate capture: a one-line problem
statement, the **persona** who has it, the **job-to-be-done**, and 2–3 representative evidence items
(link + engagement metric + date).

### 4 — Qualify (Mom Test / Jobs-to-be-Done)

For each candidate, record the things that predict real demand rather than opinion:

- **Existing spend or workarounds** — are people already paying for, or hacking together, a solution? (The
  strongest signal in *The Mom Test*: money and effort already spent beat any stated interest.) **Caution:
  competitor spend proves the *category*, not that anyone will switch to a new entrant — in a crowded
  space, heavy existing spend is evidence *against* an easy entry. Note incumbent density explicitly; it
  feeds the Wedge score and the S5 switch-test requirement.**
- **Recurring vs one-shot** — does the job recur weekly/monthly (feeds the Natural Retention criterion), or
  is it a one-time task the user leaves when done?
- **Frequency & recency** — how often does it bite, and is it live in the last ~30 days?
- **Intensity** — engagement magnitude across sources.

Drop any candidate that can't clear the evidence gate. A clean shortlist of real problems beats a long list
padded with maybes.

### 5 — Pre-score & emit

Score each surviving candidate against **`rubric.json`** (read it — don't score from memory), run the kill
gates, then emit the output in the format specified. Rank by weighted score and flag the **top 3 for the
Demand Confidence Gate (S5)** — a passing score is necessary but not sufficient; it still has to survive S5
before it earns a build week, and **Wedge ≤ 3 candidates require the S5 switch test, always**.

## Output format

Produce all three parts, in this order.

**A. Ranked shortlist** — a markdown table:

| Rank | Candidate problem | Persona | Est. score | Verdict | Top evidence |
|---|---|---|---|---|---|

**B. Scorecard entry blocks** — one per shortlisted candidate, in the exact field order the sheet expects so
it pastes in with zero reformatting (the sheet holds candidates as columns: **6 gates, then 9 scores** —
field names and order come from `rubric.json`):

```
Candidate: <short name>
Gates (Y = failed): <one Y/N per gate in rubric.json order — as of v3.1 that is NoFreePath | NoV1InBuildWeek |
                    NeedsLicensing | OverBudget | Wrapper | NoPaymentRail | MarginFloor — but ALWAYS emit
                    whatever gates rubric.json actually lists at run time>
Pro-forma (S2 fidelity, feeds MarginFloor): price anchor $X (named competitor/workaround) | COGS class | COGS $/unit | GM %
Scores (1-5):  Pain&Urgency=5 | WillingnessToPay=4 | FreeReachability=4 | TimeToFirstDollar=4 |
               BuildFeasibility=5 | NaturalRetention=4 | MarketAdequacy=3 | Acquirability=4 | CompetitiveWedge=3
Note: <one-line verdict rationale; channel latency + payment rail noted; incumbent density noted;
      buyer map: named buyer + evidencing portco/deal (thesis/size-class/venue); Wedge is provisional until S4>
```

**C. Evidence appendix** — per candidate, the raw signals: each as `link — engagement metric — date — one-line quote/claim`.

### Worked mini-example (abbreviated)

```
Seed: "Shopify app developers"  Mode: targeted

A. Ranked shortlist
| 1 | App reviewers leave 1★ over slow support, devs can't triage at scale | Shopify app devs | ~78 | STRONG | r/shopifyDev 480▲, 2026-06-09 |

B. Scorecard entry
Candidate: Review-triage copilot for Shopify app devs
Gates (Y = failed): NoFreePath=N | NoV1InBuildWeek=N | NeedsLicensing=N | OverBudget=N | Wrapper=N | NoPaymentRail=N
Scores (1-5): Pain&Urgency=5 | WillingnessToPay=4 | FreeReachability=3 | TimeToFirstDollar=4 |
              BuildFeasibility=5 | NaturalRetention=4 | MarketAdequacy=3 | Acquirability=4 | CompetitiveWedge=3
Note: devs already pay for helpdesk tools; Shopify App Store review latency 2-4 wks (Reachability capped); recurring triage job = retention-friendly.

C. Evidence appendix
- reddit.com/r/shopifyDev/… — 480 upvotes — 2026-06-09 — "1★ reviews from support latency are killing my install rate"
```

## Quality bar (verify before returning)

- ≥10 distinct candidates (or as many as genuinely clear the evidence gate — don't pad).
- Every candidate has ≥1 dated, resolving link **with an engagement metric** from ~the last 30 days.
- Every candidate fully scored on all criteria in `rubric.json` + a kill-gate verdict (rubric read at run
  time, version noted).
- Output pastes into `Opportunity-Scorecard.xlsx` with no reformatting.
- Spot-check 3 evidence links: they resolve and actually express the claimed pain.

## Compounding (do this every run)

Append to `sourcing-log.md` in the project: which seed, which probes, and which sources produced candidates —
and later, which survived their demand tests. Re-weight the probe patterns toward what actually converts.
This is the `ce-compound` step: next week's sourcing should be sharper than this week's because of what you
wrote down.

## Anti-patterns

- **Inventing pain.** Never describe a problem you can't back with a real, recent link. If `last30days`
  returns thin evidence, say so and narrow the probe — don't fabricate.
- **Stale signal.** A 2024 thread is not current pain. Hold the ~30-day window.
- **One loud voice = a market.** Require corroboration across sources before scoring pain high.
- **Loud niche = big niche.** Reddit/HN volume measures who posts, not who pays. Correct for it in offline verticals.
- **Restating the rubric.** Read `rubric.json`; never carry a local copy (it will drift — it already did once).
- **Generic probes.** "CRM software" returns a generic brief. "Why are [persona] leaving [CRM] in 2026"
  returns pain. Shape every probe.
