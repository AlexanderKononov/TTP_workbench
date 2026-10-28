---
Status: accepted
---

# Execution requires the Owner's confirmation of a case

No live order is placed without the Owner's **confirmation** of a **case**: one strategy, on a set of markets, for a time window, with a **budget**, **limits** (max loss, max position per market, max slippage, max open orders) and an **expiry**. Inside a confirmed case the trading system trades on its own; hitting any limit or the expiry stops it and alerts the Owner. We chose per-case over per-order confirmation because spike trading issues many small orders, and over fully autonomous trading because thin markets carry outsized slippage, manipulation and venue risk.

## Consequences

- The case format is a core interface: it must carry everything the Owner needs to decide.
- Limits are enforced by the execution service ([ADR-0004](0004-deterministic-trading-system.md)), not by the strategy code.
- **Stopping never needs confirmation; starting always does.** The Owner has a kill switch (Telegram `/stop` plus a local CLI equivalent) that cancels open orders and halts every case at once. It is built before any live stage.
- The confirmation channel must authenticate the Owner and record budget, limits and expiry; which channel is decided with the case format.
