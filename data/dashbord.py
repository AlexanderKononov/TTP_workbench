import streamlit as st
import sqlite3
import pandas as pd
import plotly.express as px
import json
import subprocess
from pathlib import Path
from datetime import datetime

# --- Paths ---
BASE_DIR = Path(__file__).parent
DB_PATH = BASE_DIR / "metadata.db"
CONFIG_PATH = BASE_DIR / "tracks.json"

st.set_page_config(page_title="Trading Bot Data Hub", layout="wide")

st.title("📈 Trading Bot Data Hub")

# --- Tabs ---
tab1, tab2 = st.tabs(["📊 Data Viewer", "⚙️ Data Manager"])

# ==============================================================
# TAB 1: Data Viewer
# ==============================================================
with tab1:
    #st.header("📊 Data Viewer")

    def get_available_assets():
        with sqlite3.connect(DB_PATH) as conn:
            query = "SELECT DISTINCT asset_type FROM files"
            return [row[0] for row in conn.execute(query).fetchall()]

    def get_available_tickers(asset_type):
        with sqlite3.connect(DB_PATH) as conn:
            query = "SELECT DISTINCT ticker FROM files WHERE asset_type = ?"
            return [row[0] for row in conn.execute(query, (asset_type,)).fetchall()]

    def load_data(asset_type, ticker):
        with sqlite3.connect(DB_PATH) as conn:
            query = """
            SELECT resolution, start_date, end_date
            FROM files
            WHERE asset_type = ? AND ticker = ?
            ORDER BY start_date
            """
            return pd.read_sql(query, conn, params=(asset_type, ticker))

    # --- UI Row for selection ---
    col1, col2 = st.columns(2)
    with col1:
        asset_types = get_available_assets()
        asset_type = st.selectbox("Asset Type", asset_types)
    with col2:
        tickers = get_available_tickers(asset_type) if asset_type else []
        ticker = st.selectbox("Ticker", tickers)

    # --- Show data if selected ---
    if asset_type and ticker:
        df = load_data(asset_type, ticker)

        if df.empty:
            st.warning("⚠ No data found for this ticker")
        else:
            # --- Status notification ---
            last_date = pd.to_datetime(df["end_date"]).max()
            today = pd.to_datetime(datetime.today().date())
            delay = (today - last_date).days

            if delay <= 0:
                st.success(f"✅ Data is up to date (last update {last_date.date()})")
            elif 1 <= delay <= 6:
                st.warning(f"⚠ Data is {delay} days late (last update {last_date.date()})")
            else:
                st.error(f"🚨 Data is {delay} days late (last update {last_date.date()})")

            # --- Timeline plot ---
            fig = px.timeline(
                df, x_start="start_date", x_end="end_date",
                y="resolution", color="resolution",
                title=f"Data coverage for {ticker}"
            )
            fig.update_yaxes(autorange="reversed")  # better view
            st.plotly_chart(fig, use_container_width=True)

            # --- Table ---
            st.subheader("Available Files")
            st.dataframe(df)

# ==============================================================
# TAB 2: Data Manager
# ==============================================================
with tab2:
    #st.header("⚙️ Data Manager")

    # --- Run collector ---
    col1, col2 = st.columns([1, 4])

    with col1:
        run_collector = st.button("🔄 Collect Data")

    with col2:
        st.markdown("Click to fetch the **latest data** from Yahoo Finance.")

    if run_collector:
        with st.spinner("Collecting data..."):
            try:
                result = subprocess.run(
                    ["python", "collector.py"],
                    capture_output=True, text=True, cwd=BASE_DIR
                )
                if result.stdout:
                    st.text_area("Collector Output", result.stdout, height=200)
                if result.stderr:
                    st.error(result.stderr)
            except Exception as e:
                st.error(f"❌ Failed to run collector: {e}")

    # --- Show existing tracks ---
    st.subheader("📋 Existing Tracks")
    if CONFIG_PATH.exists():
        with open(CONFIG_PATH, "r") as f:
            tracks = json.load(f)
        if "tracks" in tracks and tracks["tracks"]:
            tracks_df = pd.DataFrame(tracks["tracks"])
            st.dataframe(tracks_df)
        else:
            st.info("No tracks defined yet.")
    else:
        st.info("No config file found.")

    # --- Add new track ---
    st.subheader("➕ Add New Track")
    with st.form("add_track_form", clear_on_submit=True):
        col1, col2, col3 = st.columns(3)
        with col1:
            new_asset_type = st.selectbox("Asset Type", ["stock", "crypto"])
        with col2:
            new_ticker = st.text_input("Ticker", placeholder="e.g. AAPL or BTC-USD")
        with col3:
            new_resolution = st.selectbox("Resolution", ["1d", "1h", "15m", "5m"])

        submitted = st.form_submit_button("Add Track")

        if submitted and new_ticker:
            if CONFIG_PATH.exists():
                with open(CONFIG_PATH, "r") as f:
                    tracks = json.load(f)
            else:
                tracks = {"tracks": []}

            new_track = {
                "asset_type": new_asset_type,
                "ticker": new_ticker,
                "resolution": new_resolution,
            }

            if new_track not in tracks["tracks"]:
                tracks["tracks"].append(new_track)
                with open(CONFIG_PATH, "w") as f:
                    json.dump(tracks, f, indent=2)
                st.success(f"✅ Added {new_track}")
            else:
                st.info("ℹ️ Track already exists")
