"""All of the logged-in user's sessions, with a monthly rollup."""
from __future__ import annotations

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

from src.auth import require_login
from src.session_store import list_sessions

st.set_page_config(page_title="History - Trading Tearsheet", layout="wide")

username, name = require_login()

st.title("History")
st.caption(f"All sessions uploaded by **{name}** during this server run.")

sessions = list_sessions(participant=username)
if not sessions:
    st.info("No sessions yet - upload one on the Upload page first.")
    st.stop()

overview = pd.DataFrame(
    [
        {
            "File": s["file_name"],
            "Uploaded": s["uploaded_at"],
            "Session Date": s["session_date"],
            "Trades": s["stats"]["trade_count"],
            "Net PnL": s["stats"]["net_pnl"],
            "Win Rate": s["stats"]["win_rate"],
            "Max Drawdown": s["stats"]["max_drawdown"],
        }
        for s in sessions
    ]
)
st.dataframe(overview, use_container_width=True)

st.divider()
st.subheader("Monthly Rollup")

overview["Month"] = pd.to_datetime(overview["Session Date"]).dt.to_period("M").astype(str)
monthly = overview.groupby("Month").agg(
    sessions=("File", "count"),
    trades=("Trades", "sum"),
    net_pnl=("Net PnL", "sum"),
    avg_win_rate=("Win Rate", "mean"),
).reset_index()

col1, col2 = st.columns(2)
with col1:
    fig = go.Figure(go.Bar(x=monthly["Month"], y=monthly["net_pnl"]))
    fig.update_layout(title="Net PnL by Month", margin=dict(l=40, r=20, t=50, b=40))
    st.plotly_chart(fig, use_container_width=True)
with col2:
    fig = go.Figure(go.Bar(x=monthly["Month"], y=monthly["sessions"]))
    fig.update_layout(title="Sessions Uploaded by Month", margin=dict(l=40, r=20, t=50, b=40))
    st.plotly_chart(fig, use_container_width=True)

st.dataframe(monthly, use_container_width=True)
