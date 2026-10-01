# The Build Brief

A go decision carries a `build_brief` block. `solstice brief render <decision id>` prints it as a compound-engineering settled-decisions brief, which the build stage hands to `ce-brainstorm` and `lfg`. A well-formed brief lets their intake treat the build decisions as settled and ask nothing.

## Shape

```json
{
  "build_brief": {
    "title": "<working product name>",
    "direction": "<one or two lines: who it is for and the one job it does>",
    "settled": [
      {"topic": "shape", "decision": "<...>", "provenance": "user-directed",
       "rejected_alternative": "<...>", "reason": "<one line>"}
    ],
    "open_areas": ["<anything not settled>"],
    "evidence_ids": ["<evidence record IDs behind the go>"],
    "demand_entry_ids": ["<demand entry IDs on the problem>"]
  },
  "agent_readiness": {
    "core_job_without_human": true,
    "surfaces": ["api", "mcp"],
    "blockers": [],
    "summary": "<one line: what an agent can do through the product>"
  }
}
```

`topic` is one of `shape`, `channel`, `price`, `scope`, `standards`, `name`, `other`. `surfaces` takes `api`, `mcp`, `cli`, `webhook`, `file_import_export`, `llms_txt`, `structured_data`.

## Which decisions are settled

Only the owner settles a decision. Before writing the brief, put one batched question to the owner: for each topic, your proposal, the main alternative, and the tradeoff in one line. Then record each answer:

- The owner picked between options, or overrode yours → `user-directed`.
- The owner accepted your proposal with the tradeoff in view → `user-approved`.
- The owner did not engage with it, or you cannot name the alternative that lost → not settled. Put it in `open_areas`.

Never label your own unexamined proposal as settled. A plain "sounds good" to a list with no tradeoffs shown is not settlement.

Aim to settle these five, each with a real rejected alternative:

| topic | example decision | example rejected alternative |
|---|---|---|
| `shape` | ship as a plugin in the platform's directory | a standalone web app |
| `channel` | launch through the directory listing plus one search page | launch posts in forums |
| `price` | 12 USD a month after a 14-day trial | a one-time 39 USD license |
| `scope` | one job only: <the job>; nothing else in v1 | a dashboard covering related jobs |
| `standards` | build to the lean-but-real pack for this shape | a prototype without payments or monitoring |

The CLI refuses an entry whose `rejected_alternative` is missing, blank, or a placeholder such as "none".

## What may go in it

- Your own summaries, in your own words. Never fetched text: no quotes from posts, reviews, or listings. The render refuses a brief that repeats a stretch of a cited evidence quote.
- Evidence and demand entry IDs, so the build can trace every claim.
- The positioning one-pager's direction and price corridor, summarized.

Render it with `solstice brief render <decision id>` and read the output once. Each settled line must carry the `session-settled:` stem, its class, and "chosen over".
