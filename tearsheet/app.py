"""Entry point: login gate + landing page.

Phase 2 per BUILD_PLAN.md - multipage app with local auth. See src/auth.py
for the login mechanism and src/session_store.py for the (in-memory, Phase-3-
pending) session history shared across users of this running server.
"""
from __future__ import annotations

import streamlit as st

from src.auth import require_login
from src.session_store import list_sessions

st.set_page_config(page_title="Trading Tearsheet", layout="wide")

username, name = require_login()

st.title("Trading Tearsheet")
st.write(f"Welcome, **{name}**.")

my_sessions = list_sessions(participant=username)
st.metric("Your uploaded sessions (this server run)", len(my_sessions))

st.markdown(
    """
Use the sidebar to navigate:

- **Upload** — upload a trade export CSV and see its statistics.
- **Session Details** — revisit a previously uploaded session.
- **History** — all your sessions, with monthly rollups.
- **Compare** — side-by-side stats for both participants.
"""
)

st.caption(
    "Session history currently lives in server memory only (Phase 2) and resets "
    "on server restart - persistent storage (Supabase) is Phase 3 of the build plan."
)
