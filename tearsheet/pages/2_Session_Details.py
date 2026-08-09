"""Combined metrics across one or more previously uploaded sessions.

Defaults to all of the logged-in user's sessions; the multiselect lets them
narrow it down. Statistics are recomputed from the pooled trades of the
selected sessions (rather than averaging each session's own stats dict), so
win rate, drawdown, etc. are correct for the combined set.
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

from src.auth import current_user
from src.report import render_trade_report
from src.session_store import list_sessions
from src.statistics import compute_stats

username = current_user()
if not username:
    st.info("Please log in from the home page.")
    st.stop()

st.title("Session Details")

sessions = list_sessions(participant=username)
if not sessions:
    st.info("No sessions yet - upload one on the Upload page first.")
    st.stop()

labels = [f"{s['file_name']} — {s['uploaded_at']:%Y-%m-%d %H:%M} ({s['stats']['trade_count']} trades)" for s in sessions]
selected_indices = st.multiselect(
    "Sessions",
    options=range(len(sessions)),
    default=list(range(len(sessions))),
    format_func=lambda i: labels[i],
)

if not selected_indices:
    st.info("Select at least one session above to see its statistics.")
    st.stop()

selected_sessions = [sessions[i] for i in selected_indices]
st.caption(f"Showing combined statistics across {len(selected_sessions)} of {len(sessions)} session(s).")

combined_trades = (
    pd.concat([s["trades"] for s in selected_sessions], ignore_index=True)
    .sort_values("trade_time")
    .reset_index(drop=True)
)
stats = compute_stats(combined_trades)
render_trade_report(combined_trades, stats)
