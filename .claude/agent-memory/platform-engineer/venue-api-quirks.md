---
name: venue-api-quirks
description: Non-obvious MEXC spot and Hyperliquid public-API quirks found during hands-on checks (2026-10-28)
metadata:
  type: reference
---

- MEXC `exchangeInfo` has per-symbol `makerCommission`/`takerCommission` (official fee source); `status` is string "1" for live.
- MEXC docs restructured 2026-05-08: old deep links 404; navigate from /api-docs/spot-v3/trade/.
- MEXC spot: no amend endpoint (cancel+new); place+cancel share 12 req/s per UID.
- ccxt.pro mexc `watchOrderBook` had an open bug (2026-09-25) losing deltas (fromVersion vs toVersion) — maintain book ourselves.
- Hyperliquid `spotMetaAndAssetCtxs`: ctx array (1164) is longer than universe (347); index ctxs by `universe[].index`.
- Hyperliquid address rate limit = 1 action per $1 traded (+10k buffer) — hostile to many-resting-orders/low-fill strategies.
