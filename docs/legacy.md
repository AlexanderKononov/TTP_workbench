# Legacy Components

Code that predates the crypto trading system. Whether each piece is kept, reused or retired is an open scoping question ([CONTEXT.md](../CONTEXT.md)). Until then, treat these as independent projects: each has its own dependencies and runs from its own directory.

## Root bot/strategy scaffolding (`bots/`, `strategies/`, `config/`, `tests/`, `utils.py/`)

Early equities/Alpaca scaffolding, runs against the root `requirements.txt` and `.venv`.

- Mostly empty stubs (0 bytes): `bots/simple_bot.py`, `strategies/momentum.py`, `config/broker_factory.py`, `main.py`, `tests/test_strategies.py`, `utils.py/logging_utils.py`. Check contents before assuming behaviour.
- `config/settings.py` loads `.env` from the repo root and exposes Alpaca credentials (`APCA_API_KEY_ID`, `APCA_API_SECRET_KEY`, `APCA_API_BASE_URL`) plus `INITIAL_CASH`.
- `strategies/sma_pandas.py`: pure-pandas SMA crossover signals + a long-only backtest loop (`generate_sma_signals`, `simple_backtest`).
- `strategies/sma_backtrader.py`: the same idea as a `backtrader.Strategy` (`SmaCross`).
- `utils.py/` is a **package directory** despite the name; `perf.py` has `performance_metrics()` (Sharpe/CAGR/drawdown). Nothing imports it.
- `tests/test_alpaca_connection.py` is a manual smoke check that calls Alpaca at import time; run it with `python tests/test_alpaca_connection.py`, not under pytest.

## `data/`: Yahoo Finance pipeline

Collects OHLCV via `yfinance` into partitioned Parquet, indexed in SQLite. Full details: [data/README.md](../data/README.md).

- Layout: `data/raw/<asset_type>/<ticker>/<resolution>/<ticker>_<resolution>_<start>_<end>.parquet`, tracked in `data/metadata.db` (table `files`). Both gitignored.
- Config: `data/tracks.json` (what to collect), `data/config_limits.json` (Yahoo intraday history limits, used as first-run lookback).
- `collector.py` fetches only the gap since the last stored range; `indexer.py` rebuilds `metadata.db` from the `raw/` tree.
- `dashbord.py` (misspelled on purpose; check references before renaming): Streamlit coverage viewer + data manager. `streamlit run data/dashbord.py`.
- Its gap-fill + Parquet + metadata-index pattern is a candidate to reuse for crypto backtest data.

## `tearsheet/`: trade tearsheet app

The most complete piece: a multi-page Streamlit app where two users upload trade-export CSVs and view PnL/drawdown/win-rate statistics. Own venv, `requirements.txt` and pytest suite. Design history: [tearsheet/BUILD_PLAN.md](../tearsheet/BUILD_PLAN.md) (partly outdated, so trust the code).

```bash
cd tearsheet
python -m venv .venv && .venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py      # log in with Alx/Alx or Ars/Ars
pytest                    # full suite
```

- `src/parsing.py`: `load_upload()` auto-detects **Format B** (closed trades, has `Profit`) vs **Format A** (fills, has `Price`/`Quantity`/`Total`).
- `src/matching.py`: FIFO-nets Format A fills into Format-B-equivalent round-trip trades.
- `src/statistics.py`, `src/activity.py`: pure pandas, no Streamlit dependency; keep them that way.
- `src/database.py`: Supabase persistence (schema in `supabase/schema.sql`). Stats are recomputed on read, never snapshotted; trades are deduped by a deterministic `trade_hash`. Needs `SUPABASE_URL`/`SUPABASE_KEY` from `.env` or Streamlit secrets.
- `src/auth.py`: a hardcoded two-user name gate, not real security (BUILD_PLAN §5's `streamlit-authenticator` design was never built).
- `src/report.py`: the shared KPI/chart layout for the Upload and Session Details pages.
- Gotcha: `st.file_uploader` keeps its file across reruns; `pages/1_Upload.py` guards re-ingest with a `(name, size)` fingerprint.
- Candidate reuse: post-trade analysis of executed cases.

## Other root files

- `package.json` / `package-lock.json`: Supabase JS deps, unused by the Python code.
- `.devcontainer/`: Python 3.11 container that auto-starts the tearsheet app on port 8501.
