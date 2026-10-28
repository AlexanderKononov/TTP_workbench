"""The engine's clock: event time, the same in every stage.

The engine advances the clock to each event's `time` before handing it to the
strategy, so `now` is the time of the event being processed. In replay that is
the recorded time; in paper and live the feed stamps events with the venue's
time, so the clock tracks wall time. The clock never moves backwards: a live feed
may interleave streams slightly out of order and must not crash the engine.
"""

from datetime import UTC, datetime
from typing import Protocol


class Clock(Protocol):
    def now(self) -> datetime: ...


EPOCH = datetime(1970, 1, 1, tzinfo=UTC)


class SimulatedClock:
    def __init__(self, start: datetime = EPOCH) -> None:
        _require_utc(start)
        self._now = start

    def now(self) -> datetime:
        return self._now

    def advance_to(self, time: datetime) -> None:
        _require_utc(time)
        self._now = max(self._now, time)


def _require_utc(time: datetime) -> None:
    if time.tzinfo is None or time.utcoffset() is None:
        raise ValueError(f"clock times must be tz-aware (UTC): {time!r}")
