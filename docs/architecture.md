# Architecture

How the trading system's code is organised. Dev roles build within this structure; changing it needs an ADR. Terms are defined in [GLOSSARY.md](../GLOSSARY.md); the governing decisions are [ADR-0004](adr/0004-deterministic-trading-system.md) (deterministic runtime, credentials only in the execution service) and [ADR-0006](adr/0006-one-strategy-class-all-stages.md) (one strategy class in all stages).

## Parts

| Part | Does | Varies by stage |
|---|---|---|
| **Strategy** | Event-driven class: reacts to market events and fills, emits order intents. Never touches a venue | Never |
| **Feed** | Delivers market events to the engine | Replay feed (dataset) in backtest, live feed in paper/live |
| **Broker** | Receives order intents, reports fills | Simulated broker (backtest), paper broker (paper), execution service (live) |
| **Engine** | Event loop wiring one strategy to one feed and one broker | Never |
| **Venue connector** | The only code that calls a venue API (REST + WebSocket) | Never |
| **Execution service** | The live broker: holds credentials, enforces confirmation, limits, expiry and the kill switch | Live only |
| **Screener** | Ranks markets for a strategy's pattern and produces candidates with evidence | |
| **Recorder** / **Downloader** | Record live data / fetch available history into datasets | |

## Package layout

```
src/ttp/
  core/        events, order intents, clock, shared types
  strategies/  <name>/strategy.py + STRATEGY.md
  data/        dataset storage (Parquet + DuckDB), recorder, downloader, dataset cards
  feeds/       replay feed, live feed
  venues/      mexc/ connector
  execution/   simulated broker (fill model), paper broker, execution service
  engine/      event loop, backtest runner, reports
  screener/    candidate search and evidence
  notify/      Telegram
```

Dependencies point inwards: `strategies` import only `core`; only `venues` imports venue libraries; only `execution` reads venue credentials.

## Data flow per stage

- **Backtest:** dataset → replay feed → engine ↔ strategy → simulated broker
- **Paper:** venue connector → live feed → engine ↔ strategy → paper broker
- **Live:** venue connector → live feed → engine ↔ strategy → execution service → venue connector
