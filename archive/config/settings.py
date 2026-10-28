# config/settings.py
from pathlib import Path
from dotenv import load_dotenv
import os

# load .env from project root (adjust path if needed)
ROOT = Path(__file__).resolve().parents[1]
load_dotenv(ROOT / ".env")

# Alpaca
ALPACA_KEY = os.getenv("APCA_API_KEY_ID")
ALPACA_SECRET = os.getenv("APCA_API_SECRET_KEY")
ALPACA_BASE_URL = os.getenv("APCA_API_BASE_URL", "https://paper-api.alpaca.markets")

# Binance (optional
#NANCE_KEY = os.getenv("BINANCE_API_KEY")
#INANCE_SECRET = os.getenv("BINANCE_SECRET_KEY")

# Strategy defaults
INITIAL_CASH = float(os.getenv("INITIAL_CASH", "10000"))
