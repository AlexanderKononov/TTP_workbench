from dotenv import load_dotenv
import os
from alpaca.trading.client import TradingClient

# Load secrets
load_dotenv()

ALPACA_KEY = os.getenv("APCA_API_KEY_ID")
ALPACA_SECRET = os.getenv("APCA_API_SECRET_KEY")

# True = paper trading, False = live
trading_client = TradingClient(ALPACA_KEY, ALPACA_SECRET, paper=True)

try:
    account = trading_client.get_account()
    print("✅ Alpaca connection OK")
    print("Account status:", account.status)
    print("Buying power:", account.buying_power)
except Exception as e:
    print("❌ Alpaca connection FAILED:", e)
