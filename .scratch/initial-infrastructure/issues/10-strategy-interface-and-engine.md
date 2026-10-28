# 10: Strategy interface and engine

**Role:** quant-engineer

**Status:** done

**Blocked by:** 03

**What to build:** The core of ADR-0006: the event-driven strategy interface and the engine that runs any strategy against a feed and a broker, proven with a replay feed over a dataset.

Spec: [../spec.md](../spec.md)

- [x] Core types: market events (trade, book snapshot, kline, timer), fill, order intents (place limit, cancel); strategies import only core
- [x] Strategy base class with event callbacks emitting intents
- [x] Engine event loop wiring one strategy, one feed and one broker, with a simulated clock for replay
- [x] Replay feed over a dataset's stored data, time-ordered across data types
- [x] A recording stub broker that captures intents (real fill models are M3)
- [x] Engine-seam tests: a toy strategy on fixture data produces the expected intents

## Comments

quant-engineer, 2026-10-28:

- **Core types** (`src/ttp/core/`): `Market(venue, symbol)`, `Side`, events `Trade`, `BookSnapshot` (+`BookLevel`), `Kline`, `Timer`, and `Fill`; intents `PlaceLimit`, `Cancel` (no amend: requote is cancel + place). All frozen dataclasses with tz-aware UTC `time`. Floats for price/quantity, matching storage; venue precision is the broker's job.
- **Event time = when the event became known.** A `Kline` carries `open_time` and `time` = close time; the replay feed stamps it so. Reacting to a candle at its open time would be look-ahead. Timers, trades and snapshots are instants.
- **Strategy base** (`core/strategy.py`): override `on_start/on_trade/on_book/on_kline/on_timer/on_fill/on_stop`; each returns the intents to send. `self.now` is engine time; `self.next_client_id()` gives deterministic ids (`<name>-<n>`), so cancels never wait for a venue id. Strategies import only `ttp.core`; `tests/test_engine.py::test_strategies_import_only_core` enforces it statically.
- **Engine** (`engine/loop.py`): per event it advances the clock, lets the broker see the event, delivers any fills (`on_fill`), then dispatches the event. So an order placed in reaction to an event can only be filled by later events; tested. `stop()` halts after the current event and still runs `on_stop` (ADR-0002: stopping needs no confirmation). `run()` returns `RunStats`.
- **Clock** (`core/clock.py`): one `SimulatedClock`, driven by event times in every stage (in paper/live the feed stamps venue time, so it tracks wall time). Never moves backwards, so slightly out-of-order live streams cannot crash the loop.
- **Feed / Broker seams** (`engine/ports.py`, structural `Protocol`s): `Feed.events()` is a pull iterator (a live feed blocks between events and emits its own `Timer`s); `Broker.on_event / submit(intent, now) / drain_fills()`. M3's simulated broker implements fills in `on_event` and hands them back via `drain_fills`; M4's paper broker and M5's execution service pull fills from the user-data stream the same way. The engine does not change.
- **Replay feed** (`feeds/replay.py`): merges every series of a dataset (`DatasetStore.series`) by event time with `heapq.merge`; tie order is timers, then market name, then data type. Window `[start, end)` applies to event time (so to a kline's close). `SOURCES` maps a `DataType.name` to its row-to-event builder plus the time delay between stored time and event time; trades and 1 s snapshots add an entry each. Series load fully into memory before replay; per-day chunking can come with the heavier data types.
- **Timers:** produced by the feed (`timer_interval`), not the engine, so paper/live feeds supply them from wall time with no engine branch. Ticks start at the first event's time.
- **Stub broker** (`execution/recording.py`): `RecordingBroker` records `(engine time, intent)` and never fills. Fill models (queue position, fill-on-touch, trade-through) are M3; the test suite's `TouchBroker` shows the shape.
- **Not in scope / deferred:** order acks, rejects and cancel confirmations as events back to the strategy (needed once a real broker can reject; add an `OrderUpdate` event then); multiple strategies per engine; a CLI command.
