# Worked example — a candidate the system killed (and what it taught)

*Real, archived case from the system's first dry-run (June 2026). Shared because killed candidates are teaching material; live pipelines stay private — yours should too.*

## The candidate

**Seed (S0):** DTC Shopify operators who can't reconcile payouts to bank deposits or see true net-margin by SKU (r/shopify, Shopify Community forums). Market-attractiveness 84/100 — passed all five lenses.

**Sourcing (S1):** real, dated, linkable pain — payouts never equal sales (fees, refunds, UTC cutoffs, tax withholding); operators reporting 5–15% of sales seemingly unaccounted; threads with 84 replies / 1,160 views; a genuine why-now (a platform tax-withholding change that silently broke books).

**Scoring (S2, rubric v2.0):** Payout↔Bank Reconciliation scored **90.4**, True Net-Margin **90.0**. Both STRONG. Looked like a slam dunk.

## What went wrong — and how the system caught itself

The space was **saturated**: five entrenched incumbents (A2X with 13k+ customers, Link My Books — later acquired by Visma — Synder, Bookkeep, Webgility). Two candidates in a crowded market both scored ~90 because Competitive Wedge carried only 4 of 100 points — proven pain + spend + reach swamped the saturation signal. The rubric literally could not distinguish a crowded market from an open one.

That became **calibration entry #1** (see `example-calibration-entry.md`): Wedge re-weighted 4→10, Pain and Reachability trimmed. Re-scored: 86.8 / 88.0 — and the *ranking flipped*.

An external review then found the deeper flaw: the demand gate was about to pass this candidate on **category evidence** — "A2X has 13k customers" proves A2X wins, not that anyone would switch to a new entrant. In a saturated market, heavy existing spend is evidence *against* easy entry. That produced two permanent rules now in the system:

- **Wedge ≤ 3 → the S5 switch test is mandatory** (≥3 competitor-paying humans commit, or kill).
- **Category evidence never clears the demand gate alone in a crowded market.**

## The outcome

The candidate was archived without a build. Zero dollars and zero build-weeks spent on a market where the realistic outcome was a distant sixth place. The next (real) sourcing run started from a clean pipeline — and the rubric that scored it was measurably sharper than the one that had said "90, go."

**The lesson this example encodes:** a high score is a hypothesis, not a verdict. The system's job is to try to kill your idea cheaply; when it succeeds, that *is* the win.
