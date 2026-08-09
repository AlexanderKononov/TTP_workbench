from pathlib import Path

import pytest

from src.parsing import (
    FORMAT_FILLS,
    FORMAT_TRADES,
    UnsupportedFileFormatError,
    load_upload,
    normalize_trades,
    read_csv,
)

DATA_DIR = Path(__file__).resolve().parents[2] / "data" / "trades_example"
FILLS_CSV = DATA_DIR / "export_trades_2026-07-23_2026-07-23.csv"
TRADES_CSV = DATA_DIR / "export_trades_2026-07-23_2026-07-23 2.csv"


def test_detects_closed_trades_format():
    fmt, trades = load_upload(TRADES_CSV)
    assert fmt == FORMAT_TRADES
    assert len(trades) == 3
    assert set(trades["symbol"]) == {"ONUSDT", "RIFUSDT", "BROCCOLIF3BUSDT"}


def test_detects_fills_format():
    fmt, fills = load_upload(FILLS_CSV)
    assert fmt == FORMAT_FILLS
    assert len(fills) == 74


def test_net_pnl_is_profit_minus_fee():
    _, trades = load_upload(TRADES_CSV)
    onusdt = trades[trades["symbol"] == "ONUSDT"].iloc[0]
    assert onusdt["profit"] == pytest.approx(-3.92681148)
    assert onusdt["fee"] == pytest.approx(0.50778148)
    assert onusdt["net_pnl"] == pytest.approx(-3.92681148 - 0.50778148)


def test_bom_and_semicolon_delimiter_handled():
    df = read_csv(TRADES_CSV)
    assert "Market" in df.columns
    assert df.columns[0] == "Market"  # no leftover BOM character


def test_unsupported_format_raises():
    import io

    bad_csv = io.StringIO("A;B;C\n1;2;3\n")
    with pytest.raises(UnsupportedFileFormatError):
        load_upload(bad_csv)


def test_normalize_trades_missing_columns_raises():
    import pandas as pd

    df = pd.DataFrame({"Market": ["X"], "Profit": [1.0]})
    with pytest.raises(UnsupportedFileFormatError):
        normalize_trades(df)
