---
Status: accepted
---

# Every strategy goes backtest → paper → live, each step approved by the Owner

A strategy reaches real money only through three stages: **backtest** (historical data, with a dataset card), **paper trading** (live market data, simulated orders, for a set period), then **live** (real orders, small budget first). Each promotion is an explicit Owner decision. Paper trading is mandatory, even when a backtest looks strong, because thin markets are where backtests mislead most: fills, slippage and spikes that vanish once you trade into them only show up against the live order book.
