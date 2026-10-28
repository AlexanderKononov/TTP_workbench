# 10: Strategy interface and engine

**Role:** quant-engineer

**Status:** ready-for-agent

**Blocked by:** 03

**What to build:** The core of ADR-0006: the event-driven strategy interface and the engine that runs any strategy against a feed and a broker, proven with a replay feed over a dataset.

Spec: [../spec.md](../spec.md)

- [ ] Core types: market events (trade, book snapshot, kline, timer), fill, order intents (place limit, cancel); strategies import only core
- [ ] Strategy base class with event callbacks emitting intents
- [ ] Engine event loop wiring one strategy, one feed and one broker, with a simulated clock for replay
- [ ] Replay feed over a dataset's stored data, time-ordered across data types
- [ ] A recording stub broker that captures intents (real fill models are M3)
- [ ] Engine-seam tests: a toy strategy on fixture data produces the expected intents
