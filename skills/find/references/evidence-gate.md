# Evidence gate and drop rules

## The gate

A candidate becomes a problem record only when all of these hold:

1. **A machine-fetched number.** At least one `solstice demand fetch` call succeeds for it. A failed fetch leaves the problem `pending_evidence`; it is never a zero and never replaced with an estimate.
2. **A dated, resolving link.** Every quoted post or listing has a URL that resolves and a date. A link you have not opened in this run does not count.
3. **Recent pain.** At least one piece of evidence is from the last 12 months; for complaint mining, the last 90 days.
4. **Corroboration.** Two independent sources (two venues, or a venue plus a demand number). One loud post is not a market.

No number in any record comes from the model. Numbers come from adapters; quotes come from pages; ratings are judgments that cite both.

## Drop rules

Drop the candidate, and report the rule, when any of these hold:

- **Thin AI wrapper.** The product would be a prompt around a general model with no workflow ownership, no data the user builds up, and no switching cost. A general assistant already does it.
- **Free incumbent.** A free, good, well-maintained product already does the job for this persona, and the complaints are about price only. Exception: the free product is stale or badly rated (then it is a marketplace gap).
- **No buyer.** The people with the pain cannot pay or never pay for tools (for example, it is a complaint about a hobby with no spend anywhere in the evidence).
- **Regulated core.** The core job needs a license, holds health or financial records, or moves money itself.
- **Not a product.** The pain is about a policy, a person, or a platform's own decision, and no tool changes it.

## Quality bar before scoring

- Every problem has at least one demand entry and at least one quoted, dated evidence record.
- Spot-check three evidence URLs: they resolve and say what the quote says.
- Duplicates are merged: the same complaint on three platforms is one problem with three evidence records.
