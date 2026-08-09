# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Repository shape

This is not one app — it's a workbench containing three loosely-related, independently-runnable Python pieces that each have their own dependencies and (in two cases) their own virtualenv. There is no shared build/lint/test command across the repo; always work inside the relevant subdirectory.

1. **Root (`bots/`, `strategies/`, `config/`, `data/`, `tests/`)** — early-stage trading bot scaffolding. Most files here are empty stubs (`bots/simple_bot.py`, `strategies/momentum.py`, `config/broker_factory.py`, `main.py`, `tests/test_strategies.py`, `utils.py/logging_utils.py` are all 0 bytes). Treat them as placeholders, not working code — check file contents before assuming behavior.
2. **`data/`** — a self-contained Yahoo Finance data pipeline with its own README (`data/README.md`). Runs against the root venv/`requirements.txt`.
3. **`tearsheet/`** — a Streamlit app for analyzing trade-export CSVs. This is the most complete, tested part of the repo. It has its own venv, `requirements.txt`, and pytest suite, and should be treated as a separate project rooted at `tearsheet/`.

## Root-level bot/strategy scaffolding

- `config/settings.py` loads `.env` from the repo root and exposes Alpaca credentials (`APCA_API_KEY_ID`, `APCA_API_SECRET_KEY`, `APCA_API_BASE_URL`) plus `INITIAL_CASH`. `config/broker_factory.py` is an empty stub despite the name.
- `strategies/sma_pandas.py` — pure pandas SMA crossover signal generator + a simple long-only backtest loop (`generate_sma_signals`, `simple_backtest`), no external deps beyond pandas.
- `strategies/sma_backtrader.py` — the same SMA-crossover idea implemented as a `backtrader.Strategy` subclass (`SmaCross`), for use with the `backtrader` engine instead of the hand-rolled loop above.
- `utils.py/` is a **directory** (package), not a module — despite the `.py`-looking name it contains `__init__.py` and `perf.py` (Sharpe/CAGR/drawdown calc via `performance_metrics()`). Nothing in the repo currently imports it.
- `tests/test_alpaca_connection.py` is a manual connectivity smoke-check (prints account status), not a pytest test — it executes API calls against Alpaca at import time using credentials from `.env`. Run it directly with `python tests/test_alpaca_connection.py`, don't expect it to run cleanly under `pytest` without live credentials.

## `data/` — financial data pipeline

Collects OHLCV data from Yahoo Finance (`yfinance`) into partitioned Parquet files, indexed by a local SQLite DB. See `data/README.md` for the full feature list.

- **Storage layout:** `data/raw/<asset_type>/<ticker>/<resolution>/<ticker>_<resolution>_<start>_<end>.parquet`, tracked in `data/metadata.db` (table `files`). `data/raw/` and `metadata.db` are gitignored.
- **Config:** `data/tracks.json` lists which `{asset_type, ticker, resolution}` combinations to collect; `data/config_limits.json` encodes Yahoo Finance's per-resolution intraday history limits (e.g. `"1m": 7` days), used as the initial lookback window when no prior data exists.
- **`data/collector.py`** — for each track, looks up the latest stored date range in `metadata.db` and fetches only the gap up to today (or the config-limit window on first run), writes a new Parquet file, and inserts a new DB row. Run with `python data/collector.py` (must run from a context where `data/` is on the path, or invoke via the dashboard).
- **`data/indexer.py`** — (re)creates the `files` table and backfills `metadata.db` by scanning the `raw/` directory tree and parsing filenames with a regex. Run once to (re)initialize: `python data/indexer.py`.
- **`data/dashbord.py`** (filename is misspelled, not a typo to "fix" casually — check for references before renaming) — Streamlit dashboard with two tabs: a data-coverage viewer (Plotly timeline over `metadata.db`) and a data manager that can invoke `collector.py` as a subprocess and append new tracks to `tracks.json`. Run with `streamlit run data/dashbord.py`.

## `tearsheet/` — trade tearsheet Streamlit app

Small private multi-page Streamlit app for two hardcoded users to upload trade-export CSVs and view PnL/drawdown/win-rate statistics. Full design doc and phase history: [tearsheet/BUILD_PLAN.md](tearsheet/BUILD_PLAN.md); original brief: [tearsheet/tearsheet_infro_memo.md](tearsheet/tearsheet_infro_memo.md).

### Setup & run

```bash
cd tearsheet
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -r requirements.txt
streamlit run app.py
```

Log in with `Alx`/`Alx` or `Ars`/`Ars` (see "Auth" below).

### Tests

```bash
cd tearsheet
pytest                          # full suite
pytest tests/test_statistics.py # single file
pytest tests/test_statistics.py::test_name  # single test
```

Test files: `test_parsing.py`, `test_statistics.py`, `test_session_store.py`, `test_auth.py`, `test_app_pages.py` (page-boot smoke tests using `streamlit.testing.v1.AppTest`, including a simulated full login flow).

### Architecture

- **`app.py`** — entry point: login gate (`src.auth.require_login`) then landing page.
- **`pages/1_Upload.py` … `4_Compare.py`** — Streamlit's file-based multipage routing. `1_Upload.py` uploads+processes a CSV, `2_Session_Details.py` revisits a stored session, `3_History.py` lists a user's sessions, `4_Compare.py` shows both participants side by side.
- **`src/parsing.py`** — CSV loading and format auto-detection. Two trade-export formats, distinguished by column set:
  - **Format B** ("closed trades", has a `Profit` column) — one row per round-trip trade; this is the format that drives statistics (`normalize_trades`).
  - **Format A** ("fills", has `Price`/`Quantity`/`Total` columns) — one row per order fill; stored/displayed only via `normalize_fills`, **not** matched into trade-level stats yet (that's planned Phase-2+ scope, see BUILD_PLAN.md §2).
  - `load_upload()` is the single entry point pages should call; it returns `(format, normalized_df)`.
- **`src/statistics.py`** — `compute_stats(trades_df) -> dict` and `equity_curve(trades_df) -> df`. Deliberately pure/pandas-only functions with no Streamlit dependency, so they're unit-testable in isolation (memo principle: keep processing separate from UI).
- **`src/visualisation.py`** — Plotly chart builders (equity curve, drawdown, PnL histogram, PnL-by-symbol) consumed by `src/report.py`.
- **`src/report.py`** — `render_trade_report(trades, stats)` is the shared KPI/chart/table layout used by both the Upload and Session Details pages, so that layout exists in exactly one place.
- **`src/auth.py`** — **current implementation is a hardcoded 2-user dict** (`Alx`/`Alx`, `Ars`/`Ars`) checked in-process via `st.session_state`; explicitly a name-gate, not real security, per the module's own docstring. Note this is simpler than what `BUILD_PLAN.md` §5 describes (`streamlit-authenticator`, bcrypt, `st.secrets`) — that's the target design, not what's currently in the file; check `src/auth.py` directly rather than trusting the build plan for current auth behavior.
- **`src/session_store.py`** — in-memory session history shared across all users of the running server process via `st.cache_resource` (not `st.session_state`, since Compare needs to see every participant's uploads). This is an explicit Phase-2 stand-in for Supabase persistence (Phase 3, not yet implemented) — it resets on every server restart and won't survive a multi-instance deploy.

### Known gotchas (from BUILD_PLAN.md, worth knowing before touching related code)

- Do not wrap `stauth.Authenticate(...)`-style constructors (if `streamlit-authenticator` is introduced later) in `@st.cache_resource` — its constructor creates a widget internally and Streamlit forbids widgets inside cached functions.
- `st.file_uploader`'s selected file persists across Streamlit reruns; `1_Upload.py` guards against re-appending the same file to session history on unrelated reruns using a `(name, size)` fingerprint in `st.session_state`.

## Cross-cutting notes

- No linter/formatter config exists anywhere in the repo (no ruff/flake8/black/pyproject.toml) — don't assume one when making style calls.
- Two independent `requirements.txt` files exist (root and `tearsheet/`) with no shared install step; install into whichever venv matches the code you're touching.
- `data/raw/`, `data/metadata.db`, `.env`, and `.streamlit/` are gitignored — don't expect them to be present in a fresh checkout, and don't commit them.
