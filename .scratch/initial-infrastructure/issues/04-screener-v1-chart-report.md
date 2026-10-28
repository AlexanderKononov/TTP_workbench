# 04: Screener v1 with chart report

**Role:** platform-engineer

**Status:** ready-for-agent

**Blocked by:** 03

**What to build:** The Owner runs the screener and gets a ranked list of thin markets most likely to have a volume bot producing up-spikes, with a chart and statistics per candidate.

Spec: [../spec.md](../spec.md)

- [ ] `ttp screen [--max-volume ..] [--hours N] [--top K]` scans API-tradable thin markets using 1-minute klines (via the connector and storage from ticket 03)
- [ ] Per market: upper-wick count, typical wick size, interval regularity, 24h volume, and a score; ranking is deterministic
- [ ] Writes a report under gitignored `reports/screens/<screen-id>/`: candle chart PNG of recent hours per top candidate plus a stats table (CSV + markdown); the screen id is printed
- [ ] Wick metrics and ranking tested on fixture kline series with known patterns and pattern-free controls
- [ ] Respects rate limits for scanning ~1,200 markets; progress is shown
