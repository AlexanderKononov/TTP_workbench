---
Status: accepted
---

# MEXC spot is the first venue

We build milestones M0–M6 against MEXC spot only. It is the one venue with a large thin-market universe (about 1,170 API-tradable USDT/USDC pairs under $100k per day, against about 100 live ones on Hyperliquid) and 0% maker fees, and the Owner can trade there from Kazakhstan. Hyperliquid has the more algo-native API (order amend, server-side dead-man switch, active SDK, trader addresses on trades), but too few thin markets, and an address-level action limit that starves a strategy holding many rarely-filled resting orders. Evidence: [venue-research.md](../../.scratch/initial-infrastructure/venue-research.md), [venue-dev-ease.md](../../.scratch/initial-infrastructure/venue-dev-ease.md).

## Consequences

- No testnet: order handling is proven at minimum size in M5.
- No order amend: every requote is cancel + place, within a shared 12 requests/second limit.
- We maintain the order book ourselves from WebSocket snapshot + diffs (ccxt.pro's MEXC book feed drops updates); ccxt or raw REST for orders; kill switch built on cancel-all.
- The screener must filter markets where API trading is disabled.
- Revisit if sweeps turn out to happen mainly on Hyperliquid, if MEXC disables API trading on our markets, or if the 12/s limit proves too tight.
