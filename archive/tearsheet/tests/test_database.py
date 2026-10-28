"""src.database tests against a fake Supabase client (no network calls).

The fake (tests/_fakes.py, wired in via the autouse fixture in
tests/conftest.py) reimplements just enough of the chainable postgrest-py
query builder to exercise src.database's real logic - in particular the
trade_hash dedup path that makes cumulative, multi-upload statistics correct
(SUPABASE_PLAN.md §3).
"""
from __future__ import annotations

import pandas as pd
import pytest

from src import database
from src.statistics import compute_stats


def _trades(rows: list[tuple]) -> pd.DataFrame:
    """rows: (trade_time, symbol, direction, profit, fee) tuples."""
    df = pd.DataFrame(rows, columns=["trade_time", "symbol", "direction", "profit", "fee"])
    df["trade_time"] = pd.to_datetime(df["trade_time"])
    df["market"] = "X"
    df["profit_pct"] = pd.NA
    df["net_pnl"] = df["profit"] - df["fee"]
    return df[["trade_time", "market", "symbol", "direction", "profit", "profit_pct", "fee", "net_pnl"]]


def test_ensure_participant_creates_once_and_reuses(fake_supabase):
    first = database.ensure_participant("Alx")
    second = database.ensure_participant("Alx")
    assert first == second
    assert len(fake_supabase.tables["participants"]) == 1


def test_save_upload_inserts_trades(fake_supabase):
    trades = _trades(
        [
            ("2026-08-01 10:00", "AAA", "sell", 10.0, 1.0),
            ("2026-08-01 11:00", "BBB", "buy", -4.0, 1.0),
        ]
    )
    result = database.save_upload("Alx", "day1.csv", "B", trades)

    assert result["trade_count"] == 2
    assert result["inserted_count"] == 2
    assert result["duplicate_count"] == 0
    assert len(fake_supabase.tables["trades"]) == 2


def test_save_upload_deduplicates_overlapping_trades(fake_supabase):
    trades_day1 = _trades(
        [
            ("2026-08-01 10:00", "AAA", "sell", 10.0, 1.0),
            ("2026-08-01 11:00", "BBB", "buy", -4.0, 1.0),
        ]
    )
    database.save_upload("Alx", "day1.csv", "B", trades_day1)

    # day2's export re-includes the last trade from day1, plus one new trade.
    trades_day2 = _trades(
        [
            ("2026-08-01 11:00", "BBB", "buy", -4.0, 1.0),
            ("2026-08-02 09:00", "CCC", "sell", 6.0, 1.0),
        ]
    )
    result = database.save_upload("Alx", "day2.csv", "B", trades_day2)

    assert result["inserted_count"] == 1
    assert result["duplicate_count"] == 1
    assert len(fake_supabase.tables["trades"]) == 3


def test_get_all_trades_combines_uploads_for_cumulative_stats(fake_supabase):
    database.save_upload(
        "Alx", "day1.csv", "B", _trades([("2026-08-01 10:00", "AAA", "sell", 10.0, 1.0)])
    )
    database.save_upload(
        "Alx", "day2.csv", "B", _trades([("2026-08-02 10:00", "BBB", "buy", -6.0, 1.0)])
    )

    all_trades = database.get_all_trades("Alx")
    assert len(all_trades) == 2
    assert list(all_trades["trade_time"]) == sorted(all_trades["trade_time"])

    stats = compute_stats(all_trades)
    assert stats["trade_count"] == 2
    assert stats["net_pnl"] == pytest.approx((10.0 - 1.0) + (-6.0 - 1.0))


def test_get_all_trades_scoped_per_participant(fake_supabase):
    database.save_upload("Alx", "a.csv", "B", _trades([("2026-08-01 10:00", "AAA", "sell", 10.0, 1.0)]))
    database.save_upload("Ars", "b.csv", "B", _trades([("2026-08-01 10:00", "AAA", "sell", 5.0, 1.0)]))

    assert len(database.get_all_trades("Alx")) == 1
    assert len(database.get_all_trades("Ars")) == 1


def test_list_sessions_shape_matches_report_expectations(fake_supabase):
    database.save_upload(
        "Alx", "day1.csv", "B", _trades([("2026-08-01 10:00", "AAA", "sell", 10.0, 1.0)])
    )

    sessions = database.list_sessions("Alx")
    assert len(sessions) == 1
    session = sessions[0]
    assert session["file_name"] == "day1.csv"
    assert session["participant"] == "Alx"
    assert session["stats"]["trade_count"] == 1
    assert not session["trades"].empty


def test_list_participants(fake_supabase):
    database.save_upload("Alx", "a.csv", "B", _trades([("2026-08-01 10:00", "AAA", "sell", 10.0, 1.0)]))
    database.save_upload("Ars", "b.csv", "B", _trades([("2026-08-01 10:00", "AAA", "sell", 5.0, 1.0)]))

    assert database.list_participants() == ["Alx", "Ars"]
