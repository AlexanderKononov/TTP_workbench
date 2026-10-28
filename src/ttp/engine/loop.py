"""The engine: one strategy, one feed, one broker, the same loop in every stage."""

from dataclasses import dataclass
from datetime import datetime

from ttp.core import (
    BookSnapshot,
    Fill,
    Intents,
    Kline,
    MarketEvent,
    SimulatedClock,
    Strategy,
    Timer,
    Trade,
)
from ttp.engine.ports import Broker, Feed


@dataclass(frozen=True)
class RunStats:
    events: int
    fills: int
    intents: int
    start: datetime | None  # time of the first event, None if the feed was empty
    end: datetime | None  # time of the last event


class Engine:
    def __init__(
        self,
        strategy: Strategy,
        feed: Feed,
        broker: Broker,
        clock: SimulatedClock | None = None,
    ) -> None:
        self.strategy = strategy
        self.feed = feed
        self.broker = broker
        self.clock = clock or SimulatedClock()
        self._stopping = False
        self._events = self._fills = self._intents = 0

    def stop(self) -> None:
        """Stop after the current event. Never needs confirmation (ADR-0002)."""
        self._stopping = True

    def run(self) -> RunStats:
        strategy = self.strategy
        strategy.bind(self.clock)
        self._submit(strategy.on_start())
        start = end = None
        for event in self.feed.events():
            if self._stopping:
                break
            self.clock.advance_to(event.time)
            start = start or event.time
            end = event.time
            self._events += 1
            self.broker.on_event(event)
            for fill in self.broker.drain_fills():
                self._deliver_fill(fill)
            self._submit(self._dispatch(event))
        self._submit(strategy.on_stop())
        return RunStats(self._events, self._fills, self._intents, start, end)

    def _dispatch(self, event: MarketEvent) -> Intents:
        strategy = self.strategy
        match event:
            case Kline():
                return strategy.on_kline(event)
            case Trade():
                return strategy.on_trade(event)
            case BookSnapshot():
                return strategy.on_book(event)
            case Timer():
                return strategy.on_timer(event)
        raise TypeError(f"unknown market event: {event!r}")

    def _deliver_fill(self, fill: Fill) -> None:
        self._fills += 1
        self._submit(self.strategy.on_fill(fill))

    def _submit(self, intents: Intents) -> None:
        now = self.clock.now()
        for intent in intents:
            self._intents += 1
            self.broker.submit(intent, now)
