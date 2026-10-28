# Spec: Initial infrastructure (M0–M6)

Status: awaiting Owner approval (gate 1)
Decisions: ADR-0002, 0004, 0005, 0006, 0007 · Structure: `docs/architecture.md` · Terms: `GLOSSARY.md`
Research: [venue-research.md](venue-research.md), [venue-dev-ease.md](venue-dev-ease.md)

## Problem Statement

The Owner has seen volume bots in thin crypto markets periodically sweep the order book, producing up-spikes that return to the normal zone, and wants to harvest them with small sums. There is no infrastructure yet: no market data, no way to find markets showing the pattern, no way to test a strategy honestly against thin-market reality, and no safe way to place and control real orders. History available from venues is limited (MEXC has klines and trades but no order book history), so evidence must be recorded by us.

## Solution

A deterministic Python trading system on MEXC spot, built in stages, each ending in a demo the Owner approves:

- **M0 – Venue & data feasibility:** a MEXC venue connector for public data; a downloader for kline/trade history; dataset storage.
- **M1 – Recorder:** records trades, 1 s top-20 order book snapshots and a gap log for approved markets, running locally.
- **M2 – Strategy interface & screener:** the event-driven strategy interface and engine; a screener ranking thin markets by recurring upper wicks, reporting charts to Telegram; dataset approval through the CLI with matched control markets; the `up-spike-harvest` strategy definition (gate 2).
- **M3 – Backtest:** replay feed, simulated broker with a queue-position fill model, per-market parameter calibration from history, reports.
- **M4 – Paper trading:** live feed + paper broker running the same strategy class.
- **M5 – Execution service:** real limit orders at minimum size: confirmation records, limits, expiry, kill switch, our own order/fill tracking.
- **M6 – First live case:** $50 total, ≤ $20 per market, max loss $15, 7-day expiry.

Tickets are cut only for M0–M2; M3–M6 get tickets after the Owner sees M2 working.

## User Stories

### Datasets & screening
1. As the Owner, I want the screener to rank all API-tradable thin MEXC markets by how often and how regularly they show upper wicks, so that I see the few markets where a volume bot is likely active.
2. As the Owner, I want each candidate's evidence as a candle chart of recent hours plus pattern statistics (wick count, typical size, interval regularity, 24h volume), so that I can judge it at a glance.
3. As the Owner, I want the screen summary and charts sent to Telegram, so that I can review it on my phone.
4. As the Owner, I want to approve chosen candidates with one CLI command, so that nothing is downloaded or recorded without my decision (gate 7).
5. As the Owner, I want one control market picked automatically per candidate from the same 24h-volume band where the screener finds no pattern, so that every dataset has negative examples.
6. As the Owner, I want approved markets' available history (klines, trades) downloaded into the dataset, so that analysis can start before recording has run long.
7. As the Owner, I want each dataset named, versioned and described by a dataset card, so that every backtest result is traceable to its data.
8. As the screener, I need markets with API trading disabled filtered out, so that we never pick untradable markets.
9. As the Owner, I want to run the screener on demand, so that it costs nothing while I'm not using it.

### Recording
10. As the Owner, I want every trade (price, size, side, time) recorded for approved markets, so that fills can be simulated against real prints.
11. As the Owner, I want a top-20-level book snapshot every second, built from a locally maintained book (snapshot + diffs), so that queue position and spike reach can be measured.
12. As the Owner, I want disconnects, resyncs and missing intervals written to a gap log, so that backtests know where data is missing.
13. As the Owner, I want the recorder to reconnect and resync on its own, and alert me on Telegram if it can't, so that recording survives network hiccups.
14. As the Owner, I want recorded data written to partitioned Parquet files and queryable with DuckDB, so that analysis is quick without a database server.
15. As the Owner, I want to start and stop recording for a dataset from the CLI, so that I control what runs on my PC.

### Strategy & engine
16. As a dev role, I want a strategy to be a class that reacts to market events, timers and fills and emits order intents, so that one class runs in every stage.
17. As a dev role, I want the engine to wire one strategy to one feed and one broker, with only feed and broker differing by stage, so that backtest and live can't drift apart.
18. As the Owner, I want `up-spike-harvest` defined in a STRATEGY.md I approve before it is coded (gate 2), so that the code implements what I meant.
19. As the Owner, I want the strategy to buy inventory in the normal zone with resting limit buys, rest sell limits at the levels spikes reach, and rebuy after fills, so that it harvests repeated sweeps.
20. As the Owner, I want spike levels, inventory and stop derived per market from that market's history, so that each coin is traded on its own behaviour.

### Backtest
21. As the Owner, I want backtests to replay a dataset through the same strategy class, so that results reflect the code that will trade.
22. As the Owner, I want the default fill model to track our place in the queue (we fill once traded volume at our price exceeds the size resting ahead of us), so that results reflect thin books where mostly the venue's own bots sit.
23. As the Owner, I want fill-on-touch and trade-through results shown alongside, so that I see the optimistic and pessimistic bounds.
24. As the Owner, I want backtest reports with PnL, fills, inventory over time, max drawdown, fees and the dataset card, compared against control markets, so that I can judge the edge before paper trading.

### Paper & live
25. As the Owner, I want paper trading on live data with simulated fills for a set period, so that I see behaviour against the live book before real money (stage gate).
26. As the Owner, I want a case confirmation to fix budget, limits and expiry before any real order, so that execution never exceeds what I approved.
27. As the Owner, I want the execution service to enforce max inventory per market, max loss, max open orders, the stop and expiry itself, so that strategy bugs can't breach limits.
28. As the Owner, I want a kill switch (`/stop` on Telegram and a CLI command) that cancels all open orders and halts every case without confirmation, so that I can stop instantly.
29. As the Owner, I want our own orders and fills tracked from MEXC's user-data stream and reconciled with REST, so that the system always knows its true position.
30. As the Owner, I want Telegram reports for fills, limit hits, stops and daily PnL, so that I can follow live cases without a screen.
31. As the Owner, I want M5 to prove order placement, cancel and fills at MEXC's minimum size before M6, so that the first live case only tests the strategy, not the plumbing.

## Implementation Decisions

- **Package:** single Python package under `src/`, managed with uv (one `pyproject.toml` + lockfile), pytest, ruff from the first commit; layout and dependency rules per `docs/architecture.md`.
- **Legacy:** all pre-pivot code (root stubs, Alpaca code, `data/` Yahoo pipeline, `tearsheet/`) moves to `archive/`; dev container and docs updated. Recorded data lives in a gitignored root `data/` directory.
- **Venue connector (MEXC):** the only module calling MEXC. ccxt or raw REST for orders and history; our own WebSocket handlers for the order book (snapshot + diffs, sequence-checked, resync on gap) and the user-data stream, since ccxt.pro's MEXC book feed drops updates. Respects the shared 12 req/s order limit. No amend on MEXC: a requote is cancel + place.
- **Events & intents:** core types for trade, book snapshot, timer, fill, and order intents (place limit, cancel); strategies import only these.
- **Storage:** Parquet partitioned by venue / market / data type / date; DuckDB for reads; dataset card per dataset in the knowledge base.
- **Screener v1:** 1-minute klines over REST for every API-tradable USDT/USDC market under a volume ceiling; ranks by wick frequency, size and interval regularity; writes a report (chart PNGs + table) to a gitignored reports directory and sends it to the dev Telegram bot; run on demand.
- **Dataset approval:** CLI command naming a screen and the approved markets; triggers history download, control selection (1:1, same volume band, no pattern) and recorder start.
- **Fill models (simulated broker):** queue-position (default), fill-on-touch, trade-through; every report shows all three.
- **Calibration:** strategy parameters per market are computed from the market's dataset by a deterministic calibration step; parameters are part of the case.
- **Execution service:** the only holder of MEXC credentials (env vars); accepts intents only within a valid confirmation's budget, limits and expiry; kill switch built on cancel-all; never imported by strategies.
- **Notifications:** Telegram through the notify module; dev bot for M0–M4, trading bot from M5.
- **Runtime:** local PC for now; VPS move is a later decision.

## Testing Decisions

- Good tests check external behaviour through the highest seam, never internal structure.
- **Primary seam: the engine.** Run a strategy through the engine with a replay feed and the simulated broker on small fixture datasets (hand-built spike scenarios plus slices of real recordings); assert on emitted intents, fills, inventory and PnL. The same seam later covers paper (paper broker) and execution-service limit checks.
- **Venue connector seam:** recorded MEXC REST/WebSocket payloads as fixtures; test book maintenance (diff application, sequence gaps → resync) and parsing without the network. A small opt-in suite hits public MEXC endpoints for drift detection.
- **Execution service invariants** (ADR-0002/0004): no order without a valid confirmation; every limit and the expiry enforced; kill switch always cancels and halts. `verifier` owns these.
- **Screener:** fixture kline series with known wick patterns and controls; assert ranking order.
- Prior art: `archive/tearsheet/tests/` (pure-pandas statistics tested in isolation).

## Out of Scope

- Down-spike strategy (later, same infrastructure).
- Venues other than MEXC spot; Hyperliquid is venue 2 (ADR-0007).
- Telegram buttons for approvals and confirmations (CLI first).
- VPS deployment, scheduling, Level 2+ agent autonomy.
- LLMs anywhere in the runtime (ADR-0004).
- Tick-by-tick book storage.

## Further Notes

- The pattern is rare: in a 30-market random sample only 1 showed repeated >3% upper wicks; the screener must rank the whole universe.
- On very thin markets our own orders are a visible share of the book; spikes may change once we trade into them. Paper trading (M4) and M5–M6 at minimum size exist to surface this.
- Unconfirmed: MEXC withdrawal-freeze/custody risk; mitigation is holding only the case budget on MEXC.
