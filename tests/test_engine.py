"""Engine seam: a toy strategy on fixture klines produces the expected intents."""

import ast
from datetime import UTC, datetime, timedelta
from pathlib import Path

import pandas as pd
import pytest

from ttp.core import (
    Cancel,
    Fill,
    Kline,
    Market,
    PlaceLimit,
    Side,
    SimulatedClock,
    Strategy,
)
from ttp.data.store import KLINES_1M, DatasetStore
from ttp.engine import Broker, Engine, Feed
from ttp.execution import RecordingBroker
from ttp.feeds import ReplayFeed

T0 = datetime(2026, 10, 27, 23, 58, tzinfo=UTC)  # crosses a UTC date boundary
MIN = timedelta(minutes=1)
ADX = Market("mexc", "ADXUSDT")


def klines_frame(start: datetime, lows: list[float]) -> pd.DataFrame:
    """Flat candles at 1.0 except `low`, one per minute from `start`."""
    return pd.DataFrame(
        {
            "open_time": [start + i * MIN for i in range(len(lows))],
            "open": 1.0,
            "high": 1.0,
            "low": lows,
            "close": 1.0,
            "volume": 10.0,
            "quote_volume": 10.0,
        }
    )


@pytest.fixture
def store(tmp_path) -> DatasetStore:
    return DatasetStore(tmp_path)


class Requoter(Strategy):
    """Toy: on every kline, requote a resting buy at the candle's low (cancel + place)."""

    name = "requoter"

    def __init__(self) -> None:
        super().__init__()
        self.resting: str | None = None
        self.started = self.stopped = False
        self.seen: list[Kline] = []

    def on_start(self):
        self.started = True
        return ()

    def on_kline(self, kline):
        self.seen.append(kline)
        intents = []
        if self.resting:
            intents.append(Cancel(kline.market, self.resting))
        self.resting = self.next_client_id()
        intents.append(PlaceLimit(kline.market, self.resting, Side.BUY, kline.low, 10))
        return intents

    def on_fill(self, fill):
        self.resting = None
        return [
            PlaceLimit(
                fill.market,
                self.next_client_id(),
                Side.SELL,
                round(fill.price * 1.02, 6),
                fill.quantity,
            )
        ]

    def on_stop(self):
        self.stopped = True
        return [Cancel(ADX, self.resting)] if self.resting else ()


def test_toy_strategy_on_fixture_klines_emits_expected_intents(store):
    store.write(
        "fx", "mexc", "ADXUSDT", KLINES_1M, klines_frame(T0, [0.98, 0.97, 0.99])
    )
    strategy, broker = Requoter(), RecordingBroker()
    stats = Engine(strategy, ReplayFeed(store, "fx"), broker).run()

    assert strategy.started and strategy.stopped
    assert [k.time for k in strategy.seen] == [T0 + MIN, T0 + 2 * MIN, T0 + 3 * MIN]
    assert strategy.now == T0 + 3 * MIN  # clock stays at the last event
    assert [(r.time, r.intent) for r in broker.intents] == [
        (T0 + MIN, PlaceLimit(ADX, "requoter-1", Side.BUY, 0.98, 10)),
        (T0 + 2 * MIN, Cancel(ADX, "requoter-1")),
        (T0 + 2 * MIN, PlaceLimit(ADX, "requoter-2", Side.BUY, 0.97, 10)),
        (T0 + 3 * MIN, Cancel(ADX, "requoter-2")),
        (T0 + 3 * MIN, PlaceLimit(ADX, "requoter-3", Side.BUY, 0.99, 10)),
        (T0 + 3 * MIN, Cancel(ADX, "requoter-3")),  # on_stop, at the last event time
    ]
    assert stats.events == 3 and stats.intents == 6 and stats.fills == 0
    assert (stats.start, stats.end) == (T0 + MIN, T0 + 3 * MIN)
    assert broker.events_seen == 3


class TouchBroker(RecordingBroker):
    """Test broker: fills a resting buy at its price when a later kline trades below it."""

    def __init__(self) -> None:
        super().__init__()
        self.resting: dict[str, PlaceLimit] = {}
        self.filled: list[Fill] = []
        self._fills: list[Fill] = []

    def on_event(self, event):
        super().on_event(event)
        if not isinstance(event, Kline):
            return
        for order in list(self.resting.values()):
            if order.side is Side.BUY and event.low <= order.price:
                del self.resting[order.client_id]
                fill = Fill(
                    order.market,
                    event.time,
                    order.client_id,
                    order.side,
                    order.price,
                    order.quantity,
                    fee=0.0,
                )
                self.filled.append(fill)
                self._fills.append(fill)

    def submit(self, intent, now):
        super().submit(intent, now)
        if isinstance(intent, PlaceLimit):
            self.resting[intent.client_id] = intent
        else:
            self.resting.pop(intent.client_id, None)

    def drain_fills(self):
        fills, self._fills = self._fills, []
        return fills


def test_broker_sees_event_before_strategy_so_no_look_ahead(store):
    # Candle 1 (low 0.98): the strategy rests a buy at 0.98. That candle touched
    # 0.98, but the order did not exist when the broker saw it: no fill.
    # Candle 2 (low 0.99): no touch; requote to 0.99.
    # Candle 3 (low 0.98): touches 0.99 -> fill, delivered before on_kline, so the
    # sell is posted before the next requote.
    store.write(
        "fx", "mexc", "ADXUSDT", KLINES_1M, klines_frame(T0, [0.98, 0.99, 0.98])
    )
    strategy, broker = Requoter(), TouchBroker()
    stats = Engine(strategy, ReplayFeed(store, "fx"), broker).run()

    assert [(f.time, f.client_id, f.price) for f in broker.filled] == [
        (T0 + 3 * MIN, "requoter-2", 0.99)
    ]
    assert [(r.time, r.intent) for r in broker.intents] == [
        (T0 + MIN, PlaceLimit(ADX, "requoter-1", Side.BUY, 0.98, 10)),
        (T0 + 2 * MIN, Cancel(ADX, "requoter-1")),
        (T0 + 2 * MIN, PlaceLimit(ADX, "requoter-2", Side.BUY, 0.99, 10)),
        (T0 + 3 * MIN, PlaceLimit(ADX, "requoter-3", Side.SELL, 1.0098, 10)),
        (T0 + 3 * MIN, PlaceLimit(ADX, "requoter-4", Side.BUY, 0.98, 10)),
        (T0 + 3 * MIN, Cancel(ADX, "requoter-4")),
    ]
    assert stats.fills == 1


def test_on_start_intents_use_the_clock_start_time():
    class Eager(Strategy):
        def on_start(self):
            return [PlaceLimit(ADX, self.next_client_id(), Side.BUY, 1.0, 1)]

    class EmptyFeed:
        def events(self):
            return iter(())

    broker = RecordingBroker()
    stats = Engine(Eager(), EmptyFeed(), broker, SimulatedClock(T0)).run()
    assert [(r.time, r.intent.client_id) for r in broker.intents] == [
        (T0, "strategy-1")
    ]
    assert (stats.events, stats.start, stats.end) == (0, None, None)


def test_stop_halts_after_current_event_and_still_calls_on_stop(store):
    store.write("fx", "mexc", "ADXUSDT", KLINES_1M, klines_frame(T0, [1.0] * 5))
    strategy = Requoter()
    engine = Engine(strategy, ReplayFeed(store, "fx"), RecordingBroker())
    original = strategy.on_kline

    def stop_after_second(kline):
        if len(strategy.seen) == 1:
            engine.stop()
        return original(kline)

    strategy.on_kline = stop_after_second
    stats = engine.run()
    assert stats.events == 2
    assert strategy.stopped


def test_strategy_now_requires_binding():
    with pytest.raises(RuntimeError):
        _ = Strategy().now


def test_replay_feed_and_recording_broker_satisfy_engine_ports(store):
    assert isinstance(ReplayFeed(store, "fx"), Feed)
    assert isinstance(RecordingBroker(), Broker)


def test_clock_never_moves_backwards_and_requires_utc():
    clock = SimulatedClock(T0)
    clock.advance_to(T0 + MIN)
    clock.advance_to(T0)
    assert clock.now() == T0 + MIN
    with pytest.raises(ValueError):
        clock.advance_to(datetime(2026, 1, 1))


def test_strategies_import_only_core():
    """Architecture rule: `strategies` depends on `core` and nothing else in `ttp`."""
    root = Path(__file__).parent.parent / "src" / "ttp" / "strategies"
    offenders = []
    for path in root.rglob("*.py"):
        tree = ast.parse(path.read_text(encoding="utf-8"))
        for node in ast.walk(tree):
            names = []
            if isinstance(node, ast.Import):
                names = [a.name for a in node.names]
            elif isinstance(node, ast.ImportFrom) and node.module:
                names = [node.module]
            for name in names:
                if name.startswith("ttp") and not name.startswith("ttp.core"):
                    offenders.append(f"{path.relative_to(root)}: {name}")
    assert offenders == []
