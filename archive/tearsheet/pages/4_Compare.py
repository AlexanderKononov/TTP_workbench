"""Side-by-side stats for both participants.

Computed cumulatively over each participant's full trade history in
Supabase (src.database.get_all_trades), so this is always an all-time vs.
all-time comparison rather than a per-session average - see SUPABASE_PLAN.md.
"""
from __future__ import annotations

import pandas as pd
import streamlit as st

from src.auth import current_user
from src.database import get_all_trades, list_participants
from src.statistics import compute_stats

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
    trades = get_all_trades(p)
    if trades.empty:
        continue
    stats = compute_stats(trades)
    rows.append(
        {
            "Participant": p,
            "Trades": stats["trade_count"],
            "Net PnL": stats["net_pnl"],
            "Win Rate": stats["win_rate"],
            "Max Drawdown": stats["max_drawdown"],
        }
    )

if len(rows) < 2:
    st.info("Need at least two participants with closed trades to compare.")
    st.stop()

comparison = pd.DataFrame(rows).set_index("Participant")
st.dataframe(comparison, use_container_width=True)

st.bar_chart(comparison[["Net PnL"]])
