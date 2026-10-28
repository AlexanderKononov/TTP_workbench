"""Verifier (ticket 11): engine seam per ADR-0006, independent of test_engine.py.

A broker that fills every resting order on the next event it sees is the
harshest fill model: if the engine let an order placed on event k fill on event
k, this broker would show it.
"""

from datetime import UTC, datetime, timedelta

import pandas as pd
import pytest

from ttp.core import (
    BookSnapshot,
    Cancel,
    Fill,
    Kline,
    Market,
    PlaceLimit,
    Side,
    Strategy,
    Timer,
    Trade,
)
from ttp.data.store import BOOK_1S, BOOK_DEPTH, KLINES_1M, TRADES, DatasetStore
from ttp.engine import Engine
from ttp.execution import RecordingBroker
from ttp.feeds import ReplayFeed

# 23:59 UTC: the fixture crosses a UTC date boundary.
T0 = datetime(2026, 10, 27, 23, 59, tzinfo=UTC)
S = timedelta(seconds=1)
ADX = Market("mexc", "ADXUSDT")
BAR = Market("mexc", "BARUSDT")


class ListFeed:
    def __init__(self, events):
        self._events = list(events)

    def events(self):
        yield from self._events


class FillEverythingNextEvent:
    """Fills every resting PlaceLimit in full on the next event it sees."""

    def __init__(self) -> None:
        self.resting: dict[str, tuple[PlaceLimit, datetime]] = {}
        self.fills: list[Fill] = []
        self.log: list[tuple[str, datetime]] = []

    def on_event(self, event) -> None:
        self.log.append(("event", event.time))
        for cid, (order, _) in list(self.resting.items()):
            self.fills.append(
                Fill(order.market, event.time, cid, order.side, order.price, 1.0)
            )
            del self.resting[cid]

    def submit(self, intent, now) -> None:
        self.log.append(("submit", now))
        if isinstance(intent, PlaceLimit):
            self.resting[intent.client_id] = (intent, now)
        elif isinstance(intent, Cancel):
            self.resting.pop(intent.client_id, None)

    def drain_fills(self):
        out, self.fills = self.fills, []
        return out


class Recorder(Strategy):
    """Places one buy per trade; records callback order and fill times."""

    name = "rec"

    def __init__(self, stop_on=None) -> None:
        super().__init__()
        self.calls: list[tuple[str, datetime]] = []
        self.placed: dict[str, datetime] = {}
        self.fill_times: dict[str, datetime] = {}
        self.stop_on = stop_on
        self.engine: Engine | None = None

    def on_start(self):
        self.calls.append(("start", self.now))
        return ()

    def on_trade(self, trade):
        self.calls.append(("trade", self.now))
        assert self.now == trade.time  # the clock is the event's time
        cid = self.next_client_id()
        self.placed[cid] = self.now
        if self.stop_on is not None and trade.time == self.stop_on:
            self.engine.stop()
        return [PlaceLimit(trade.market, cid, Side.BUY, trade.price, 1.0)]

    def on_kline(self, kline):
        self.calls.append(("kline", self.now))
        return ()

    def on_book(self, book):
        self.calls.append(("book", self.now))
        return ()

    def on_timer(self, timer):
        self.calls.append(("timer", self.now))
        return ()

    def on_fill(self, fill):
        self.calls.append(("fill", self.now))
        self.fill_times[fill.client_id] = fill.time
        return ()

    def on_stop(self):
        self.calls.append(("stop", self.now))
        return [Cancel(ADX, cid) for cid in self.placed]


def trades(n, market=ADX, start=T0):
    return [Trade(market, start + i * S, 1.0 + i, 1.0, Side.BUY) for i in range(n)]


def test_intent_emitted_on_event_k_never_fills_on_event_k():
    strategy, broker = Recorder(), FillEverythingNextEvent()
    Engine(strategy, ListFeed(trades(5)), broker).run()
    assert len(strategy.placed) == 5
    # Every order but the last got filled, and strictly later than it was placed.
    assert set(strategy.fill_times) == {f"rec-{i}" for i in range(1, 5)}
    for cid, filled in strategy.fill_times.items():
        assert filled > strategy.placed[cid], cid


def test_fill_is_delivered_before_the_events_own_callback():
    strategy = Recorder()
    Engine(strategy, ListFeed(trades(3)), FillEverythingNextEvent()).run()
    kinds = [k for k, _ in strategy.calls]
    assert kinds == ["start", "trade", "fill", "trade", "fill", "trade", "stop"]


def test_broker_sees_event_before_intents_of_that_event_are_submitted():
    broker = FillEverythingNextEvent()
    Engine(Recorder(), ListFeed(trades(2)), broker).run()
    assert [k for k, _ in broker.log] == [
        "event",
        "submit",
        "event",
        "submit",
        "submit",  # on_stop cancels rec-1
        "submit",  # and rec-2
    ]


def test_stop_from_a_callback_halts_and_on_stop_intents_reach_the_broker():
    strategy = Recorder(stop_on=T0 + S)
    broker = RecordingBroker()
    engine = Engine(strategy, ListFeed(trades(5)), broker)
    strategy.engine = engine
    stats = engine.run()
    assert stats.events == 2
    assert stats.end == T0 + S
    cancels = [r.intent for r in broker.intents if isinstance(r.intent, Cancel)]
    assert [c.client_id for c in cancels] == ["rec-1", "rec-2"]
    assert strategy.calls[-1] == ("stop", T0 + S)  # stamped at the last event


def test_stop_during_on_start_processes_no_event_but_calls_on_stop():
    class StopAtStart(Recorder):
        def on_start(self):
            self.engine.stop()
            return ()

    strategy = StopAtStart()
    engine = Engine(strategy, ListFeed(trades(3)), RecordingBroker())
    strategy.engine = engine
    stats = engine.run()
    assert stats.events == 0
    assert [k for k, _ in strategy.calls] == ["stop"]


def test_empty_feed_still_starts_and_stops():
    strategy = Recorder()
    stats = Engine(strategy, ListFeed([]), RecordingBroker()).run()
    assert (stats.events, stats.start, stats.end) == (0, None, None)
    assert [k for k, _ in strategy.calls] == ["start", "stop"]


# -- replay over a small dataset written through DatasetStore ---------------


def _book_row(time, version, bid, ask, levels=2):
    row = {"time": time, "version": version}
    for i in range(1, BOOK_DEPTH + 1):
        on = i <= levels
        row[f"bid_price_{i}"] = bid - (i - 1) * 0.001 if on else None
        row[f"bid_qty_{i}"] = 10.0 * i if on else None
        row[f"ask_price_{i}"] = ask + (i - 1) * 0.001 if on else None
        row[f"ask_qty_{i}"] = 5.0 * i if on else None
    return row


@pytest.fixture
def mixed(tmp_path) -> DatasetStore:
    """ADX: 2 klines (23:58, 23:59 open), trades and 1 s book around midnight; BAR: klines."""
    store = DatasetStore(tmp_path)
    m = timedelta(minutes=1)
    kl = pd.DataFrame(
        {
            "open_time": [T0 - m, T0],
            "open": [1.0, 1.0],
            "high": [1.1, 1.2],
            "low": [0.9, 0.95],
            "close": [1.0, 1.05],
            "volume": [3.0, 4.0],
            "quote_volume": [3.0, 4.0],
        }
    )
    store.write("mix", "mexc", "ADXUSDT", KLINES_1M, kl)
    store.write("mix", "mexc", "BARUSDT", KLINES_1M, kl)
    tr = pd.DataFrame(
        {
            "time": [
                T0 + 30 * S,
                T0 + 60 * S,
                T0 + 61 * S,
            ],  # 23:59:30, 00:00:00, 00:00:01
            "price": [1.0, 1.01, 1.02],
            "quantity": [2.0, 3.0, 4.0],
            "side": ["buy", "sell", "buy"],
        }
    )
    store.write("mix", "mexc", "ADXUSDT", TRADES, tr)
    book = pd.DataFrame(
        [_book_row(T0 + 59 * S, 7, 0.99, 1.01), _book_row(T0 + 60 * S, 8, 0.98, 1.02)]
    )
    store.append("mix", "mexc", "ADXUSDT", BOOK_1S, book)
    return store


def _key(e):
    kind = type(e).__name__
    market = getattr(e, "market", None)
    return (e.time, kind, market.symbol if market else None)


def test_replay_orders_klines_trades_and_book_by_event_time(mixed):
    events = list(ReplayFeed(mixed, "mix").events())
    times = [e.time for e in events]
    assert times == sorted(times)
    assert len(events) == 2 * 2 + 3 + 2
    midnight = T0 + 60 * S
    # The 23:59 candle closes at midnight: it must not appear before the 23:59:30 trade.
    first_trade = next(i for i, e in enumerate(events) if isinstance(e, Trade))
    kline_0000 = [
        i for i, e in enumerate(events) if isinstance(e, Kline) and e.time == midnight
    ]
    assert all(i > first_trade for i in kline_0000)
    at_midnight = [_key(e) for e in events if e.time == midnight]
    # Same time: by market, then by data type.
    assert at_midnight == [
        (midnight, "BookSnapshot", "ADXUSDT"),
        (midnight, "Kline", "ADXUSDT"),
        (midnight, "Trade", "ADXUSDT"),
        (midnight, "Kline", "BARUSDT"),
    ]
    # Deterministic across runs.
    assert [_key(e) for e in ReplayFeed(mixed, "mix").events()] == [
        _key(e) for e in events
    ]


def test_replay_book_rows_round_trip_with_null_levels_dropped(mixed):
    books = [e for e in ReplayFeed(mixed, "mix", data_types={"book_1s"}).events()]
    assert [b.time for b in books] == [T0 + 59 * S, T0 + 60 * S]
    b = books[0]
    assert isinstance(b, BookSnapshot) and b.market == ADX
    assert [lv.price for lv in b.bids] == pytest.approx([0.99, 0.989])
    assert [lv.price for lv in b.asks] == pytest.approx([1.01, 1.011])
    assert b.best_bid.price < b.best_ask.price


def test_replay_window_is_on_event_time_across_types(mixed):
    midnight = T0 + 60 * S
    events = list(ReplayFeed(mixed, "mix", start=midnight, end=midnight + S).events())
    assert {e.time for e in events} == {midnight}
    assert len(events) == 4  # book, ADX kline, trade, BAR kline


def test_engine_over_replay_sees_no_kline_before_it_closes(mixed):
    class Watch(Strategy):
        def __init__(self):
            super().__init__()
            self.bad = []
            self.seen = 0

        def on_kline(self, k):
            self.seen += 1
            if self.now < k.open_time + timedelta(minutes=1):
                self.bad.append(k)
            return ()

    w = Watch()
    stats = Engine(w, ReplayFeed(mixed, "mix"), RecordingBroker()).run()
    assert w.seen == 4 and w.bad == []
    assert stats.events == 9
    assert stats.start == T0 and stats.end == T0 + 61 * S


def test_timers_fill_quiet_stretches_and_precede_data_at_the_same_time(mixed):
    feed = ReplayFeed(mixed, "mix", data_types={"trades"}, timer_interval=10 * S)
    events = list(feed.events())
    timers = [e.time for e in events if isinstance(e, Timer)]
    # Ticks from the first event (23:59:30) every 10 s up to the last event.
    first = T0 + 30 * S
    assert timers == [first + i * 10 * S for i in range(4)]  # :30 :40 :50 00:00
    kinds = [type(e).__name__ for e in events]
    assert kinds[:2] == ["Timer", "Trade"]
    midnight = [type(e).__name__ for e in events if e.time == T0 + 60 * S]
    assert midnight == ["Timer", "Trade"]


def test_strategy_receives_timers_with_the_clock_at_tick_time(mixed):
    strategy = Recorder()
    feed = ReplayFeed(mixed, "mix", data_types={"trades"}, timer_interval=10 * S)
    Engine(strategy, feed, RecordingBroker()).run()
    timer_calls = [t for k, t in strategy.calls if k == "timer"]
    assert timer_calls == [T0 + (30 + 10 * i) * S for i in range(4)]
