"""Daily trading-activity aggregation: trade frequency and upload cadence.

Pure/pandas-only, like statistics.py, so it's unit-testable without Streamlit
or session_store in the loop.
"""
from __future__ import annotations

import pandas as pd


def compute_daily_activity(sessions: list[dict], as_of: pd.Timestamp | None = None) -> pd.DataFrame:
    """Build a one-row-per-day activity table spanning a user's history.

    Each session dict is expected to have the shape produced by
    database.list_sessions: "trades" (a DataFrame with a trade_time column),
    "uploaded_at" (datetime), "file_name" (str).

    The date range runs from the earliest trade/upload through as_of
    (defaults to today), with zero-filled gap days included - gaps are the
    point, since the chart this feeds is meant to show how often (or
    rarely) the user actually trades.

    Returns columns: date, trade_count, uploaded (bool), upload_count,
    uploaded_files (list[str]). Empty (no rows) if sessions is empty.
    """
    columns = ["date", "trade_count", "uploaded", "upload_count", "uploaded_files"]
    if not sessions:
        return pd.DataFrame(columns=columns)

    trade_dates: list[pd.Timestamp] = []
    upload_rows: list[tuple[pd.Timestamp, str]] = []
    for session in sessions:
        trades = session["trades"]
        if not trades.empty:
            trade_dates.extend(pd.to_datetime(trades["trade_time"]).dt.normalize().tolist())
        upload_rows.append((pd.Timestamp(session["uploaded_at"]).normalize(), session["file_name"]))

    trade_counts = pd.Series(trade_dates).value_counts().sort_index() if trade_dates else pd.Series(dtype=int)

    upload_df = pd.DataFrame(upload_rows, columns=["date", "file_name"])
    uploaded_files_by_day = upload_df.groupby("date")["file_name"].apply(list)

    bounds = [pd.Timestamp(as_of).normalize() if as_of is not None else pd.Timestamp.now().normalize()]
    if not trade_counts.empty:
        bounds += [trade_counts.index.min(), trade_counts.index.max()]
    if not uploaded_files_by_day.empty:
        bounds += [uploaded_files_by_day.index.min(), uploaded_files_by_day.index.max()]

    full_range = pd.date_range(min(bounds), max(bounds), freq="D")

    daily = pd.DataFrame({"date": full_range})
    daily["trade_count"] = daily["date"].map(trade_counts).fillna(0).astype(int)
    files = daily["date"].map(uploaded_files_by_day)
    daily["uploaded_files"] = files.apply(lambda v: v if isinstance(v, list) else [])
    daily["uploaded"] = daily["uploaded_files"].str.len() > 0
    daily["upload_count"] = daily["uploaded_files"].str.len()
    return daily[columns]
