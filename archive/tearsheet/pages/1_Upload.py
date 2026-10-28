"""Upload a trade export CSV, process it, and persist it to Supabase."""
from __future__ import annotations

import streamlit as st

from src.auth import current_user
from src.database import get_all_trades, save_upload
from src.matching import match_fills_to_trades
from src.parsing import FORMAT_FILLS, UnsupportedFileFormatError, load_upload
from src.report import render_trade_report
from src.statistics import compute_stats

username = current_user()
if not username:
    st.info("Please log in from the home page.")
    st.stop()
name = username

st.title("Upload Session")
st.caption(f"Uploading as **{name}**.")

uploaded_file = st.file_uploader("Upload trade export (.csv)", type=["csv"])

if uploaded_file is None:
    st.info(
        "Waiting for a CSV upload. Expected: semicolon-delimited export with a "
        "'Profit' column (closed trades) or 'Price'/'Quantity'/'Total' columns (fills)."
    )
    st.stop()

try:
    fmt, data = load_upload(uploaded_file)
except UnsupportedFileFormatError as exc:
    st.error(f"Could not parse this file: {exc}")
    st.stop()
except Exception as exc:  # malformed CSV, encoding issues, etc.
    st.error(f"Failed to read file: {exc}")
    st.stop()

if fmt == FORMAT_FILLS:
    fills = data
    trades, open_positions = match_fills_to_trades(fills)

    st.caption(
        f"Fills export: matched {len(trades)} closed round-trip trade(s) from "
        f"{len(fills)} fills via FIFO netting per symbol (oldest lots closed first)."
    )

    if not open_positions.empty:
        st.warning(
            f"{len(open_positions)} symbol(s) still have an open position at the end of "
            "this file (fills never netted back to zero), so no realized PnL exists for "
            "them yet - excluded from statistics below."
        )
        st.dataframe(open_positions, use_container_width=True)

    with st.expander("Raw fills used for this match"):
        st.dataframe(fills, use_container_width=True)
        st.download_button(
            "Download parsed fills (CSV)",
            data=fills.to_csv(index=False).encode("utf-8"),
            file_name="parsed_fills.csv",
            mime="text/csv",
        )

    if trades.empty:
        st.info(
            "No closed round-trip trades could be matched from this file - every "
            "position is still open. This file is not saved to your session history."
        )
        st.stop()
else:
    trades = data

stats = compute_stats(trades)

# Streamlit reruns this whole script on every interaction, and the uploaded
# file stays in the widget's state - guard so re-runs don't re-append the
# same upload to session history every time.
file_key = (uploaded_file.name, uploaded_file.size)
if st.session_state.get("_last_upload_key") != file_key:
    result = save_upload(username, uploaded_file.name, fmt, trades)
    st.session_state["_last_upload_key"] = file_key
    st.session_state["_last_upload_result"] = result
else:
    result = st.session_state["_last_upload_result"]

session_id = result["session_id"]
if result["duplicate_count"]:
    st.info(
        f"Processed and saved as session `{session_id[:8]}` - "
        f"{result['inserted_count']} new trade(s), {result['duplicate_count']} "
        "were already in your history and were skipped."
    )
else:
    st.success(f"Processed and saved as session `{session_id[:8]}` ({result['inserted_count']} trade(s)).")

render_trade_report(trades, stats)

st.divider()
st.subheader("All-Time Statistics")
st.caption(f"Combined statistics across every trade **{name}** has ever uploaded.")
all_trades = get_all_trades(username)
render_trade_report(all_trades, compute_stats(all_trades))
