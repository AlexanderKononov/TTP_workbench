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
- MEXC spot WebSocket (verified live 2026-10-28): `wss://wbs-api.mexc.com/ws`; streams `spot@public.aggre.depth.v3.api.pb@100ms@SYM` (diffs, `fromVersion`/`toVersion`) and `spot@public.aggre.deals.v3.api.pb@100ms@SYM` (trades, `tradeType` 1 buy / 2 sell); pushes are binary protobuf `PushDataV3ApiWrapper` (oneof 313 aggreDepths, 314 aggreDeals; `.proto` files in github mexcdevelop/websocket-proto). Versions chain by exactly +1; snapshot `GET /api/v3/depth` (weight 3) `lastUpdateId` is in the same version space.
- MEXC WS control: subscribe `{"method":"SUBSCRIPTION","params":[...]}` -> `{"id":0,"code":0,"msg":"<streams joined by , in the server's order>"}`; a refused symbol still has `code 0` with `msg "Not Subscribed successfully! [...]. Reason? Blocked!"` (check the text). `{"method":"PING"}` -> `{"id":0,"code":0,"msg":"PONG"}`; server drops idle connections (1 min no data, 30 s no subscription, 24 h max). 30 subscriptions per connection = 15 markets.
- MEXC `/api/v3/depth` `limit=5000` returns at most 2000 levels per side (BTCUSDT). Thin markets push one depth diff every few seconds and may have no trades for minutes.
