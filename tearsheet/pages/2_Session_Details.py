"""Revisit a previously uploaded session for the logged-in user."""
from __future__ import annotations

import streamlit as st

from src.auth import require_login
from src.report import render_trade_report
from src.session_store import list_sessions

st.set_page_config(page_title="Session Details - Trading Tearsheet", layout="wide")

username, name = require_login()

st.title("Session Details")

sessions = list_sessions(participant=username)
if not sessions:
    st.info("No sessions yet - upload one on the Upload page first.")
    st.stop()

labels = [f"{s['file_name']} — {s['uploaded_at']:%Y-%m-%d %H:%M} ({s['stats']['trade_count']} trades)" for s in sessions]
selected = st.selectbox("Session", options=range(len(sessions)), format_func=lambda i: labels[i])

session = sessions[selected]
render_trade_report(session["trades"], session["stats"])
