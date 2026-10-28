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
- MEXC spot IP limits (docs intro, 2026-10-28): IP-weighted endpoints share 300 weight / 10 s; `exchangeInfo` and `ticker/24hr` weigh 25 each. 429/418 carry `Retry-After`; continuing after 429 leads to an IP ban. Current docs live under mexc.co/api-docs/spot-v3/market-data-endpoints/<page>.
- MEXC `ticker/24hr` `count` is null; `quoteVolume` is a string. `tradeSideType` 4 + status "2" = delisted.
- MEXC `exchangeInfo` `st: true` = "special treatment" (risk-warned, delisting candidate); ~62 symbols on 2026-10-28. The screener excludes them by default (Governor decision, ticket 04).
- MEXC REST latency from the Owner's PC is ~0.4 s per request, far below the weight budget; sequential kline scans are latency-bound, so fetch markets in parallel (6 workers ran 131 markets x 12 h in 28 s with no 429s).
