import json
import sqlite3
from pathlib import Path
from datetime import datetime, timedelta
import yfinance as yf
import pandas as pd

DB_PATH = Path(__file__).parent / "metadata.db"
STORE_DIR = Path(__file__).parent / "raw"

# --- DB helpers ---
def get_latest_entry(asset_type, ticker, resolution):
    """Return the latest stored file info for given asset_type/ticker/resolution."""
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.cursor()
        cur.execute("""
            SELECT start_date, end_date, file_path
            FROM files
            WHERE asset_type = ? AND ticker = ? AND resolution = ?
            ORDER BY end_date DESC LIMIT 1
        """, (asset_type, ticker, resolution))
        row = cur.fetchone()
    return row  # (start_date, end_date, file_path) or None

def insert_file(asset_type, ticker, resolution, start_date, end_date, file_path):
    """Insert new file entry into the metadata DB."""
    with sqlite3.connect(DB_PATH) as conn:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO files (asset_type, ticker, resolution, start_date, end_date, file_path)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (asset_type, ticker, resolution, start_date, end_date, str(file_path)))
        conn.commit()

# --- Collector main ---
def collect_data():
    # Load config
    config = json.load(open(Path(__file__).parent / "tracks.json"))
    tracks = config["tracks"]  # Each track: {"asset_type": "stock", "ticker": "AAPL", "resolution": "1d"}

    today = datetime.today().strftime("%Y-%m-%d")

    for track in tracks:
        asset_type = track["asset_type"]
        ticker = track["ticker"]
        resolution = track["resolution"]

        print(f"\n🔎 Checking {asset_type.upper()} {ticker} {resolution}")

        

        # --- inside collect_data() loop for each track ---
        latest = get_latest_entry(asset_type, ticker, resolution)

        if latest:
            _, last_end, _ = latest
            start_date_dt = datetime.strptime(last_end, "%Y-%m-%d") + timedelta(days=1)
            print(f"   Last data until {last_end}. Fetching from {start_date_dt.strftime('%Y-%m-%d')} → {today}...")
        else:
            # Load limits
            limits_config = json.load(open(Path(__file__).parent / "config_limits.json"))
            limits = limits_config["limits"]
            max_days = limits.get(resolution, 365*2)  # fallback to 2 years if not in config

            # First download → use limit from config
            start_date_dt = datetime.today() - timedelta(days=max_days)
            print(f"   No data in DB. Fetching last {max_days} days: {start_date_dt.strftime('%Y-%m-%d')} → {today}...")

        start_date = start_date_dt.strftime("%Y-%m-%d")

        # Check if period is valid
        if start_date_dt >= datetime.today():
            print(f"⚠ No new data to download. Latest data already covers {start_date} or beyond.")
            continue

        # Fetch from Yahoo Finance
        df = yf.download(ticker, interval=resolution, start=start_date, end=today, progress=False)

        if df.empty:
            print("⚠ No new data returned from Yahoo Finance")
            continue

        # Prepare output directory: raw/<asset_type>/<ticker>/<resolution>/
        outdir = STORE_DIR / asset_type / ticker / resolution
        outdir.mkdir(parents=True, exist_ok=True)

        # Save file
        file_name = f"{ticker}_{resolution}_{start_date}_{today}.parquet"
        file_path = outdir / file_name
        df.reset_index(inplace=True)
        df.to_parquet(file_path, index=False)

        # Update DB
        insert_file(asset_type, ticker, resolution, start_date, today, file_path)
        print(f"✅ Saved {file_path}")

if __name__ == "__main__":
    collect_data()
