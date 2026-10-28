# Venue research: MEXC spot vs Hyperliquid (milestone 1)

Author: strategist. All claims checked **2026-10-28**; `[n]` = source list at bottom. "Unverified" = secondary or non-official source only. "Hypothesis" = not yet measured.

## Comparison

| # | Topic | MEXC spot | Hyperliquid (spot + perps) |
|---|---|---|---|
| 1 | Trades | REST `/api/v3/trades` max 1000 [3]; WS `aggre.deals` @100ms, protobuf [2] | WS `trades` with buyer/seller addresses [9] |
| 1 | L2 book | REST snapshot up to 5000 levels [3]; WS **diff deltas @10ms or 100ms** with version sequencing [4]; partial book 5/10/20 levels [5] | REST `l2Book` max 20 levels/side [10]; WS `l2Book` is **snapshots only**, 20 levels (5 in `fast` mode), pushed per block at most every ~0.5 s [9] |
| 1 | Klines | REST max 500 per call [3]; WS kline stream [2] | `candleSnapshot`: only the latest 5000 candles [10]; WS candles 1m to 1M [9] |
| 1 | Auth | API key + HMAC-SHA256; IP whitelist (up to 10 IPs; keys without one expire after 90 days) [1] | EVM wallet signatures; master approves "API wallets" that only sign [11]. Unverified: agents cannot withdraw [16] |
| 1 | Rate limits | 300 weight/10 s per IP, 500/10 s per UID [1]; place + cancel share 12 req/s [6]; WS max 30 streams per connection [1] | 1200 weight/min per IP; WS max 10 connections and 1000 subscriptions; per-address budget of 1 action per 1 USDC traded (10k starting buffer) [7] |
| 2 | History | Official klines **and trades** for all spot pairs since 2023-01-01; no order book history [8] | S3 `hyperliquid-archive`: L2 snapshots + asset contexts, requester pays, uploaded about monthly with possible gaps, **no spot data in the archive** [12]; node fills/trades buckets [12] |
| 3 | Testnet | None. ccxt exposes only a spot "test order" endpoint [13] | Yes. Faucet gives 1000 mock USDC but needs a prior mainnet deposit from the same address [14]. Testnet books are not realistic (hypothesis) |
| 4 | Order types | LIMIT, MARKET, LIMIT_MAKER (post-only), IOC, FOK; set varies by symbol [15] | GTC, ALO (post-only), IOC, reduce-only, TP/SL triggers [17] |
| 4 | Minimums | Per symbol: `baseSizePrecision` = min qty, `quoteAmountPrecision` = min notional (docs example "1" USDT); ±band from last price; `tradeSideType` can block one side [18] | **$10 minimum notional** (unverified, many secondary sources) [16]; prices max 5 sig figs, size by `szDecimals` [19] |
| 5 | Fees (base) | Unverified: 0% maker / 0.05% taker; official fee page not found [20] | Perps 0.015% maker / 0.045% taker; spot 0.040% / 0.070%. Rebates only at >0.5% maker share of volume [21] |
| 6 | Universe | ~2,456 pairs (CoinGecko) [22]; Altrady: ~80% API-tradable (Apr 2025) [23] | ~305 spot + ~340 perps (DefiLlama, undated snapshot) [24] |
| 7 | Libraries | ccxt spot + swap, ccxt.pro `watchOrderBook/Trades/OHLCV` [13] | ccxt spot + swap + HIP-3 [25]; official `hyperliquid-python-sdk` (not re-checked) |
| 8 | KYC / geo / custody | Centralised custody. US and Canada prohibited; the full list differs across MEXC pages [26]. No-KYC withdrawal limits conflict across sources [27] | On-chain self-custody (USDC bridged from Arbitrum, 5 USDC minimum) [14]. ToS restricts US and Ontario, enforced by front-end geofence (unverified) [28] |
| 9 | Risks | API blocked on Assessment Zone pairs since 2025-03-28, partly lifted 2026-01-30; project teams can disable API trading on a pair [23]; new error 30035 "order limit" (2026-10-23) [6]; custody/freeze risk (not researched) | JELLY: validators delisted a market and force-settled it (2025-03-26) [29]; thin HIP-1 spot tokens; L2 snapshots hide intra-block activity |

**Item 6 count of markets under $100k 24h volume: not measured.** Hypothesis: MEXC has many hundreds; Hyperliquid spot has fewer than 300. Next step: a dev role pulls `GET /api/v3/ticker/24hr` (MEXC) and `metaAndAssetCtxs` / `spotMetaAndAssetCtxs` (HL) and counts.

## Thin-market caveats

- On a $10 minimum, a market with $20k/day volume makes each of our orders a visible share of the book. Spikes may vanish once we trade into them.
- HL's 0.5 s book snapshots cannot show robot-like sub-second spikes. MEXC's 10 ms deltas can.
- MEXC history has trades but no order book. Backtests of fill probability need our own recorded book data on either venue.

## Recommendation

**MEXC spot for milestone 1.** It has the much larger thin-market universe and a full-depth 10 ms delta book feed. Official trade and kline history back to 2023 lets us backtest spike patterns before our own recorder has accumulated data. Maker fees are reportedly 0% and minimum notionals are small, which suits small limit orders. ccxt covers it. The costs are no testnet, so paper trading against live data stands in for it. Custodial and KYC risk are kept small by holding only the case budget on the venue. API access can be blocked per pair, so the screen must filter on `isSpotTradingAllowed` and `tradeSideType`. Keep Hyperliquid as the second venue: it has a better testnet, self-custody and on-chain transparency, but a $10 minimum, coarser book data and a smaller thin universe.

## Sources (all checked 2026-10-28)

1. https://www.mexc.co/api-docs/spot-v3/introduction
2. https://www.mexc.com/api-docs/spot-v3/websocket-market-streams
3. https://www.mexc.com/api-docs/spot-v3/market-data-endpoints/order-book , /klinecandlestick-data , /recent-trades-list
4. https://www.mexc.com/api-docs/spot-v3/websocket-market-streams/how-to-properly-maintain-a-local-copy-of-the-order-book
5. https://www.mexc.com/api-docs/spot-v3/websocket-market-streams/partial-book-depth-streams
6. https://mexc.com/api-docs/spot-v3/change-log
7. https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/rate-limits-and-user-limits
8. https://www.mexc.com/api-docs/spot-v3/market-data-endpoints/download-historical-market-data
9. https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/websocket/subscriptions
10. https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/info-endpoint
11. https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/nonces-and-api-wallets
12. https://hyperliquid.gitbook.io/hyperliquid-docs/historical-data
13. https://docs.ccxt.com/exchanges/mexc
14. https://hyperliquid.gitbook.io/hyperliquid-docs/onboarding/testnet-faucet ; https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/usdc
15. https://www.mexc.com/api-docs/spot-v3/public-api-definitions
16. https://docs.chainstack.com/docs/hyperliquid-order-precision ; https://www.dynamic.xyz/docs/recipes/integrations/hyperliquid-agent-wallets
17. https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/exchange-endpoint
18. https://www.mexc.com/api-docs/spot-v3/market-data-endpoints/exchange-information
19. https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/tick-and-lot-size
20. https://www.mexc.com/ru-RU/crypto-pulse/article/mexc-trading-fees-complete-guide-39643
21. https://hyperliquid.gitbook.io/hyperliquid-docs/trading/fees
22. https://www.coingecko.com/exchanges/mexc
23. https://www.mexc.com/support/articles/17827791522788 ; https://support.altrady.com/en/article/trading-with-an-api-key-on-mexc-1movlxr/
24. https://defillama.com/exchange/hyperliquid
25. https://docs.ccxt.com/exchanges/hyperliquid
26. https://www.mexc.com/learn/article/mexc-restricted-countries-complete-list-of-prohibited-limited-regions/1
27. https://cryptsy.com/mexc-kyc/
28. https://onekey.so/blog/ecosystem/geo-block-hyperliquid-dydx-us/
29. https://www.theblock.co/post/348314
