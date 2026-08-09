from pathlib import Path

import pandas as pd
import pytest

from src.matching import match_fills_to_trades
from src.parsing import load_upload

DATA_DIR = Path(__file__).resolve().parents[2] / "data" / "trades_example"
FILLS_CSV = DATA_DIR / "export_trades_2026-07-23_2026-07-23.csv"
TRADES_CSV = DATA_DIR / "export_trades_2026-07-23_2026-07-23 2.csv"


def _fill(time, symbol, direction, price, qty, fee, market="X"):
    total = price * qty
    return {
        "fill_time": pd.Timestamp(time),
        "market": market,
        "symbol": symbol,
        "direction": direction,
        "price": float(price),
        "quantity": float(qty),
        "total": float(total),
        "fee": float(fee),
    }


def test_matches_real_export_against_brokers_own_closed_trades():
    """The two sample CSVs describe the same underlying trades in two
    formats - the fills export should FIFO-match into the same net_pnl and
    fee the broker's own closed-trades export reports per symbol, and leave
    no open positions (every position in this sample closes within the
    file).
    """
    _, fills = load_upload(FILLS_CSV)
    _, broker_trades = load_upload(TRADES_CSV)

    matched, open_positions = match_fills_to_trades(fills)

    assert open_positions.empty
    assert len(matched) == len(broker_trades) == 3
    assert set(matched["symbol"]) == set(broker_trades["symbol"])

    for symbol in matched["symbol"]:
        m = matched[matched["symbol"] == symbol].iloc[0]
        b = broker_trades[broker_trades["symbol"] == symbol].iloc[0]
        assert m["fee"] == pytest.approx(b["fee"], abs=1e-8)
        assert m["net_pnl"] == pytest.approx(b["profit"], abs=1e-8)
        assert m["direction"] == b["direction"]
        assert m["trade_time"] == b["trade_time"]


def test_simple_long_round_trip():
    fills = pd.DataFrame(
        [
            _fill("2026-01-01 10:00", "AAA", "buy", 100, 10, 1),
            _fill("2026-01-01 11:00", "AAA", "sell", 110, 10, 1),
        ]
    )
    trades, open_positions = match_fills_to_trades(fills)

    assert open_positions.empty
    assert len(trades) == 1
    t = trades.iloc[0]
    assert t["direction"] == "buy"
    assert t["profit"] == pytest.approx(100.0)  # 1100 - 1000
    assert t["fee"] == pytest.approx(2.0)
    assert t["net_pnl"] == pytest.approx(98.0)
    assert t["quantity"] == pytest.approx(10.0)
    assert t["entry_time"] == pd.Timestamp("2026-01-01 10:00")
    assert t["trade_time"] == pd.Timestamp("2026-01-01 11:00")


def test_position_reversal_splits_into_two_trades():
    """A closing fill larger than the open position both closes the old
    trade and opens a new one in the opposite direction.
    """
    fills = pd.DataFrame(
        [
            _fill("2026-01-01 10:00", "AAA", "buy", 10, 100, 2),  # opens long 100
            _fill("2026-01-01 11:00", "AAA", "sell", 12, 150, 3),  # closes 100, opens short 50
            _fill("2026-01-01 12:00", "AAA", "buy", 11, 50, 1),  # closes short 50
        ]
    )
    trades, open_positions = match_fills_to_trades(fills)

    assert open_positions.empty
    assert len(trades) == 2

    long_trade = trades.iloc[0]
    assert long_trade["direction"] == "buy"
    assert long_trade["trade_time"] == pd.Timestamp("2026-01-01 11:00")
    assert long_trade["quantity"] == pytest.approx(100.0)
    assert long_trade["profit"] == pytest.approx(200.0)  # 1200 - 1000
    assert long_trade["fee"] == pytest.approx(4.0)  # 2 + (3 * 100/150)
    assert long_trade["net_pnl"] == pytest.approx(196.0)

    short_trade = trades.iloc[1]
    assert short_trade["direction"] == "sell"
    assert short_trade["entry_time"] == pd.Timestamp("2026-01-01 11:00")
    assert short_trade["trade_time"] == pd.Timestamp("2026-01-01 12:00")
    assert short_trade["quantity"] == pytest.approx(50.0)
    assert short_trade["profit"] == pytest.approx(50.0)  # 600 - 550
    assert short_trade["fee"] == pytest.approx(2.0)  # (3 * 50/150) + 1
    assert short_trade["net_pnl"] == pytest.approx(48.0)


def test_unclosed_position_excluded_from_trades_and_reported_as_open():
    fills = pd.DataFrame(
        [
            _fill("2026-01-01 10:00", "AAA", "buy", 5, 100, 1),
            _fill("2026-01-01 11:00", "AAA", "sell", 6, 40, 0.5),  # only partially closes
        ]
    )
    trades, open_positions = match_fills_to_trades(fills)

    assert trades.empty
    assert len(open_positions) == 1
    pos = open_positions.iloc[0]
    assert pos["symbol"] == "AAA"
    assert pos["direction"] == "buy"
    assert pos["quantity"] == pytest.approx(60.0)
    assert pos["avg_price"] == pytest.approx(5.0)
    assert pos["opened_at"] == pd.Timestamp("2026-01-01 10:00")


def test_empty_fills_returns_empty_frames():
    fills = pd.DataFrame(columns=["fill_time", "market", "symbol", "direction", "price", "quantity", "total", "fee"])
    trades, open_positions = match_fills_to_trades(fills)
    assert trades.empty
    assert open_positions.empty
