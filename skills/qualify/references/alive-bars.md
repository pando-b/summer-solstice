# Alive bars and kill windows

Write the alive bar and kill window into the decision before you record the verdict. They are a prediction made in advance, so the weekly review can test it without moving the goalposts.

## The falsification rule

- Set the bar before any launch data exists, and never lower it after seeing the numbers.
- Missing the bar inside the window means kill, unless the review records why the window had not really started.
- The kill window starts at channel-live (the product's `channel_live_at`), not at build-done. A marketplace review queue does not use up the window.

## Choosing the bar

Pick one metric the product will record from day one, and a threshold a living product clears inside the window.

| shape | metric | a reasonable starting threshold |
|---|---|---|
| plugin or extension with a paid tier | `paying_customers` | 3 inside 45 days |
| web tool with a subscription | `mrr_usd` | the pro forma's break-even customers × price, inside 60 days |
| digital product | `sales_count` | the pro forma's break-even customers, inside 30 days |
| agent tool | `paying_customers` | 3 inside 60 days |

Write it as:

```json
{"alive_bar": {"metric": "paying_customers", "threshold": 3,
               "description": "three paying customers within 45 days of channel-live"},
 "kill_window": {"days": 45}}
```

The threshold should be reachable through the channel the pro forma assumed. If `channel_capacity_customers` is far below the bar, lower your hopes for the product, not the bar.
