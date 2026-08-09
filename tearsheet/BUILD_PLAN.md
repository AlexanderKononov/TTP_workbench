# Trading Tearsheet App — Build Plan

Status: **Phase 1 and Phase 2 implemented** (local prototype + multipage app with login). Phase 3+ (Supabase persistence, deployment) not started. See [README.md](README.md) for setup/run instructions.
Base doc: [tearsheet_infro_memo.md](tearsheet_infro_memo.md)
Sample data: [data/trades_example/](../data/trades_example/)

---

## 1. Overview

A small private web app for **two users** to:

1. Register / log in.
2. Upload a trade-export CSV.
3. See computed statistics for that upload (PnL, drawdown, win rate, mean PnL/trade, etc.).
4. Browse history of past uploads and compare month-to-month / user-to-user.

Scope is intentionally small — this is a personal analytics tool, not a production system. Follows the stack and principles in the memo (Streamlit + Supabase), scaled to what's actually needed for 2 users and small CSVs.

---

## 2. Input Data — What We're Actually Parsing

Two example files were provided from the same export tool, covering the same session (2026-07-23) but in **two different report formats**:

### Format A — "Fills" export (order-level detail)
`export_trades_2026-07-23_2026-07-23.csv`

```
Market;Symbol;Key;Date;Time;Direction;Price;Quantity;Total;Fee
BINANCE;ONUSDT;"BINANCE Etlsa***";2026-07-23;05:08:03;buy;0.1766;124;21.8984;0.0109492
...
```

- One row per individual order fill (a symbol/session can have dozens of partial fills).
- `Direction` is `buy`/`sell`, `Total` = `Price × Quantity`, `Fee` is per-fill.
- 74 rows in the sample, covering 3 symbols: `ONUSDT`, `RIFUSDT`, `BROCCOLIF3BUSDT`.
- **Not directly usable for trade-level PnL** — fills must be matched/netted per symbol into a round-trip trade first.

### Format B — "Closed trades" export (trade-level, pre-netted)
`export_trades_2026-07-23_2026-07-23 2.csv`

```
Market;Symbol;Key;Date;Time;Direction;Profit;"Profit %";Fee
BINANCE;ONUSDT;"BINANCE Etlsa***";2026-07-23;05:08:03;sell;-3.92681148;-0.77593934;0.50778148
BINANCE;RIFUSDT;"BINANCE Etlsa***";2026-07-23;04:20:40;sell;4.73572215;0.93704845;0.50276785
BINANCE;BROCCOLIF3BUSDT;"BINANCE Etlsa***";2026-07-23;04:12:38;buy;-3.19402938;-0.64232887;0.49590838
```

- **One row per closed trade** (exactly one row per symbol here — confirms this is the netted/aggregated view of Format A's fills for the same session).
- `Profit` = realized gross P&L for that trade, `Profit %` = return %, `Fee` = total fees for the round-trip.
- **This is the format the app should use as the primary source for statistics** — it's already at the correct granularity (one row = one trade), so no matching/reconstruction logic is needed for v1.

### Parsing decisions

- Delimiter is `;`, decimals use `.`, files may have a UTF-8 BOM — use `pandas.read_csv(path, sep=";", encoding="utf-8-sig")`.
- Auto-detect format by column set: if `Profit` column present → Format B (trade-level). If `Price`/`Quantity`/`Total` present → Format A (fills).
- **v1**: only Format B drives statistics. Format A, if uploaded, is stored and shown as a raw fill blotter (no stats) with a note that trade-matching isn't implemented yet.
- **v2 (stretch)**: implement FIFO matching to derive Format-B-equivalent trades from Format A fills, so raw fill exports work too.
- Net PnL per trade = `Profit - Fee` (Profit appears to be fee-exclusive, based on Fee being listed separately).

---

## 3. Statistics to Compute (per uploaded session, and rolled up historically)

From the trade-level table (`symbol, direction, profit, profit_pct, fee, net_pnl, timestamp`):

| Metric | Definition |
|---|---|
| Trade count | `count(rows)` |
| Gross PnL | `sum(profit)` |
| Total fees | `sum(fee)` |
| Net PnL | `sum(profit) - sum(fee)` |
| Win rate | `count(net_pnl > 0) / count(rows)` |
| Mean PnL / trade | `mean(net_pnl)` |
| Median PnL / trade | `median(net_pnl)` |
| Average win / average loss | `mean(net_pnl where net_pnl>0)` / `mean(net_pnl where net_pnl<0)` |
| Largest win / largest loss | `max(net_pnl)` / `min(net_pnl)` |
| Profit factor | `sum(wins) / abs(sum(losses))` |
| Max drawdown | max peak-to-trough drop of the **cumulative net PnL curve** (sorted by time) |
| Expectancy | `win_rate * avg_win - (1-win_rate) * abs(avg_loss)` |
| Sharpe (optional, later) | `mean(net_pnl) / std(net_pnl)` — noisy with few trades; label as "low sample size" under ~30 trades |

These are computed by a pure function (`compute_stats(trades_df) -> dict`) that's independently unit-testable, decoupled from Streamlit — per memo principle #12.

---

## 4. Tech Stack (per memo, unchanged)

- **Streamlit** — UI, upload, charts, tables.
- **Supabase** — Postgres (sessions, statistics), Auth, Storage (raw CSVs).
- **pandas** — parsing and stats.
- **Plotly** — equity curve, drawdown chart, PnL histogram.
- **GitHub** — source control, no secrets/private data committed.

```
streamlit, pandas, numpy, plotly, supabase, pyarrow, python-dotenv
```

---

## 5. Auth / "Simple Registration" — Recommendation

The memo leans toward Supabase Auth or Streamlit OIDC. For exactly 2 known users and a genuinely simple v1, recommend:

- **v1 (local prototype, no cloud yet):** `streamlit-authenticator` with a small YAML config listing the 2 users (username, name, bcrypt password hash). "Registration" = you run a tiny one-off script to add a user + hashed password to the YAML — not a public sign-up form (not needed for 2 people, and avoids building/securing a sign-up flow). This satisfies "simple registration" without any external service.
- **v2 (once deployed to Streamlit Cloud):** move credentials into Supabase Auth (email/password), so login works from anywhere and Row Level Security can scope each user to their own data. Registration still stays admin-created (Supabase dashboard or a small script) rather than public self-serve — there's no reason for public sign-up with 2 users.

This matches memo principle: "do not implement custom password hashing/authentication unless required" — `streamlit-authenticator` handles hashing/session cookies for us; we're not rolling our own crypto.

---

## 6. Data Model (Supabase — Phase 2+)

```
participants
------------
id, user_id, name, created_at

sessions
--------
id, participant_id, session_date, file_name, format (A|B), uploaded_at, status

trades                              -- new: individual rows, not just aggregate stats
------
id, session_id, participant_id, symbol, direction, profit, profit_pct, fee, net_pnl, trade_time

session_statistics
-------------------
session_id, participant_id, trade_count, gross_pnl, net_pnl, win_rate,
mean_pnl, median_pnl, avg_win, avg_loss, largest_win, largest_loss,
profit_factor, max_drawdown, expectancy, created_at
```

Adding a `trades` table (beyond what the memo sketched) so per-symbol/per-trade drill-down and re-aggregation (e.g. "PnL by symbol") don't require re-parsing the original CSV every time.

File storage: `sessions/<participant_id>/<session_id>/original.csv` (per memo).

---

## 7. App Pages

```
app.py                 → login gate, redirect to Dashboard
pages/
  1_Upload.py           → pick participant context (self), upload CSV, preview, "Process" button, shows results immediately after processing
  2_Session_Details.py  → pick a past session, see its full stats + equity curve + trade table
  3_History.py          → table of all past sessions for the logged-in user, filter by date range
  4_Compare.py          → side-by-side stats for both participants (only if both consent to shared visibility)
```

---

## 8. File Structure

```
tearsheet/
├── app.py
├── requirements.txt
├── .env.example
├── auth_config.yaml          # v1 only — streamlit-authenticator users (bcrypt hashes, gitignored if it ever has real hashes)
├── pages/
│   ├── 1_Upload.py
│   ├── 2_Session_Details.py
│   ├── 3_History.py
│   └── 4_Compare.py
├── src/
│   ├── parsing.py            # CSV format detection + loading (Format A / B)
│   ├── statistics.py         # compute_stats(trades_df) -> dict, pure/testable
│   ├── database.py           # Supabase client wrapper (phase 2+)
│   └── visualisation.py      # Plotly equity curve, drawdown, PnL histogram
└── tests/
    ├── test_parsing.py
    └── test_statistics.py
```

---

## 9. Development Phases

### Phase 1 — Local prototype (no auth, no DB) — ✅ done
- `src/parsing.py`: load Format B CSV → trades DataFrame.
- `src/statistics.py`: `compute_stats()`.
- `src/visualisation.py`: equity curve + drawdown chart + win/loss histogram.
- Single-page Streamlit app: upload → process → show KPIs + charts + trade table.
- Validated end-to-end against both sample files in `data/trades_example/` (10 pytest tests).

### Phase 2 — Multi-page + local login — ✅ done
- Split into `pages/1_Upload.py`, `2_Session_Details.py`, `3_History.py`, `4_Compare.py`.
- `src/auth.py`: login gate using `streamlit-authenticator`, credentials in gitignored `auth_config.yaml` (template: `auth_config.example.yaml`), hashing via `scripts/hash_password.py`.
- `src/session_store.py`: session history shared across users of the running server process via `st.cache_resource` (not `st.session_state`, since Compare needs to see both participants' uploads) — explicitly a Phase-3 stand-in, resets on restart.
- `src/report.py`: shared KPI/chart/table rendering used by both Upload and Session Details.
- Gotcha hit and fixed: wrapping `stauth.Authenticate(...)` in `@st.cache_resource` broke, because its constructor creates a cookie-manager widget internally and Streamlit forbids widgets inside cached functions — it's now built fresh each rerun instead.
- Gotcha hit and fixed: `st.file_uploader`'s selected file persists across reruns, so without a guard the Upload page would re-append the same file to session history on every unrelated rerun — guarded with a `(name, size)` fingerprint in `st.session_state`.
- 18 pytest tests total, including page-boot smoke tests (`tests/test_app_pages.py`) and a full simulated login (username/password → bcrypt check → authenticated session) via `streamlit.testing.v1.AppTest`.
- `src/auth.py` reads credentials from `st.secrets["auth"]` first (for Streamlit Cloud, set via Settings → Secrets, never committed), falling back to local `auth_config.yaml` if no secrets are configured — see `.streamlit/secrets.toml.example`. Both paths verified end-to-end with a simulated login.

### Phase 3 — Persistence (Supabase)
- Create Supabase project, tables from §6.
- Save original CSV to Storage, trades + session_statistics to Postgres on upload.
- `2_Session_Details.py` and `3_History.py` read from Supabase instead of recomputing.

### Phase 4 — Historical reporting & comparison
- Monthly rollups (group `session_statistics` by month).
- `4_Compare.py` side-by-side view.
- Row Level Security so each user only queries their own rows (per memo §"Participant Comparison").

### Phase 5 — Deploy
- Push to GitHub, deploy on Streamlit Community Cloud, move auth to Supabase Auth, set secrets (`SUPABASE_URL`, `SUPABASE_KEY`), retire the local YAML auth file.

---

## 10. Setup Instructions (Phase 1 start)

```bash
cd tearsheet
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -r requirements.txt
streamlit run app.py
```

`requirements.txt` (Phase 1 subset, extend in later phases):

```
streamlit
pandas
numpy
plotly
pyarrow
```

Add `supabase`, `python-dotenv`, `streamlit-authenticator` starting Phase 2/3.

No secrets exist yet in Phase 1 — nothing to configure. From Phase 3 on, follow memo §"Environment / Secrets" (`.env` locally, Streamlit Secrets in the cloud; never commit `SUPABASE_URL`/`SUPABASE_KEY`).

---

## 11. Testing

- `tests/test_parsing.py`: format detection on both sample files, BOM/`;`-delimiter handling, malformed-file rejection.
- `tests/test_statistics.py`: `compute_stats()` against a small hand-computed fixture (known PnL, known win rate, known drawdown) — not just the live sample data, so expected values are independently verified.

---

## 12. Open Questions / Assumptions to Confirm Before Building

1. **Profit sign convention** — confirmed `Profit` excludes `Fee` (they're separate columns); net PnL = `Profit - Fee`. Flag if the real export ever nets these already.
2. **"Registration"** — assumed to mean "the 2 of you can log in," not an open public sign-up form. Confirm before building a sign-up UI that isn't actually needed.
3. **Format A (raw fills)** — v1 stores and displays them but does not compute trade-level stats from them (no FIFO matching yet). Confirm this is acceptable, or whether fills-matching should be pulled into v1 scope.
4. **Currency** — sample data has no currency column; assume single currency (USDT) for v1, no FX conversion.
