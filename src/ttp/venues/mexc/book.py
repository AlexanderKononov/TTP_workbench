"""Local order book of one MEXC market, kept in sync from depth diffs. Pure: no I/O.

MEXC's rules ("How to properly maintain a local copy of the order book", spot v3
docs, checked 2026-10-28): subscribe to the depth-diff stream and buffer diffs;
take a REST snapshot (`GET /api/v3/depth`, `lastUpdateId`); drop diffs whose
`toVersion` <= `lastUpdateId`; the first remaining diff must have `fromVersion`
<= `lastUpdateId` + 1, and every later diff `fromVersion` == previous `toVersion`
+ 1; anything else means a gap: take a new snapshot. Diff levels carry absolute
quantities; quantity 0 removes the level.

`BookSync` is that state machine. It never fetches anything: it sets
`snapshot_wanted` and the I/O layer feeds it `on_snapshot`. Every state change
is returned as a `BookEvent` so the recorder can keep a gap log.
"""

from dataclasses import dataclass
from typing import Literal


@dataclass(frozen=True)
class Level:
    price: float
    quantity: float


@dataclass(frozen=True)
class BookSnapshot:
    """REST depth snapshot; `last_update_id` is its version."""

    market: str
    last_update_id: int
    bids: tuple[Level, ...]
    asks: tuple[Level, ...]


@dataclass(frozen=True)
class DepthDiff:
    """One depth-diff push covering versions `from_version`..`to_version`."""

    market: str
    from_version: int
    to_version: int
    bids: tuple[Level, ...]
    asks: tuple[Level, ...]
    time_ms: int


@dataclass(frozen=True)
class Trade:
    market: str
    price: float
    quantity: float
    side: Literal["buy", "sell"]  # taker side
    time_ms: int
    trade_id: str


BookEventKind = Literal[
    "synced", "gap", "stale_snapshot", "snapshot_failed", "disconnected"
]


@dataclass(frozen=True)
class BookEvent:
    """A sync state change: the recorder's gap log is built from these.

    `time_ms` is the venue's send time when the event comes from a push, the
    local wall clock when it comes from the connection, None if unknown.
    """

    market: str
    kind: BookEventKind
    time_ms: int | None
    detail: str


class OrderBook:
    """Price levels of one market, updated in place by absolute-quantity levels."""

    def __init__(
        self, bids: tuple[Level, ...] = (), asks: tuple[Level, ...] = ()
    ) -> None:
        self._bids: dict[float, float] = {}
        self._asks: dict[float, float] = {}
        self.apply(bids, asks)

    def apply(self, bids: tuple[Level, ...], asks: tuple[Level, ...]) -> None:
        for side, levels in ((self._bids, bids), (self._asks, asks)):
            for level in levels:
                if level.quantity == 0:
                    side.pop(level.price, None)
                else:
                    side[level.price] = level.quantity

    def bids(self, depth: int | None = None) -> list[Level]:
        """Best (highest) bids first."""
        prices = sorted(self._bids, reverse=True)[:depth]
        return [Level(p, self._bids[p]) for p in prices]

    def asks(self, depth: int | None = None) -> list[Level]:
        """Best (lowest) asks first."""
        prices = sorted(self._asks)[:depth]
        return [Level(p, self._asks[p]) for p in prices]

    @property
    def best_bid(self) -> Level | None:
        return Level(p, self._bids[p]) if (p := max(self._bids, default=None)) else None

    @property
    def best_ask(self) -> Level | None:
        return Level(p, self._asks[p]) if (p := min(self._asks, default=None)) else None

    def __len__(self) -> int:
        return len(self._bids) + len(self._asks)


class BookSync:
    """Keeps one market's `OrderBook` in sync with MEXC's version rules.

    `book` is None until synced; `snapshot_wanted` tells the I/O layer to fetch
    a snapshot (after subscribing, a gap, or a stale snapshot).
    """

    def __init__(self, market: str) -> None:
        self.market = market
        self.book: OrderBook | None = None
        self.version: int | None = None
        self.snapshot_wanted = True
        self._buffer: list[DepthDiff] = []

    @property
    def synced(self) -> bool:
        return self.book is not None

    def on_diff(self, diff: DepthDiff) -> list[BookEvent]:
        """Apply a diff, or buffer it while unsynced. Returns a gap event if one opens."""
        if self.book is None or self.version is None:
            self._buffer.append(diff)
            return []
        if diff.to_version <= self.version:
            return []  # already covered by the snapshot or an earlier diff
        if diff.from_version > self.version + 1:
            expected, self.version = self.version + 1, None
            self.book, self.snapshot_wanted = None, True
            self._buffer = [diff]
            return [
                BookEvent(
                    self.market,
                    "gap",
                    diff.time_ms,
                    f"expected version {expected}, got {diff.from_version}",
                )
            ]
        self.book.apply(diff.bids, diff.asks)
        self.version = diff.to_version
        return []

    def on_snapshot(self, snapshot: BookSnapshot) -> list[BookEvent]:
        """Initialise the book from a snapshot and replay buffered diffs onto it."""
        pending = [d for d in self._buffer if d.to_version > snapshot.last_update_id]
        if pending and pending[0].from_version > snapshot.last_update_id + 1:
            return [
                BookEvent(
                    self.market,
                    "stale_snapshot",
                    pending[0].time_ms,
                    f"snapshot version {snapshot.last_update_id}, "
                    f"stream resumes at {pending[0].from_version}",
                )
            ]
        self.book = OrderBook(snapshot.bids, snapshot.asks)
        self.version = snapshot.last_update_id
        self.snapshot_wanted = False
        self._buffer = []
        events = [
            BookEvent(
                self.market,
                "synced",
                pending[0].time_ms if pending else None,
                f"version {snapshot.last_update_id}, {len(pending)} buffered diffs",
            )
        ]
        for diff in pending:
            events += self.on_diff(diff)
        return events

    def on_disconnect(self, time_ms: int | None, detail: str = "") -> list[BookEvent]:
        """Forget the book: versions after a reconnect need a fresh snapshot."""
        self.book, self.version = None, None
        self.snapshot_wanted = True
        self._buffer = []
        return [BookEvent(self.market, "disconnected", time_ms, detail)]
