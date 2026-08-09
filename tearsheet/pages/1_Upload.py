"""Upload a trade export CSV, process it, and store it in this session's history."""
from __future__ import annotations

import streamlit as st

from src.auth import require_login
from src.parsing import FORMAT_FILLS, FORMAT_TRADES, UnsupportedFileFormatError, load_upload
from src.report import render_trade_report
from src.session_store import add_session
from src.statistics import compute_stats

st.set_page_config(page_title="Upload - Trading Tearsheet", layout="wide")

username, name = require_login()

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
    st.warning(
        "This looks like a raw fills export (individual order executions), not a "
        "closed-trades export. Trade-level statistics require matching fills into "
        "round-trip trades, which isn't implemented yet - showing the raw fill "
        "blotter only. Upload the 'closed trades' export instead to see full stats. "
        "This file is not saved to your session history."
    )
    st.subheader("Fills")
    st.dataframe(data, use_container_width=True)
    st.download_button(
        "Download parsed fills (CSV)",
        data=data.to_csv(index=False).encode("utf-8"),
        file_name="parsed_fills.csv",
        mime="text/csv",
    )
    st.stop()

trades = data
stats = compute_stats(trades)

# Streamlit reruns this whole script on every interaction, and the uploaded
# file stays in the widget's state - guard so re-runs don't re-append the
# same upload to session history every time.
file_key = (uploaded_file.name, uploaded_file.size)
if st.session_state.get("_last_upload_key") != file_key:
    session_id = add_session(username, uploaded_file.name, trades, stats)
    st.session_state["_last_upload_key"] = file_key
    st.session_state["_last_upload_session_id"] = session_id
else:
    session_id = st.session_state["_last_upload_session_id"]

st.success(f"Processed and saved as session `{session_id[:8]}`.")

render_trade_report(trades, stats)
