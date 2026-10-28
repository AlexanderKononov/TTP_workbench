# Venue dev-ease: MEXC spot vs Hyperliquid (resting-order sweep strategy)

Author: platform-engineer, 2026-10-28. Builds on [venue-research.md](venue-research.md) and does not repeat it. Hands-on checks used public endpoints only. Strategy context: a volume bot sweeps the book from time to time, and we profit from limit orders already resting there. What matters most is managing resting orders, keeping an accurate book and getting reliable fill events. Latency matters less.

## 1. Universe (live pull, 2026-10-28 ~UTC)

| | <$100k 24h | $100k–1M | ≥$1M |
|---|---|---|---|
| MEXC spot USDT/USDC pairs (1,679 of 1,840) | **1,225** (1,170 API-tradable) | **402** (390 tradable) | 52 |
| Hyperliquid spot, listed pairs (347) | 326 (**227 at zero volume**) | 9 | 12 |
| Hyperliquid perps, live (179 of 235) | 40 | 77 | 62 |

"Tradable" means `status=1`, `isSpotTradingAllowed`, and `permissions=[SPOT]`. 1,771 of 1,840 MEXC symbols allow API trading. `exchangeInfo` exposes per-symbol `makerCommission`: 0 on 1,740 symbols, 0.0001 on 100. This is the first official confirmation of the 0% maker fee that venue-research.md listed as unverified. `spotMetaAndAssetCtxs` returns 1,164 contexts but only 347 listed pairs, so join on `universe[].index`.

## 2. Wick check (MEXC 1m klines, last 24h)

- Three thin pairs, 1,440 candles each:
  - CYBROUSDT: 0 candles with upper wick >3%, and 631 flat candles (h==l)
  - NOTUSDC: 0 wicks
  - MATUSDT: 1 wick >5%
- A random sample of 30 tradable pairs at $20k–100k: only AGRSUSDT showed ≥3 upper wicks >3% (it had 3, plus 1,316 flat candles). 28 of 30 had no >3% upper wicks at all.
- **Reading:** random thin pairs show almost no sweep wicks in 1m klines. Most of them are quoted continuously by market makers, so a sweep may only move price a few ticks. The pattern has to be screened for, for example by ranking all 1,170 pairs by wick count. Klines are fine for that screen, but fill modelling needs our own recorded book.

## 3. Dev ease

| | MEXC spot | Hyperliquid |
|---|---|---|
| Docs | Reorganised into per-endpoint pages on 2026-05-08. Old deep links 404, and several pages leave out batch limits and stream encoding [1][2] | One coherent GitBook. The exchange endpoint page is long but complete [3] |
| Official Python SDK | `mexcdevelop/mexc-api-sdk`: last push 2024-02-12, 87 open issues. Effectively abandoned | `hyperliquid-python-sdk` v0.24.0 (2026-06-04), 1.9k stars, actively released |
| ccxt / ccxt.pro | Spot is mature. **Open bug (2026-09-25): `watchOrderBook` silently loses deltas** because of a `fromVersion`/`toVersion` mix-up. 14 MEXC issues opened in the past year, mostly swap or WS | 41 issues opened in the past year (young integration), 2 open. Fill parsing bug on reduce-only (2026-10-13) |
| User-data WS | listenKey: 60 min validity, keepalive via PUT, connection dropped at 24 h. Streams for orders, deals and account [2] | `orderUpdates`, `userFills`, `userEvents`. Orders can also be *sent* over WS (`post`) [3] |
| Amend | **None**, so cancel + new order is needed (the UI "modify" is also cancel/replace) | `modify` and `batchModify`, by `oid` or `cloid` [3] |
| Post-only | `LIMIT_MAKER` (on all 1,840 symbols) | `Alo` |
| Order-rate | Place and cancel **share 12 req/s per UID** (2026-03-11). Batch orders 5/s (2025-03-25). Cancel-all-per-symbol exists (2026-05-22). New error 30035 "order limit" (2026-10-23) [1][4] | IP: 1200 weight/min, a batch of n costs 1+n/40. **Address: 1 action per $1 traded, 10k starting buffer**, then 1 per 10 s. Cancels get extra headroom. Up to 1,000 open orders [5] |
| Kill-switch aid | None server-side, only cancel-all | `scheduleCancel` dead-man switch, ≥5 s ahead, 10 triggers/day. `expiresAfter` on actions [3] |
| Keys | HMAC key with read/trade/withdraw scopes. IP whitelist of up to 10 IPs, and keys without one expire after 90 days. Key management API added 2026-06 [1] | Agent wallet signs only, with no IP binding. Nonce management is required. EIP-712 signing is hard to hand-roll, so use the SDK |
| Breaking changes, past year | Doc restructure. Rate limits tightened twice (2025-03, 2026-03). Per-pair API bans (2025-03-28, see venue-research) | HIP-3 dexes. Spot pairs are named `@N`. No core trading API break found |

## 4. Verdict

**Hyperliquid is the more algo-native API**: atomic amend, a dead-man switch, a maintained SDK, clean fill streams and on-chain trade addresses that make the sweep bot identifiable. **MEXC is the venue where this strategy can actually run.** It has 1,170 tradable sub-$100k pairs against 99 non-zero ones on HL spot. HL's address budget of one action per $1 traded also starves a strategy that rests many orders and fills rarely: after the 10k buffer it gets one action per 10 s. On MEXC the costs are cancel/replace instead of amend, a 12/s order budget and our own book maintenance. We should not trust ccxt.pro `watchOrderBook` given the open bug; implement the documented delta+snapshot sync ourselves. **Recommend MEXC spot.** Use ccxt (or raw REST) for orders, write our own WS book and user-data handlers, and build the kill switch on cancel-all.

What would change this:
1. Sweeps turn out to happen mainly on HL perps or HIP-3 markets.
2. MEXC bans API trading on our chosen pairs.
3. MEXC's 12/s budget proves too tight for the requote rate we measure.

## Sources (checked 2026-10-28)
1. https://mexc.com/api-docs/spot-v3/change-log
2. https://www.mexc.com/api-docs/spot-v3/websocket-user-data-streams ; https://www.mexc.com/api-docs/spot-v3/trade/
3. https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/exchange-endpoint
4. https://www.mexc.com/ru-RU/announcements/article/mexc-to-adjust-api-spot-order-rate-limit-effective-mar-25-2025-17827791522801
5. https://hyperliquid.gitbook.io/hyperliquid-docs/for-developers/api/rate-limits-and-user-limits
6. GitHub: ccxt/ccxt issues (searched `mexc` / `hyperliquid` in title), hyperliquid-dex/hyperliquid-python-sdk, mexcdevelop/mexc-api-sdk
