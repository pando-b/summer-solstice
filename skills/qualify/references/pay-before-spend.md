# Pay-before-spend test

A candidate that needs more than the launch limit (`budgets.launch_spend_limit_usd`, $50 by default) to reach channel-live is not dropped. It earns the spend by selling first.

## On the go

1. The `upfront_cash` check is `pass`, with the basis "over the launch limit: pay-before-spend test (R21)".
2. Create the product at `qualified` with `estimated_upfront_spend_usd` set to the pro forma's `upfront_spend_usd`.
3. Request the costly item (license, paid tool, asset) as an `owner_prereq` approval with its `cost_usd`. It cannot close until the product records a buy signal.
4. Run `solstice record transition product <id> testing`. The CLI refuses `building` while the spend is over the limit, so `testing` is the only way forward, and it starts the 14-day clock.

## During the test

The owner sets up a landing page with a real checkout for a refundable pre-order or founding-member price. Each paid order is recorded on the product:

```
solstice record event product <id> --file -
{"type": "buy_signal", "kind": "pre_order", "source": "<checkout name>", "reference": "<order id>"}
```

Email-only sign-ups use `"kind": "waitlist_signup"`. They are recorded but never unlock spend.

## The outcome

- Three or more paid pre-orders (or founding-member purchases) within 14 days of the test start → `solstice record transition product <id> building`, and the owner can close the costly prerequisite with `solstice approvals close <approval id>`.
- Fewer by day 14 → `solstice record transition product <id> parked`. A parked idea can be tested again later.

The CLI enforces all of this: a refused move prints `transition_refused` with `details.rule` (`launch_spend_limit`, `pre_orders_to_unlock`, `test_window`). Report the rule; never work around it.
