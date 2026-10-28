# 03: Download klines into a dataset

**Role:** quant-engineer

**Status:** done

**Blocked by:** 02

**What to build:** Kline history for a market lands in the project's dataset storage and can be queried, with a dataset card describing it. Completes M0.

Spec: [../spec.md](../spec.md)

- [x] Connector fetches 1-minute klines with pagination over a requested range
- [x] `ttp download klines <market> --days N [--dataset <name>]` writes Parquet partitioned by venue / market / data type / date under the gitignored `data/` root; re-running fills gaps without duplicating rows
- [x] A DuckDB-based reader returns a market's klines for a time range as a DataFrame
- [x] A dataset card is written per the docs/knowledge-base/README.md template (source, markets, type/resolution, range, location, collected by, gaps)
- [x] Tests cover pagination, dedup/gap-fill and the reader using fixtures

## Comments

quant-engineer, 2026-10-28:

- **Connector:** `MexcClient.klines(symbol, start_ms, end_ms)` in `src/ttp/venues/mexc/client.py` pages `GET /api/v3/klines` (weight 1, through the existing `WeightLimiter`). Probed live on 2026-10-28: the page limit is 500 even if `limit=1000` is sent; `startTime` is ignored unless `endTime` is also sent (MEXC then returns the latest candles), so every page sends both; rows come back for open times in `[startTime, endTime)`. MEXC keeps exactly 30 days of 1m history; older ranges return `[]`, so an empty page advances by a full page instead of stopping. Idle minutes come back as flat zero-volume candles, so a missing minute is a real gap.
- **Storage** (`src/ttp/data/store.py`): `data/datasets/<dataset>/venue=<v>/market=<m>/type=<data type>/date=<UTC date>/data.parquet`. Each `DataType` declares its time column, dedup key, column types and optional sampling interval. Trades and 1 s book snapshots will be new `DataType` entries in the same layout. The reader globs `*.parquet` per date dir, so the recorder can append extra part files per day. Writes merge per date partition: dedup on key, last write wins, written to a temp file and then `os.replace`d. Times are stored as naive UTC `TIMESTAMP` and returned tz-aware UTC.
- **Reader:** `DatasetStore.read(dataset, venue, market, data_type, start, end)` returns rows with `start <= time < end` as a DataFrame. It prunes date partitions in Python and queries with DuckDB `read_parquet`.
- **Gap-fill:** the downloader reads which minutes of `[now - N days, current minute)` are already stored and asks MEXC only for the missing contiguous ranges. The current, unclosed minute is never stored. Minutes MEXC doesn't have (older than 30 days) are asked for again on each run; that costs about 6 weight-1 requests and is harmless.
- **Dataset card** (`src/ttp/data/cards.py`): regenerated from storage on every download at `docs/knowledge-base/datasets/<dataset>.md`, following the README template, plus a per-series table and a list of internal gaps. Hand edits are overwritten (the card says so). "Collected by" is the short commit, with `-dirty` added if tracked files changed. Per-(venue, data type) source text and quirks live in `SOURCES`.
- **Defaults:** `--dataset` defaults to `adhoc`. Dataset names must match `[a-z0-9][a-z0-9._-]*`, which also blocks path traversal. The market accepts `ADXUSDT` or `ADX/USDT`. Paths are relative to the working directory, so run `ttp` from the repo root.
- **Dependencies added:** `duckdb>=2.0,<3`, `pandas>=3.1,<4`. Writing goes through DuckDB `COPY`, so no pyarrow is needed.
- **QUESTION FOR OWNER:** should generated dataset cards be committed to the repo? (They are under `docs/`, which is tracked; the data itself is gitignored.) The conservative choice for now: the downloader writes the card and leaves committing it to the Owner. No card is committed in this branch.
- Live check (2026-10-28): `--days 32` on ADXUSDT fetched 43,200 rows (30 days) in about 37 s. A re-run added 0 rows, and the card showed 0 internal gaps.

**Governor decision (dataset cards):** cards for Owner-approved datasets (ticket 06) are committed, since the knowledge base is the provenance record backtests cite. Cards for the default `adhoc` dataset are gitignored. Branch-parallel work from now on uses isolated worktrees, so the integration branch is `governor/initial-infrastructure-spec` in the main checkout only.
