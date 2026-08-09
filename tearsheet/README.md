# Trading Tearsheet

Small private Streamlit app for two users to upload trade-export CSVs and see PnL, drawdown, win rate, and other stats. See [BUILD_PLAN.md](BUILD_PLAN.md) for the full design/roadmap and [tearsheet_infro_memo.md](tearsheet_infro_memo.md) for the original brief.

## Setup

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -r requirements.txt
```

No credentials setup needed — the two users (`Alx`/`Alx` and `Ars`/`Ars`) are built into `src/auth.py`. This is a simple name-gate, not real security (see the module docstring); fine for a private 2-person tool.

## Run

```bash
streamlit run app.py
```

Log in with `Alx`/`Alx` or `Ars`/`Ars`, then use the sidebar: **Upload** a CSV → **Session Details** / **History** / **Compare**.

## Run tests

```bash
pytest
```

## Deploy to Streamlit Community Cloud

1. Push this repo to GitHub.
2. Go to [share.streamlit.io](https://share.streamlit.io) → sign in with GitHub → **New app**.
3. Pick the repo/branch, set the main file path to `tearsheet/app.py` (adjust if the repo root is already `tearsheet/`), and deploy.

No secrets to configure — login credentials are hardcoded in `src/auth.py` since they aren't meant to protect anything sensitive.

Note: session history (Upload/History/Compare) currently lives in server memory only (Phase 2) — Streamlit Cloud free-tier apps sleep after inactivity and lose that memory on wake. Persistent history needs Supabase (Phase 3), not yet implemented.

## Current status (Phase 2 of BUILD_PLAN.md)

- CSV parsing + statistics engine — done, tested against real sample exports.
- Multipage app + simple login (`src/auth.py`, hardcoded username=password per user) — done.
- Session history — **in-memory only**, shared by all users of the current server process, resets on restart. Supabase persistence (Phase 3) not yet implemented.
- Format A (raw fills) is stored/displayed but not matched into trade-level stats yet.
