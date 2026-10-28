"""The strategy base class (ADR-0006): one event-driven class for every stage.

Subclass it, override the `on_*` callbacks you need, and return the order
intents you want sent. A strategy never calls a venue and imports only
`ttp.core`; the engine swaps the feed and broker around it per stage.

Callback order, guaranteed by the engine for each market event:

1. the broker sees the event (it may produce fills for orders already resting);
2. `on_fill` for each fill, in order;
3. the event's own callback (`on_trade`, `on_book`, `on_kline`, `on_timer`).

So an order placed in reaction to an event can only be filled by later events.
"""

from collections.abc import Iterable
from itertools import count

from ttp.core.clock import Clock
from ttp.core.events import BookSnapshot, Fill, Kline, Timer, Trade
from ttp.core.intents import OrderIntent

Intents = Iterable[OrderIntent]


class Strategy:
    name: str = "strategy"

    def __init__(self) -> None:
        self._clock: Clock | None = None
        self._ids = count(1)

    # -- wiring (called by the engine) ---------------------------------------

    def bind(self, clock: Clock) -> None:
        self._clock = clock

    # -- helpers for subclasses ----------------------------------------------

    @property
    def now(self):
        if self._clock is None:
            raise RuntimeError(f"{self.name}: not bound to an engine clock yet")
        return self._clock.now()

    def next_client_id(self) -> str:
        """A fresh order id, deterministic per run: `<name>-1`, `<name>-2`, ..."""
        return f"{self.name}-{next(self._ids)}"

    # -- callbacks -----------------------------------------------------------

    def on_start(self) -> Intents:
        return ()

    def on_trade(self, trade: Trade) -> Intents:
        return ()

    def on_book(self, book: BookSnapshot) -> Intents:
        return ()

    def on_kline(self, kline: Kline) -> Intents:
        return ()

    def on_timer(self, timer: Timer) -> Intents:
        return ()

    def on_fill(self, fill: Fill) -> Intents:
        return ()

    def on_stop(self) -> Intents:
        return ()
