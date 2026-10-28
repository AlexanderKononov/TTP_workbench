"""CSV loading and format detection for trade exports.

Two export formats are supported (see tearsheet/BUILD_PLAN.md §2):

Format B ("closed trades", one row per round-trip trade) - drives statistics.
Format A ("fills", one row per order execution) - stored/displayed only, no
trade-level matching yet.
"""
from __future__ import annotations

import io

import pandas as pd

FORMAT_B_MARKER_COLUMNS = {"Profit"}
FORMAT_A_MARKER_COLUMNS = {"Price", "Quantity", "Total"}

FORMAT_TRADES = "B"
FORMAT_FILLS = "A"


class UnsupportedFileFormatError(Exception):
    """Raised when an uploaded CSV doesn't match a known export format."""


def read_csv(file) -> pd.DataFrame:
    """Read a semicolon-delimited export CSV (handles UTF-8 BOM)."""
    df = pd.read_csv(file, sep=";", encoding="utf-8-sig")
    df.columns = [c.strip() for c in df.columns]
    return df


def detect_format(df: pd.DataFrame) -> str:
    cols = set(df.columns)
    if FORMAT_B_MARKER_COLUMNS.issubset(cols):
        return FORMAT_TRADES
    if FORMAT_A_MARKER_COLUMNS.issubset(cols):
        return FORMAT_FILLS
    raise UnsupportedFileFormatError(
        f"Unrecognised CSV columns: {sorted(cols)}. "
        "Expected either a 'Profit' column (closed trades export) or "
        "'Price'/'Quantity'/'Total' columns (fills export)."
    )


def normalize_trades(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize a Format B (closed trades) export into the trades schema.

    Output columns: trade_time, market, symbol, direction, profit,
    profit_pct, fee, net_pnl.
    """
    required = {"Market", "Symbol", "Date", "Time", "Direction", "Profit", "Fee"}
    missing = required - set(df.columns)
    if missing:
        raise UnsupportedFileFormatError(f"Closed trades export is missing columns: {sorted(missing)}")

    out = pd.DataFrame()
    out["trade_time"] = pd.to_datetime(df["Date"].astype(str) + " " + df["Time"].astype(str))
    out["market"] = df["Market"]
    out["symbol"] = df["Symbol"]
    out["direction"] = df["Direction"]
    out["profit"] = pd.to_numeric(df["Profit"])
    out["profit_pct"] = pd.to_numeric(df["Profit %"]) if "Profit %" in df.columns else pd.NA
    out["fee"] = pd.to_numeric(df["Fee"])
    out["net_pnl"] = out["profit"] - out["fee"]
    out = out.sort_values("trade_time").reset_index(drop=True)
    return out


def normalize_fills(df: pd.DataFrame) -> pd.DataFrame:
    """Normalize a Format A (fills) export for display only (no stats)."""
    required = {"Market", "Symbol", "Date", "Time", "Direction", "Price", "Quantity", "Total", "Fee"}
    missing = required - set(df.columns)
    if missing:
        raise UnsupportedFileFormatError(f"Fills export is missing columns: {sorted(missing)}")

    out = pd.DataFrame()
    out["fill_time"] = pd.to_datetime(df["Date"].astype(str) + " " + df["Time"].astype(str))
    out["market"] = df["Market"]
    out["symbol"] = df["Symbol"]
    out["direction"] = df["Direction"]
    out["price"] = pd.to_numeric(df["Price"])
    out["quantity"] = pd.to_numeric(df["Quantity"])
    out["total"] = pd.to_numeric(df["Total"])
    out["fee"] = pd.to_numeric(df["Fee"])
    out = out.sort_values("fill_time").reset_index(drop=True)
    return out


def load_upload(file) -> tuple[str, pd.DataFrame]:
    """Load an uploaded file-like object.

    Returns (format, normalized_dataframe) where format is FORMAT_TRADES or
    FORMAT_FILLS.
    """
    raw = read_csv(file)
    fmt = detect_format(raw)
    if fmt == FORMAT_TRADES:
        return fmt, normalize_trades(raw)
    return fmt, normalize_fills(raw)
