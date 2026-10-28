# 06: Dataset approval with control markets

**Role:** quant-engineer

**Status:** done

**Blocked by:** 04

**What to build:** The Owner approves screener candidates with one command; the system builds a versioned dataset with matched control markets and their history (gate 7).

Spec: [../spec.md](../spec.md)

- [x] `ttp dataset approve <screen-id> <market>... --name <dataset>` creates a versioned dataset definition listing candidates and controls
- [x] One control per candidate, chosen at random (seeded, reproducible) from the same 24h-volume band among markets the screen scored as pattern-free
- [x] Kline and trade history available from MEXC is downloaded for all dataset markets
- [x] Dataset card written/updated; `ttp dataset list` and `ttp dataset show <name>` work
- [x] Tests cover control selection and dataset definition with fixtures

## Comments

quant-engineer, 2026-10-28:

- **Definition** (`src/ttp/data/datasets.py`): `data/datasets/<name>/dataset.json` holds `approvals` (version, time, screen id, seed, band, max control events, commit) and `markets` (market, role candidate/control, paired_with, version added, screen id, score, events, 24h volume, band used). Each `approve` with new markets adds a version; markets are never removed; re-approving known markets just refreshes the history. The definition is rendered into the card (`## Definition` section), which is the committed provenance record; `ttp download klines --dataset <name>` keeps that section since the card reads the definition from storage.
- **Controls:** pattern-free = `wick_count <= --max-control-events` (default 0, i.e. no spike candle at all in the screen window; allowed up to 2, below the screener's `MIN_EVENTS`, so score is always 0). Same band = control 24h volume within `[v / band, v * band]` of the candidate's, `--band` default 2. The pool also requires as many candles as the screen's fullest market (a half-listed market is trivially quiet) and excludes candidates, markets already in the dataset and earlier picks. An empty pool widens the band to band^2 then band^3 (recorded per control; the Owner sees `x4`/`x8` in the card) and then fails. Draw: `random.Random(f"{seed}/{candidate}").choice(sorted(pool))`, so row order of `stats.csv` does not matter and adding candidates later leaves earlier controls unchanged. In the real screen `20261028-083639`, 982 of 1130 markets have 0 events, so pools at x2 hold ~50-900 markets.
- **Trades history:** `MexcClient.agg_trades(symbol, start_ms, end_ms)` pages `GET /api/v3/aggTrades` (weight 1). Probed live: `startTime`+`endTime` must be sent together (else -1128), both inclusive, at most exactly 1 h apart (else -1127), max 1000 rows, newest first, timestamps whole seconds, `a/f/l` ids null; history reaches back ~24 h (26 h back is empty for BTCUSDT too). A full page is paged backwards by re-asking up to its oldest second, so a second split across pages is read whole. `GET /api/v3/trades` returns only the latest ~200 prints (ms timestamps, no ids), useless for history. MEXC also offers a web download of klines and trades back to 2023-01-01 (not an API; noted for later).
- **`trades` DataType** (`store.py`): columns `time, price, quantity, side` (aggressor side `buy`/`sell`); key is the whole row since there are no ids, so two prints identical in all four collapse (seen 0 such in 1000 BTC rows). Within-second order is not preserved by the store (DuckDB `ORDER BY` is not stable); stated in the card. `download_trades` fetches from the last stored print onwards (trades have no grid, so gap-fill is impossible; a quiet hour and a missing hour look alike). Replay feed `SOURCES` has a `trades` entry emitting `core.Trade` at the stored time.
- **Download:** `approve` downloads `--days` (default 30) of klines and 26 h of trades for every dataset market, 4 markets at a time through the shared `WeightLimiter`; a market that fails is reported and the command exits 1 after writing the definition and card, so a re-run only retries the download. `--no-download` writes definition and card only.
- **Live check** (2026-10-28, throwaway dataset `live-check`, removed afterwards): RTUSDT and CTXUSDT from screen `20261028-083639` got controls LRCUSDT (53,930 vol) and EWTUSDT (10,070 vol); 2 days of klines and ~24 h of trades (716-4,197 prints per market) landed; `list` and `show` print as expected. On the first run 3 of 4 markets failed with a TLS `internal error` on their first request (4 cold connections opened at once); the re-run fetched them cleanly. Not changed: the re-run path exists for this; if it recurs, warm the connection pool with one request before the pool starts.
- **Card committed?** No card is committed in this branch: approving a dataset is the Owner's gate 7, so the first real card appears when the Owner runs `ttp dataset approve` and commits `docs/knowledge-base/datasets/<name>.md`.
- Commands: `uv run pytest` -> 82 passed, 3 deselected; `uv run pytest -m live tests/test_trades_download.py` -> 1 passed; `uv run ruff check` and `uv run ruff format --check` clean.
