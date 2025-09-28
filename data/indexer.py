import sqlite3
from pathlib import Path
import re

DB_PATH = Path(__file__).parent / "metadata.db"
RAW_DIR = Path(__file__).parent / "raw"

def init_db():
    """Initialize the SQLite database and create the files table with asset_type."""
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    cur.execute("""
    CREATE TABLE IF NOT EXISTS files (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        asset_type TEXT NOT NULL,
        ticker TEXT NOT NULL,
        resolution TEXT NOT NULL,
        start_date TEXT NOT NULL,
        end_date TEXT NOT NULL,
        file_path TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)
    
    conn.commit()
    conn.close()
    print("✅ Database initialized at", DB_PATH)


def populate_db_from_files():
    """
    Scan the raw/ folder structure and populate metadata.db with existing files.
    Assumes files are named as <ticker>_<resolution>_<start_date>_<end_date>.parquet
    and folder structure is raw/<asset_type>/<ticker>/<resolution>/
    """
    conn = sqlite3.connect(DB_PATH)
    cur = conn.cursor()

    # Regex to extract ticker, resolution, start_date, end_date
    pattern = re.compile(r"(?P<ticker>.+)_(?P<resolution>.+)_(?P<start>\d{4}-\d{2}-\d{2})_(?P<end>\d{4}-\d{2}-\d{2})\.parquet")

    files_added = 0

    for asset_type_dir in RAW_DIR.iterdir():
        if not asset_type_dir.is_dir():
            continue
        asset_type = asset_type_dir.name  # stock, crypto, etc.
        
        for ticker_dir in asset_type_dir.iterdir():
            if not ticker_dir.is_dir():
                continue
            ticker = ticker_dir.name

            for resolution_dir in ticker_dir.iterdir():
                if not resolution_dir.is_dir():
                    continue
                resolution = resolution_dir.name

                for file_path in resolution_dir.glob("*.parquet"):
                    match = pattern.match(file_path.name)
                    if not match:
                        print(f"⚠ Skipping file with unexpected name: {file_path}")
                        continue
                    
                    start_date = match.group("start")
                    end_date = match.group("end")

                    # Check if already exists in DB
                    cur.execute("""
                        SELECT 1 FROM files
                        WHERE asset_type=? AND ticker=? AND resolution=? AND start_date=? AND end_date=?
                    """, (asset_type, ticker, resolution, start_date, end_date))
                    if cur.fetchone():
                        continue  # already in DB

                    # Insert into DB
                    cur.execute("""
                        INSERT INTO files (asset_type, ticker, resolution, start_date, end_date, file_path)
                        VALUES (?, ?, ?, ?, ?, ?)
                    """, (asset_type, ticker, resolution, start_date, end_date, str(file_path)))
                    files_added += 1

    conn.commit()
    conn.close()
    print(f"✅ Finished populating DB. {files_added} new file(s) added.")


if __name__ == "__main__":
    init_db()
    populate_db_from_files()
