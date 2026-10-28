import pandas as pd
import pytest

from src.activity import compute_daily_activity


def _session(uploaded_at, file_name, trade_days):
    trades = pd.DataFrame({"trade_time": pd.to_datetime(trade_days)}) if trade_days else pd.DataFrame({"trade_time": []})
    return {"uploaded_at": pd.Timestamp(uploaded_at), "file_name": file_name, "trades": trades}


def test_empty_sessions_returns_empty_frame():
    daily = compute_daily_activity([])
    assert daily.empty
    assert list(daily.columns) == ["date", "trade_count", "uploaded", "upload_count", "uploaded_files"]


def test_gap_days_are_zero_filled():
    sessions = [_session("2026-01-01 09:00", "a.csv", ["2026-01-01 10:00", "2026-01-01 11:00"])]
    daily = compute_daily_activity(sessions, as_of=pd.Timestamp("2026-01-04"))

    assert list(daily["date"].dt.strftime("%Y-%m-%d")) == [
        "2026-01-01",
        "2026-01-02",
        "2026-01-03",
        "2026-01-04",
    ]
    assert list(daily["trade_count"]) == [2, 0, 0, 0]


def test_upload_flag_and_multiple_uploads_same_day():
    sessions = [
        _session("2026-01-01 09:00", "morning.csv", ["2026-01-01 09:30"]),
        _session("2026-01-01 15:00", "afternoon.csv", ["2026-01-01 15:30", "2026-01-01 15:45"]),
    ]
    daily = compute_daily_activity(sessions, as_of=pd.Timestamp("2026-01-01"))

    assert len(daily) == 1
    row = daily.iloc[0]
    assert row["trade_count"] == 3
    assert row["uploaded"] is True or bool(row["uploaded"]) is True
    assert row["upload_count"] == 2
    assert set(row["uploaded_files"]) == {"morning.csv", "afternoon.csv"}


def test_trades_across_multiple_sessions_and_days():
    sessions = [
        _session("2026-01-01 09:00", "a.csv", ["2026-01-01 10:00"]),
        _session("2026-01-03 09:00", "b.csv", ["2026-01-03 10:00", "2026-01-03 11:00", "2026-01-03 12:00"]),
    ]
    daily = compute_daily_activity(sessions, as_of=pd.Timestamp("2026-01-03"))

    assert list(daily["trade_count"]) == [1, 0, 3]
    assert list(daily["uploaded"]) == [True, False, True]


def test_range_extends_to_as_of_even_with_no_recent_activity():
    sessions = [_session("2026-01-01 09:00", "a.csv", ["2026-01-01 10:00"])]
    daily = compute_daily_activity(sessions, as_of=pd.Timestamp("2026-01-10"))
    assert daily["date"].max() == pd.Timestamp("2026-01-10")
    assert daily["date"].min() == pd.Timestamp("2026-01-01")


def test_session_with_no_trades_still_counts_as_upload():
    sessions = [_session("2026-01-01 09:00", "empty.csv", [])]
    daily = compute_daily_activity(sessions, as_of=pd.Timestamp("2026-01-01"))
    assert len(daily) == 1
    assert daily.iloc[0]["trade_count"] == 0
    assert daily.iloc[0]["uploaded"] == True  # noqa: E712 (numpy bool, explicit compare reads clearer here)
