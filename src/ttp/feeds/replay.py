"""Replay feed: a dataset's stored series as a single time-ordered event stream.

Every series in the dataset (each venue / market / data type) is read through
`DatasetStore`, turned into events by the `ReplaySource` registered for its data
type in `SOURCES`, and merged by event `time`. Adding a data type (trades, 1 s
book snapshots) means adding a `DataType` to the store and a source here.

Ordering is deterministic: by `time`, then timers before data events, then by
market, then by data type. Kline events are stamped with their close time (open
time + interval), so a strategy sees a candle only once it has closed.

Each series is loaded in full before replay. That is fine for weeks of 1 m
klines; trades and 1 s snapshots may need per-day chunking later.
"""

import heapq
from collections.abc import Callable, Iterator
from dataclasses import dataclass
from datetime import datetime, timedelta

import pandas as pd

from ttp.core import Kline, Market, MarketEvent, Timer
from ttp.data.store import KLINES_1M, DatasetStore, Series


@dataclass(frozen=True)
class ReplaySource:
    build: Callable[[Market, pd.DataFrame], Iterator[MarketEvent]]
    delay: timedelta  # event.time minus the stored time column


def _klines(market: Market, rows: pd.DataFrame) -> Iterator[Kline]:
    step = pd.Timedelta(KLINES_1M.interval)
    for r in rows.itertuples(index=False):
        yield Kline(
            market=market,
            time=(r.open_time + step).to_pydatetime(),
            open_time=r.open_time.to_pydatetime(),
            open=r.open,
            high=r.high,
            low=r.low,
            close=r.close,
            volume=r.volume,
            quote_volume=r.quote_volume,
        )


SOURCES: dict[str, ReplaySource] = {
    KLINES_1M.name: ReplaySource(_klines, delay=KLINES_1M.interval),
}


class ReplayFeed:
    def __init__(
        self,
        store: DatasetStore,
        dataset: str,
        start: datetime | None = None,
        end: datetime | None = None,
        markets: set[str] | None = None,
        data_types: set[str] | None = None,
        timer_interval: timedelta | None = None,
    ) -> None:
        """Replay `dataset` events with start <= time < end.

        `markets` and `data_types` restrict which series replay (names as stored,
        e.g. `{"ADXUSDT"}`, `{"klines_1m"}`); None means all. With
        `timer_interval`, `Timer` events tick from the first event's time.
        """
        self.store = store
        self.dataset = dataset
        self.start = start
        self.end = end
        self.markets = markets
        self.data_types = data_types
        self.timer_interval = timer_interval

    def series(self) -> list[Series]:
        return [
            s
            for s in self.store.series(self.dataset)
            if (self.markets is None or s.market in self.markets)
            and (self.data_types is None or s.data_type.name in self.data_types)
            and s.data_type.name in SOURCES
        ]

    def events(self) -> Iterator[MarketEvent]:
        streams = [self._stream(s, rank) for rank, s in enumerate(self.series())]
        merged = (event for _, event in heapq.merge(*streams, key=lambda i: i[0]))
        if self.timer_interval is None:
            yield from merged
        else:
            yield from self._with_timers(merged)

    def _stream(self, s: Series, rank: int) -> Iterator[tuple[tuple, MarketEvent]]:
        source = SOURCES[s.data_type.name]
        lo = self.start - source.delay if self.start is not None else None
        hi = self.end - source.delay if self.end is not None else None
        rows = self.store.read(self.dataset, s.venue, s.market, s.data_type, lo, hi)
        for event in source.build(Market(s.venue, s.market), rows):
            yield (event.time, 1, s.market, rank), event

    def _with_timers(self, events: Iterator[MarketEvent]) -> Iterator[MarketEvent]:
        next_tick: datetime | None = None
        for event in events:
            if next_tick is None:
                next_tick = event.time
            while next_tick <= event.time:
                yield Timer(time=next_tick)
                next_tick += self.timer_interval
            yield event
