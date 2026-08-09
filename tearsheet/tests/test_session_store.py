import pandas as pd
import pytest

from src import session_store


@pytest.fixture(autouse=True)
def clear_store():
    """session_store uses a process-wide cache; reset it between tests."""
    session_store._store().clear()
    yield
    session_store._store().clear()


def _trades(symbol="AAA"):
    df = pd.DataFrame(
        {
            "trade_time": pd.to_datetime(["2026-01-01 10:00"]),
            "market": ["X"],
            "symbol": [symbol],
            "direction": ["sell"],
            "profit": [5.0],
            "profit_pct": [1.0],
            "fee": [1.0],
        }
    )
    df["net_pnl"] = df["profit"] - df["fee"]
    return df


def test_add_and_list_sessions_scoped_by_participant():
    session_store.add_session("alexander", "a.csv", _trades(), {"trade_count": 1})
    session_store.add_session("friend", "b.csv", _trades(), {"trade_count": 1})

    assert len(session_store.list_sessions("alexander")) == 1
    assert len(session_store.list_sessions("friend")) == 1
    assert len(session_store.list_sessions()) == 2


def test_get_session_by_id():
    sid = session_store.add_session("alexander", "a.csv", _trades(), {"trade_count": 1})
    found = session_store.get_session(sid)
    assert found["file_name"] == "a.csv"
    assert session_store.get_session("does-not-exist") is None


def test_list_participants():
    session_store.add_session("alexander", "a.csv", _trades(), {"trade_count": 1})
    session_store.add_session("friend", "b.csv", _trades(), {"trade_count": 1})
    assert session_store.list_participants() == ["alexander", "friend"]
