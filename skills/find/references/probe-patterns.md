# Probe patterns

How a probe is phrased decides what pain surfaces. Generic topics return generic results; shape every probe toward friction, switching, spend, and unmet need. Write 3 to 6 probes per lens and seed.

## Pain-shaped probes

Placeholders: `<tool>` an existing product, `<persona>`, `<job>`, `<category>`.

- **Switching:** "switching away from `<tool>`", "`<tool>` alternatives", "leaving `<tool>` for"
- **Complaints:** "`<persona>` biggest frustrations", "why `<job>` is broken", "`<tool>` keeps failing at"
- **Spend pain:** "`<category>` too expensive", "`<tool>` pricing", "paying someone to `<job>`"
- **Gaps and buying intent:** "best `<category>` for `<persona>`", "is there a tool that `<job>`"
- **Forced urgency:** "new rule for `<persona>`", "`<platform>` change breaks `<job>`"
- **Reviews:** "`<tool>` reviews", "`<tool>` vs", reading the one- to three-star reviews
- **Agent tailwind:** "can my assistant `<job>`", "`<job>` API", "MCP server for `<job>`"

Search phrasing for volume is different from probe phrasing: volume keywords are what a buyer types ("piano lesson makeup scheduler"), not a sentence.

## Fetch commands

All fetches carry `--run <run id>`. The first successful fetch for a candidate uses `--new-problem --title "<one-line problem>"`; later ones use `--problem <problem id>`. Examples use invented queries.

| adapter | keys | use | example |
|---|---|---|---|
| `wporg` | none | plugin installs for a search phrase | `solstice demand fetch wporg --query "lesson makeup scheduler" --new-problem --title "..." --run <id>` |
| `hn_algolia` | none | story count and engagement over a year | `solstice demand fetch hn_algolia --query "garden plot waitlist" --problem <pid> --run <id>` |
| `trustmrr` | yes | verified revenue of a comparable product, by slug | `solstice demand fetch trustmrr --query example-slug --problem <pid> --run <id>` |
| `scrapecreators` | yes | Reddit, TikTok, YouTube keyword search; X for one named account | `solstice demand fetch scrapecreators --platform reddit --query "wax lot labels" --problem <pid> --run <id>` |
| `last30days` | engine | recent discussion saved as evidence (never a number) | `solstice demand fetch last30days --query "..." --problem <pid> --run <id>` |
| `dataforseo_volume` | yes | monthly search volume, many keywords in one paid task | `solstice demand fetch dataforseo_volume --query "k one" --query "k two" --problem <pid> --run <id>` |
| `dataforseo_trends` | yes | 12-month trend for one keyword | `solstice demand fetch dataforseo_trends --query "k one" --problem <pid> --run <id>` |
| `manual` | none | a number printed on a page with no API | `solstice demand fetch manual --query "listing" --metric extension_users --value 4000 --unit users --url <listing url> --source "<directory name>" --problem <pid> --run <id>` |

`last30days` cannot create a problem; it only adds evidence to one. X through `scrapecreators` reads one named account (`--handle`), never a keyword-wide count.

## Manual metric names

`manual` takes any metric name, but only the names below feed the score. Use them exactly:

- `extension_users`: users shown on an extension listing (volume)
- `active_installs_top`: installs shown on a plugin listing in a directory with no API (volume)
- `keyword_volume`: only when a keyword tool shows it and no keyed source is available (volume)
- `trend_change_pct`: a keyword tool's 12-month change, in percent, same condition (trend)
- `paid_installs`, `sales_count`: sales shown on a paid listing (spend)
- `paid_review_count`: review count on a listing with a published price (spend)
- `mrr_usd`, `revenue_30d_usd`: revenue a maker publishes on a public revenue page (spend)

Manual entries are low confidence: volume and trend from them cap at 0.5 unless a stronger entry exists.
