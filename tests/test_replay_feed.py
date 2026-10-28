"""Replay feed: dataset series become one time-ordered event stream."""

from datetime import UTC, datetime, timedelta

import pandas as pd
import pytest

from ttp.core import Kline, Market, Timer
from ttp.data.store import KLINES_1M, DatasetStore
from ttp.feeds import ReplayFeed

T0 = datetime(2026, 10, 27, 23, 58, tzinfo=UTC)
MIN = timedelta(minutes=1)


def klines_frame(start: datetime, closes: list[float]) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "open_time": [start + i * MIN for i in range(len(closes))],
            "open": closes,
            "high": [c + 0.01 for c in closes],
            "low": [c - 0.01 for c in closes],
            "close": closes,
            "volume": 5.0,
            "quote_volume": 5.0,
        }
    )


@pytest.fixture
def store(tmp_path) -> DatasetStore:
    s = DatasetStore(tmp_path)
    s.write("fx", "mexc", "ADXUSDT", KLINES_1M, klines_frame(T0, [1.0, 1.1, 1.2, 1.3]))
    s.write("fx", "mexc", "ZZZUSDT", KLINES_1M, klines_frame(T0 + MIN, [2.0, 2.1]))
    return s


def test_klines_replay_as_events_stamped_at_close_time(store):
    events = list(ReplayFeed(store, "fx", markets={"ADXUSDT"}).events())
    assert all(isinstance(e, Kline) for e in events)
    first = events[0]
    assert first.market == Market("mexc", "ADXUSDT")
    assert (first.open_time, first.time) == (T0, T0 + MIN)
    assert first.time.tzinfo is not None
    assert (first.open, first.high, first.low, first.close) == (1.0, 1.01, 0.99, 1.0)
    assert (first.volume, first.quote_volume) == (5.0, 5.0)
    assert [e.close for e in events] == [1.0, 1.1, 1.2, 1.3]


def test_markets_merge_in_time_order_then_by_market_name(store):
    events = list(ReplayFeed(store, "fx").events())
    assert [(e.time, e.market.symbol) for e in events] == [
        (T0 + 1 * MIN, "ADXUSDT"),
        (T0 + 2 * MIN, "ADXUSDT"),
        (T0 + 2 * MIN, "ZZZUSDT"),
        (T0 + 3 * MIN, "ADXUSDT"),
        (T0 + 3 * MIN, "ZZZUSDT"),
        (T0 + 4 * MIN, "ADXUSDT"),
    ]


def test_window_applies_to_event_time_end_exclusive(store):
    feed = ReplayFeed(store, "fx", start=T0 + 2 * MIN, end=T0 + 4 * MIN)
    events = list(feed.events())
    assert [(e.time, e.market.symbol) for e in events] == [
        (T0 + 2 * MIN, "ADXUSDT"),
        (T0 + 2 * MIN, "ZZZUSDT"),
        (T0 + 3 * MIN, "ADXUSDT"),
        (T0 + 3 * MIN, "ZZZUSDT"),
    ]
    # The candle opening at T0+1 closes at T0+2 and so is the first one in.
    assert events[0].open_time == T0 + MIN


def test_data_type_filter_and_unknown_dataset(store):
    assert list(ReplayFeed(store, "fx", data_types={"trades"}).events()) == []
    assert list(ReplayFeed(store, "none", data_types={"klines_1m"}).events()) == []


def test_timers_tick_from_first_event_and_precede_data_at_same_time(store):
    feed = ReplayFeed(store, "fx", markets={"ADXUSDT"}, timer_interval=2 * MIN)
    events = list(feed.events())
    assert [(type(e).__name__, e.time) for e in events] == [
        ("Timer", T0 + 1 * MIN),
        ("Kline", T0 + 1 * MIN),
        ("Kline", T0 + 2 * MIN),
        ("Timer", T0 + 3 * MIN),
        ("Kline", T0 + 3 * MIN),
        ("Kline", T0 + 4 * MIN),
    ]
    assert isinstance(events[0], Timer)


def test_events_are_a_fresh_iterator_each_call(store):
    feed = ReplayFeed(store, "fx")
    assert len(list(feed.events())) == len(list(feed.events())) == 6
