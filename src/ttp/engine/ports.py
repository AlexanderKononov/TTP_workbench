"""What the engine needs from a feed and a broker; stages differ only in these.

Both are structural (`Protocol`), so `feeds/` and `execution/` implement them
without importing the engine.

- Backtest: `ReplayFeed` + simulated broker (M3; `RecordingBroker` until then).
- Paper: live feed + paper broker (M4).
- Live: live feed + execution service (M5).
"""

from collections.abc import Iterator
from datetime import datetime
from typing import Protocol, runtime_checkable

from ttp.core import Fill, MarketEvent, OrderIntent


@runtime_checkable
class Feed(Protocol):
    def events(self) -> Iterator[MarketEvent]:
        """Market events in non-decreasing `time` order; ends when the feed ends.

        A live feed blocks between events and ends when told to stop.
        """
        ...


@runtime_checkable
class Broker(Protocol):
    def on_event(self, event: MarketEvent) -> None:
        """See each market event before the strategy does, to simulate fills."""
        ...

    def submit(self, intent: OrderIntent, now: datetime) -> None:
        """Accept (or reject) an intent emitted at engine time `now`."""
        ...

    def drain_fills(self) -> list[Fill]:
        """Fills produced since the last drain, in time order."""
        ...
