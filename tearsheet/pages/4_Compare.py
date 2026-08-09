"""Side-by-side stats for both participants.

Uses the shared in-process session store (src/session_store.py), so this
only shows data uploaded while the current server process has been running -
full cross-session history arrives with Supabase in Phase 3.
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

from src.auth import current_user
from src.session_store import list_participants, list_sessions

username = current_user()
if not username:
    st.info("Please log in from the home page.")
    st.stop()

st.title("Participant Comparison")

participants = list_participants()
if len(participants) < 2:
    st.info(
        "Need uploads from at least two participants to compare (currently: "
        f"{', '.join(participants) if participants else 'none'}). "
        "Have both users upload a session first."
    )
    st.stop()

rows = []
for p in participants:
    sessions = list_sessions(participant=p)
    trade_counts = [s["stats"]["trade_count"] for s in sessions]
    net_pnls = [s["stats"]["net_pnl"] for s in sessions]
    win_rates = [s["stats"]["win_rate"] for s in sessions]
    drawdowns = [s["stats"]["max_drawdown"] for s in sessions]
    rows.append(
        {
            "Participant": p,
            "Sessions": len(sessions),
            "Trades": sum(trade_counts),
            "Net PnL": sum(net_pnls),
            "Avg Win Rate": sum(win_rates) / len(win_rates),
            "Max Drawdown": max(drawdowns),
        }
    )

comparison = pd.DataFrame(rows).set_index("Participant")
st.dataframe(comparison, use_container_width=True)

st.bar_chart(comparison[["Net PnL"]])
