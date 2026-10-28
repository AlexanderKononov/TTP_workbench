# 04: Screener v1 with chart report

**Role:** platform-engineer

**Status:** done

**Blocked by:** 03

**What to build:** The Owner runs the screener and gets a ranked list of thin markets most likely to have a volume bot producing up-spikes, with a chart and statistics per candidate.

Spec: [../spec.md](../spec.md)

- [x] `ttp screen [--max-volume ..] [--hours N] [--top K]` scans API-tradable thin markets using 1-minute klines (via the connector and storage from ticket 03)
- [x] Per market: upper-wick count, typical wick size, interval regularity, 24h volume, and a score; ranking is deterministic
- [x] Writes a report under gitignored `reports/screens/<screen-id>/`: candle chart PNG of recent hours per top candidate plus a stats table (CSV + markdown); the screen id is printed
- [x] Wick metrics and ranking tested on fixture kline series with known patterns and pattern-free controls
- [x] Respects rate limits for scanning ~1,200 markets; progress is shown

## Comments

platform-engineer, 2026-10-28:

- **Command:** `ttp screen [--max-volume 100000] [--min-volume 0] [--hours 24] [--top 10] [--min-wick 0.02] [--chart-hours 6] [--include-st]`. The universe is ticket 02's `thin_markets`; MEXC's `st` (special treatment) flag is now parsed into `SymbolInfo.st` and excluded by default (Governor decision), `--include-st` scans them too. `ttp markets` is unchanged and still lists `st` markets.
- **Metrics** (`src/ttp/screener/wicks.py`, pure pandas): upper wick = (high - max(open, close)) / max(open, close). A spike candle has a wick >= `--min-wick` (default 2%); adjacent spike minutes are one event, so a sweep crossing a minute boundary counts once. Per market: `wick_count` (events), `wick_median` (typical size), `wick_max`, `interval_median_min`, `regularity` = 1 - cv(intervals) clipped to [0, 1] (1 = perfectly periodic, ~0 = random), `volume_24h`, `candles`. Score = events x typical wick x (1 + regularity); fewer than 3 events is not a pattern and scores 0. Ranking: score desc, events desc, market name. This is a v1 heuristic for the Owner's eyes at gate 7, not a trading signal: wide-spread markets can produce irregular wicks from single prints; regularity halves their score but does not remove them.
- **Data path:** klines go through ticket 03's `download_klines` into a `screener` dataset under `data/datasets/` (gitignored, no dataset card), so a re-run over the same window costs no requests and `--top`/`--min-wick` can be tuned offline. The window is `[floor(now) - hours, floor(now))`.
- **Report:** `reports/screens/<screen-id>/` with `report.md` (parameters, top-K table with chart links, skipped markets), `stats.csv` (every scanned market, ranked) and `charts/NN-MARKET.png` (last `--chart-hours` of 1m candles, spike candles marked, volume panel; matplotlib Agg, no plotly). Screen id = `YYYYMMDD-HHMMSS` UTC of the run, printed last.
- **Rate limits and speed:** the scan runs 6 markets at a time through the shared `WeightLimiter`, which got a lock so threads share one IP budget. MEXC round trips are ~0.4 s, so 6 workers use roughly half the 300 weight / 10 s budget. Live: 131 markets x 12 h took 28 s (1m51s sequential); the full default scan (1,130 markets x 24 h, 3 pages each, cold cache) took about 4 minutes on 2026-10-28 with no rate-limit errors and 0 skipped markets. A market whose klines fail (e.g. HTTP 400) is skipped and listed in the report; a 429/418 (`MexcRateLimited`, new subclass of `MexcError`) stops the scan, since continuing gets the IP banned. Progress is a click progress bar with the current market.
- **Fix in ticket 03 code:** `DatasetStore._read_files` used `duckdb.sql(...)` (the module-global connection, not thread-safe) for the empty-result case; it now opens its own connection like the other paths.
- **Tests** (`tests/test_screener.py`): fixture series built in code (periodic wicks, irregular wicks with the same count and size, random-walk control without upper wicks, sub-threshold wicks, two-event non-pattern, adjacent-minute merge, empty series), ranking order incl. deterministic tie-break, PNG output, the CLI end to end on the saved MEXC universe fixtures (ranking, report files, `st` exclusion and inclusion, cached re-run makes no kline requests, `--hours`, skipped market vs rate-limit abort), and the limiter under threads.
- **Dependency added:** `matplotlib` (with the Agg backend set in `ttp.screener.report`).
- **QUESTION FOR OWNER:** `--min-wick 0.02` and the score formula are first guesses; after the first few screens the strategist should check whether 2% picks up the pattern seen by hand (the spec's sample used >3%). Conservative option taken: 2% catches more, and the Owner judges by chart.
- **First live result (2026-10-28 08:36 UTC, `ttp screen`):** the top 10 by score all have many events (9-22 in 24 h) but regularity 0.00 (e.g. RTUSDT, IRONUSDT, HOOKEDUSDT): frequent but irregular wicks, mostly in the $50k-100k band. The only regular one in the top 10 is XNTUSDT (6 events, regularity 0.23). The strategist should look at a few charts before gate 7 and say whether the score should weight regularity more (e.g. require regularity > 0 or multiply by it) or whether a minimum spacing between events is needed.

strategist, 2026-10-28 (answer to the scoring question, from screen `20261028-083639`, charts of ranks 1-4, 7, 9, 10):

- **Finding:** none of the 7 inspected charts shows the sweep-and-return pattern. The wicks come from trending steps (RTUSDT, QUICKUSDT, MICRODUCKUSDT), gap markets with single prints in a wide spread (CTXUSDT, XNTUSDT, ~$5k/day), a 40% swing (IRONUSDT) and chop (HOOKEDUSDT). Count x size rewards volatility; regularity 0.00 on 9 of 10 is a symptom, not the cause.
- **Decision:** do not simply weight regularity more. Measure the two features the pattern is defined by and v1 ignores: the **return** (event retrace `(H - close_last)/(H - open_first) >= 0.5`; count only returned events) and the **calm base** (`wick_median >= 2 x base_range`, base_range = median `(high - low)/close` over non-spike candles). Then gate: score 0 unless `returned_events >= 3`, `interval_median_min >= 10` and `regularity > 0`. Keep the score form `returned_events x wick_median x (1 + regularity)`. Thresholds are hypotheses; full rule in `src/ttp/strategies/up_spike_harvest/STRATEGY.md` §10.
- **Code change (for the Governor to ticket, platform-engineer):** `spike_events` adds `open_first`, `close_last`, `retrace`; `wick_stats` adds `base_range`, `retrace_median`, `returned_events` and the gates; `COLUMNS`, CSV and markdown table gain the new columns; fixtures: "trending steps" and "gap single prints" series score 0, "calm zone + returned sweeps" ranks first. Re-run on the cached `screener` dataset (no venue requests) and chart the new top 10 for strategist review before gate 7; candidates likely to surface: GMUSDT, TAPEFOURUSDT, BORDRUSDT, UMXMUSDT, UBIKUSDT, PYRUSDT. Keep `--min-wick 0.02` until v2 output is seen.
