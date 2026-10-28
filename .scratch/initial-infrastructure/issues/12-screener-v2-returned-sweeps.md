# 12: Screener v2 — score returned sweeps, not volatility

**Role:** platform-engineer

**Status:** ready-for-agent

**Blocked by:** 04, 09

**What to build:** The screener ranks markets by evidence of a volume bot's *sweep-and-return*, so the top of the list shows calm markets with repeated spikes that retrace, instead of trending or gapping markets. Rule set is the strategist's v2 scoring in `src/ttp/strategies/up_spike_harvest/STRATEGY.md` (screening section) and the strategist comment at the bottom of ticket 04.

Spec: [../spec.md](../spec.md)

- [ ] `spike_events` records open of the first spike candle, close of the last, and the event retrace `(H - close_last) / (H - open_first)`; an event is **returned** when retrace >= 0.5
- [ ] `wick_stats` adds `base_range` (median `(high-low)/close` over non-spike candles), `retrace_median`, `returned_events`; score is 0 unless `returned_events >= 3`, `interval_median_min >= 10`, `regularity > 0` and `wick_median >= 2 x base_range`; otherwise `returned_events x wick_median x (1 + regularity)`
- [ ] Report columns, CSV and the CLI table include the new fields; v1 columns stay
- [ ] New fixtures: trending steps and single gap prints score 0; a calm zone with >= 3 returned sweeps ranks first
- [ ] Re-run on the cached `screener` dataset (no venue requests) and leave the new top-10 report path in `## Comments` for the strategist's review before gate 7
