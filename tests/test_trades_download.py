"""MEXC aggregate trades: hour-window paging, the `trades` data type and its replay."""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pandas as pd
import pytest

from ttp.core import Kline, Side, Trade
from ttp.data.downloader import download_trades
from ttp.data.store import KLINES_1M, TRADES, DatasetStore
from ttp.feeds import ReplayFeed
from ttp.venues.mexc import MexcClient
from ttp.venues.mexc.client import parse_agg_trades

FIXTURES = Path(__file__).parent / "fixtures" / "mexc"
S_MS = 1_000
H_MS = 3_600_000
T0 = datetime(2026, 10, 27, 23, 0, tzinfo=UTC)
T0_MS = int(T0.timestamp() * 1000)


def print_(t_ms: int, price: float = 1.0, qty: float = 10.0, maker=True) -> dict:
    return {
        "a": None,
        "f": None,
        "l": None,
        "p": str(price),
        "q": str(qty),
        "T": t_ms,
        "m": maker,
        "M": True,
    }


class FakeAggTradesServer:
    """Serves `/api/v3/aggTrades` like MEXC (probed 2026-10-28): startTime and
    endTime required together, at most 1 h apart, both inclusive; newest first;
    at most 1000 rows."""

    def __init__(self, rows: list[dict]) -> None:
        self.rows = sorted(rows, key=lambda r: r["T"], reverse=True)
        self.requests: list[dict] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v3/aggTrades"
        q = dict(request.url.params)
        self.requests.append(q)
        if ("startTime" in q) != ("endTime" in q):
            return httpx.Response(
                400,
                json={
                    "msg": "Combination of optional parameters invalid.",
                    "code": -1128,
                },
            )
        start, end = int(q["startTime"]), int(q["endTime"])
        if end - start > H_MS:
            return httpx.Response(
                400,
                json={
                    "msg": "More than 1 hours between startTime and endTime.",
                    "code": -1127,
                },
            )
        limit = min(int(q.get("limit", 500)), 1000)
        page = [r for r in self.rows if start <= r["T"] <= end][:limit]
        return httpx.Response(200, json=page)


def client(server) -> MexcClient:
    return MexcClient(transport=httpx.MockTransport(server))


def test_agg_trades_fixture_parses_mexc_rows():
    payload = json.loads((FIXTURES / "agg_trades_adxusdt.json").read_text())
    trades = parse_agg_trades(payload)
    assert len(trades) == 12
    assert trades[0].time_ms == 1793177285000
    assert (trades[0].price, trades[0].quantity, trades[0].buyer_is_maker) == (
        0.0575,
        520.25,
        True,
    )
    assert trades[7].buyer_is_maker is False


def test_agg_trades_walk_hour_windows_oldest_first_end_exclusive():
    rows = [print_(T0_MS + i * 600 * S_MS, price=1 + i / 100) for i in range(20)]
    server = FakeAggTradesServer(rows)
    # [T0 + 5 min, T0 + 2 h 35 min): prints at 10, 20, ... 150 min.
    trades = client(server).agg_trades(
        "ADXUSDT", T0_MS + 300 * S_MS, T0_MS + 9300 * S_MS
    )
    assert [t.time_ms for t in trades] == [T0_MS + i * 600 * S_MS for i in range(1, 16)]
    assert len(server.requests) == 3  # three windows of at most 1 h
    assert all(int(q["endTime"]) - int(q["startTime"]) <= H_MS for q in server.requests)


def test_agg_trades_page_a_full_window_without_losing_a_split_second():
    # 2,300 prints over 25 s, 92 per second: the first page of 1,000 cuts a
    # second in two, so that second must be re-read whole.
    rows = [
        print_(T0_MS + s * S_MS, price=1 + s / 100, qty=i)
        for s in range(25)
        for i in range(92)
    ]
    server = FakeAggTradesServer(rows)
    trades = client(server).agg_trades("ADXUSDT", T0_MS, T0_MS + H_MS)
    assert len(trades) == len(rows)
    assert [t.time_ms for t in trades] == sorted(t.time_ms for t in trades)
    assert len({(t.time_ms, t.quantity) for t in trades}) == len(rows)
    assert len(server.requests) == 3


def test_download_trades_extends_from_last_print_and_never_duplicates(tmp_path):
    store = DatasetStore(tmp_path)
    rows = [print_(T0_MS + i * 60 * S_MS, price=1 + i / 100) for i in range(120)]
    first = FakeAggTradesServer(rows[:60])
    r1 = download_trades(
        client(first), store, "t", "ADXUSDT", T0, T0 + timedelta(hours=3)
    )
    assert (r1.fetched, r1.added) == (60, 60)

    second = FakeAggTradesServer(rows)
    r2 = download_trades(
        client(second), store, "t", "ADXUSDT", T0, T0 + timedelta(hours=3)
    )
    # Asked from the last stored print on: that print comes back and is deduplicated.
    assert int(second.requests[0]["startTime"]) == rows[59]["T"]
    assert (r2.fetched, r2.added) == (61, 60)

    df = store.read("t", "mexc", "ADXUSDT", TRADES)
    assert list(df.columns) == ["time", "price", "quantity", "side"]
    assert len(df) == 120
    assert df["time"].is_monotonic_increasing
    assert df["side"].unique().tolist() == ["sell"]  # buyer was maker
    assert df["time"].iloc[0] == T0 and df["time"].dt.tz is not None
    parts = sorted(p.parent.name for p in tmp_path.rglob("*.parquet"))
    assert parts == ["date=2026-10-27", "date=2026-10-28"]


def test_identical_prints_in_one_second_are_distinct_unless_same_size(tmp_path):
    store = DatasetStore(tmp_path)
    rows = [print_(T0_MS, qty=5), print_(T0_MS, qty=7), print_(T0_MS, qty=7)]
    download_trades(
        client(FakeAggTradesServer(rows)), store, "t", "X", T0, T0 + timedelta(hours=1)
    )
    assert sorted(store.read("t", "mexc", "X", TRADES)["quantity"]) == [5.0, 7.0]


def test_trades_replay_as_events_merged_with_klines(tmp_path):
    store = DatasetStore(tmp_path)
    candles = pd.DataFrame(
        {
            "open_time": [T0 + timedelta(minutes=i) for i in range(3)],
            "open": 1.0,
            "high": 1.0,
            "low": 1.0,
            "close": 1.0,
            "volume": 0.0,
            "quote_volume": 0.0,
        }
    )
    store.write("t", "mexc", "X", KLINES_1M, candles)
    prints = [
        print_(T0_MS + 30 * S_MS, price=1.5, qty=2, maker=False),
        print_(T0_MS + 60 * S_MS, price=1.4, qty=3, maker=True),
    ]
    download_trades(
        client(FakeAggTradesServer(prints)),
        store,
        "t",
        "X",
        T0,
        T0 + timedelta(minutes=3),
    )
    events = list(ReplayFeed(store, "t").events())
    assert [(type(e).__name__, e.time) for e in events] == [
        ("Trade", T0 + timedelta(seconds=30)),
        ("Kline", T0 + timedelta(minutes=1)),  # the first candle closes at 1 min
        ("Trade", T0 + timedelta(minutes=1)),
        ("Kline", T0 + timedelta(minutes=2)),
        ("Kline", T0 + timedelta(minutes=3)),
    ]
    buy = events[0]
    assert isinstance(buy, Trade) and isinstance(events[1], Kline)
    assert (buy.market.symbol, buy.price, buy.quantity, buy.side) == (
        "X",
        1.5,
        2.0,
        Side.BUY,
    )
    assert events[2].side == Side.SELL
    only_trades = ReplayFeed(store, "t", data_types={TRADES.name}).events()
    assert all(isinstance(e, Trade) for e in only_trades)
    assert KLINES_1M.name != TRADES.name


@pytest.mark.live
def test_live_agg_trades_last_hour():
    now = int(datetime.now(UTC).timestamp() * 1000) // S_MS * S_MS
    with MexcClient() as c:
        trades = c.agg_trades("BTCUSDT", now - H_MS, now)
    assert len(trades) > 1000  # BTC prints more than a page per hour, so paging ran
    assert [t.time_ms for t in trades] == sorted(t.time_ms for t in trades)
