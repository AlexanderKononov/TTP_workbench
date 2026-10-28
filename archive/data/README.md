📊 Financial Data Pipeline

An automated pipeline to collect, store, and manage financial data (stocks, crypto, etc.) from Yahoo Finance.
The system uses a SQLite metadata index, structured storage, and a Streamlit dashboard for easy exploration and management.

🚀 Features

- Automated collection of historical & fresh financial data.

- Storage by asset type → ticker → resolution → .parquet files.

- SQLite metadata DB to track available data.

- Streamlit dashboard to view timelines, files, and manage tracks.

- Config-driven setup via tracks.json and config_limits.json.

⚙️ Installation
# Clone the repo
```
git clone https://github.com/yourname/fin-data-pipeline.git
cd fin-data-pipeline

# Create and activate virtual environment
python -m venv .venv
source .venv/bin/activate   # On Linux/Mac
.venv\Scripts\activate      # On Windows

# Install dependencies
pip install -r requirements.txt

# Initialize DB
python indexer.py
```

🛠 Usage
1. Configure tracks

Edit tracks.json to add your assets:
```
[
  {"asset": "stock", "ticker": "AAPL", "resolution": "1d"},
  {"asset": "crypto", "ticker": "BTC-USD", "resolution": "1h"}
]
```

2. Run collector

Fetch and store fresh data:
```
python collector.py
```
3. Launch dashboard

Explore data and manage tracks:
```
streamlit run dashbord.py
```
```
📂 Project Structure
data_pipeline/
│── raw/                 # Stored findata
│── metadata.db          # SQLite index
│── collector.py         # Collect fresh data
│── indexer.py           # Init & populate DB
│── dashbord.py          # Streamlit dashboard
│── tracks.json          # Config for tickers/resolutions
│── config_limits.json   # Limits for Yahoo Finance
```
📌 Notes

Yahoo Finance free tier has limits (e.g. intraday max ~60 days).

Keep your tracks.json small to avoid hitting rate limits.

This pipeline is for research/education — not financial advice.