"""A stub broker that records every intent and never fills.

Used to prove the strategy -> engine -> broker seam until the simulated broker
with real fill models (queue position, fill-on-touch, trade-through) lands in M3.
"""

from dataclasses import dataclass
from datetime import datetime

from ttp.core import Fill, MarketEvent, OrderIntent


@dataclass(frozen=True)
class RecordedIntent:
    time: datetime  # engine time when the strategy emitted it
    intent: OrderIntent


class RecordingBroker:
    def __init__(self) -> None:
        self.intents: list[RecordedIntent] = []
        self.events_seen = 0

    def on_event(self, event: MarketEvent) -> None:
        self.events_seen += 1

    def submit(self, intent: OrderIntent, now: datetime) -> None:
        self.intents.append(RecordedIntent(now, intent))

    def drain_fills(self) -> list[Fill]:
        return []
