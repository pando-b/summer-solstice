# Lenses and seeds

## Seeds

A seed names where to hunt, in three parts:

- **Persona**: who has the problem ("independent piano teachers").
- **Pain**: the job that hurts ("rescheduling missed lessons").
- **Venue**: where those people gather or buy ("a teachers' forum, a plugin directory for studio websites").

`wide net` means: pick three to five adjacent personas from whatever the venues show, and run each as its own seed. A seed with no venue is incomplete; name the most likely venue before probing.

**Loud-niche bias.** Developer, e-commerce, and indie-maker venues are the loudest and most crowded. Observable complaining runs against underserved pain. For offline or trade verticals, prefer the venue's own sources (trade forums, review sites, job posts that describe manual work) over general social search. If every piece of evidence for an offline seed comes from developer venues, the sample is wrong; say so in the report.

## The six lenses

Each lens is one probe-runner subagent per seed.

### 1. Proven model, cloned into a niche

A product already earns money for one audience; the same job exists, unserved, for a narrower one. Find comparable products with public revenue (`trustmrr` by slug when keyed) or public founder write-ups, then check whether the niche version exists.
Strongest numbers: `mrr_usd` or `revenue_30d_usd` for the comparable, keyword volume for the niche phrasing.

### 2. Marketplace gap

Popular plugins or extensions that are poorly rated, stale (no update in a year), or overwhelmed with unresolved support threads. Demand is proven by installs; the gap is in the listing data.
Strongest numbers: `active_installs_top` (`wporg`), `extension_users` (`manual`, from the listing page).

### 3. Rising search trend

A search phrase that is growing and points at a tool, template, or digital product someone could own.
Strongest numbers: `keyword_volume` and `trend_change_pct` (`dataforseo_volume`, `dataforseo_trends`).

### 4. Complaint mining

Recurring complaints about a workflow or an existing tool, in the venue's own words.
Sources: `hn_algolia`, `scrapecreators` (Reddit, TikTok, YouTube keyword search; X only for named accounts), and `last30days` for evidence. Social numbers are engagement proxies at low confidence, so this lens needs a second, stronger number before a problem ranks well.

### 5. Who already automates this

People pay a person, a spreadsheet consultant, or a general tool to do a narrow job by hand. Job posts and service listings that describe the manual work are spend by proxy, and they name the job precisely.
Strongest numbers: a spend metric for the service or tool being replaced, keyword volume for the job.

### 6. Agent tailwind

Jobs people increasingly hand to personal agents, where no good agent-callable tool exists yet: no API, no MCP server, or data locked in a UI. Look for agent users asking "is there a tool my assistant can call for X" and for workflows that agents now attempt but fail at. Note in the candidate whether an agent could complete the core job without a human in the browser.
Strongest numbers: keyword volume for the job, Hacker News story counts for the agent-tooling gap.
