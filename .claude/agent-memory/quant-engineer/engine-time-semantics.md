---
name: engine-time-semantics
description: Backtest pitfalls fixed in the engine design (ticket 10): kline events are stamped at close time, broker sees events before the strategy, timers come from the feed
metadata:
  type: project
---

Engine/feed time rules settled in ticket 10 (2026-10-28), to keep when adding data types, brokers or strategies:

- A `Kline` event's `time` is its close time (open + interval); the replay window `[start, end)` applies to that close time. Stamping candles at open time is look-ahead.
- Per event the engine runs: broker `on_event` -> deliver fills -> strategy callback. An order emitted on event k can only be filled by events after k. Keep that order in any new broker; never fill inside `submit`.
- Timers are emitted by the feed (`timer_interval`), not the engine, so live feeds produce them from wall time without touching the loop.
- Each `DataType` added to `ttp.data.store` needs a `ReplaySource(build, delay)` in `ttp.feeds.replay.SOURCES`; `delay` is event time minus stored time column (0 for trades/snapshots).

**Why:** ADR-0006 says one strategy class in all stages; these rules are what makes replay results honest versus live.
**How to apply:** when building M3's simulated broker or new feeds, test the no-look-ahead ordering first (see `tests/test_engine.py::test_broker_sees_event_before_strategy_so_no_look_ahead`).
