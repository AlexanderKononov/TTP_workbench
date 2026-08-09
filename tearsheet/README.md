# Trading Tearsheet

Small private Streamlit app for two users to upload trade-export CSVs and see PnL, drawdown, win rate, and other stats. See [BUILD_PLAN.md](BUILD_PLAN.md) for the full design/roadmap and [tearsheet_infro_memo.md](tearsheet_infro_memo.md) for the original brief.

## Setup

```bash
python -m venv .venv
.venv\Scripts\activate          # Windows
pip install -r requirements.txt
```

Set up your two users:

```bash
copy auth_config.example.yaml auth_config.yaml
python scripts/hash_password.py "your-new-password"
```

Edit `auth_config.yaml`: set real usernames/names/emails, paste the generated hash over each placeholder `password`, and change `cookie.key` to any random string. `auth_config.yaml` is gitignored — never commit it.

## Run

```bash
streamlit run app.py
```

Log in, then use the sidebar: **Upload** a CSV → **Session Details** / **History** / **Compare**.

## Run tests

```bash
pytest
```

## Deploy to Streamlit Community Cloud

1. Push this repo to GitHub. `auth_config.yaml` and `.streamlit/secrets.toml` are gitignored — they never get pushed, which is correct.
2. Go to [share.streamlit.io](https://share.streamlit.io) → sign in with GitHub → **New app**.
3. Pick the repo/branch, set the main file path to `tearsheet/app.py` (adjust if the repo root is already `tearsheet/`), and deploy.
4. In the app's **Settings → Secrets**, paste the contents of [.streamlit/secrets.toml.example](.streamlit/secrets.toml.example) with real values:
   - Generate each password hash locally first: `python scripts/hash_password.py "your-new-password"`.
   - Set `cookie.key` to a random string.
5. Save secrets — the app picks up `st.secrets["auth"]` automatically (see `src/auth.py`), no code change needed. Local dev keeps using `auth_config.yaml` unless you also drop a `.streamlit/secrets.toml` locally.

Note: session history (Upload/History/Compare) currently lives in server memory only (Phase 2) — Streamlit Cloud free-tier apps sleep after inactivity and lose that memory on wake. Persistent history needs Supabase (Phase 3), not yet implemented.

## Current status (Phase 2 of BUILD_PLAN.md)

- CSV parsing + statistics engine — done, tested against real sample exports.
- Multipage app + local login (`streamlit-authenticator`), credentials via `st.secrets` (cloud) or `auth_config.yaml` (local) — done.
- Session history — **in-memory only**, shared by all users of the current server process, resets on restart. Supabase persistence (Phase 3) not yet implemented.
- Format A (raw fills) is stored/displayed but not matched into trade-level stats yet.
