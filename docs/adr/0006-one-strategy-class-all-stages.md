---
Status: accepted
---

# One event-driven strategy class runs unchanged in backtest, paper and live

A strategy is a single event-driven class: it reacts to market events and fills and emits order intents, never calling a venue itself. The same class runs in all three stages; only what surrounds it is swapped: the market data source (recorded replay vs live feed) and the order handler (simulated fills vs paper vs the execution service). We chose this over a vectorised backtest plus separate live code because two codebases drift apart, which is the main way a strategy that works in backtest fails live; and because the core strategy (resting limit orders hit by spikes) can't be modelled with vectorised bar signals. We build a minimal engine of our own on ccxt rather than adopting a framework (NautilusTrader, Hummingbot), to keep the code small enough for agents and the Owner to read; revisit if the engine outgrows that.
