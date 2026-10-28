"""Recorder: a dataset's markets recorded live into Parquet.

Three series per market: every trade (`trades`), the top `BOOK_DEPTH` levels of
the locally synced order book once a second (`book_1s`), and a gap log
(`gaps`) of every sync state change, so a backtest can tell absent data from a
quiet market. Rows are buffered in memory and merged into the dataset's hourly
part files every `flush_interval_s` and on stop.

`Session` is the pure part: fed venue events and clock ticks, it buffers rows,
tracks which markets are synced and decides when to alert. `Recorder` is the
runtime around it: one thread per WebSocket connection (at most
`MARKETS_PER_CONNECTION` markets each, the venue's subscription cap), one
sampler thread on the whole-second grid, and the calling thread flushing,
heartbeating a run file for `ttp record status` and polling a stop file for
`ttp record stop`. Reconnect and resync live in the venue connector; the
recorder only logs what it is told and alerts when a market stays unsynced.
"""

import json
import math
import os
import threading
import time
from collections import Counter, defaultdict
from collections.abc import Callable, Iterator, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

import pandas as pd

from ttp.data.store import BOOK_1S, BOOK_DEPTH, GAPS, TRADES, DatasetStore, DataType
from ttp.venues.mexc.book import BookEvent, DepthDiff, Level, OrderBook, Trade
from ttp.venues.mexc.client import MexcClient
from ttp.venues.mexc.stream import (
    MAX_SUBSCRIPTIONS,
    LiveBooks,
    MexcMarketStream,
    StreamStatus,
)

MARKETS_PER_CONNECTION = MAX_SUBSCRIPTIONS // 2
FLUSH_INTERVAL_S = 60.0
ALERT_AFTER_S = 120.0
HEARTBEAT_S = 10.0
STALE_AFTER_S = 3 * HEARTBEAT_S  # a run file older than this belongs to a dead process
RUN_FILE = "recorder.json"
STOP_FILE = "recorder.stop"
JOIN_TIMEOUT_S = 5.0


def _ts(seconds: float) -> pd.Timestamp:
    return pd.Timestamp(round(seconds * 1000), unit="ms", tz="UTC")


@dataclass(frozen=True)
class Top:
    """A market's best levels, published by the consumer thread after each diff."""

    version: int
    bids: tuple[Level, ...]
    asks: tuple[Level, ...]


class Session:
    """Recording state of one dataset: buffers rows, tracks sync, raises alerts.

    Thread-safe: consumer threads call `on_event`, the sampler `sample`, the
    writer `take`.
    """

    def __init__(
        self,
        name: str,
        markets: Sequence[str],
        alert_after_s: float = ALERT_AFTER_S,
        depth: int = BOOK_DEPTH,
    ) -> None:
        self.name = name
        self.markets = list(markets)
        self.alert_after_s = alert_after_s
        self.depth = depth
        self.buffered: Counter[str] = Counter()  # rows buffered per data type, ever
        self._top: dict[str, Top | None] = dict.fromkeys(self.markets)
        self._unsynced_since: dict[str, float] = {}
        self._alerted: set[str] = set()
        self._rows: dict[tuple[str, str], list[dict]] = defaultdict(list)
        self._lock = threading.Lock()

    @property
    def synced(self) -> list[str]:
        return [m for m in self.markets if self._top[m] is not None]

    def start(self, now: float) -> None:
        with self._lock:
            for market in self.markets:
                self._unsynced_since[market] = now
                self._gap(market, _ts(now), "start", None, "recording started")

    def stop(self, now: float) -> None:
        with self._lock:
            for market in self.markets:
                self._close_missing(market, now)
                self._gap(market, _ts(now), "stop", None, "recording stopped")

    def on_event(self, event: object, books: LiveBooks, now: float) -> None:
        """Account for one `LiveBooks.events()` item; `now` stamps clock-less events."""
        with self._lock:
            if isinstance(event, Trade):
                self._add(
                    event.market,
                    TRADES,
                    {
                        "time": _ts(event.time_ms / 1000),
                        "price": event.price,
                        "quantity": event.quantity,
                        "side": event.side,
                    },
                )
            elif isinstance(event, DepthDiff):
                self._publish(event.market, books.book(event.market), books)
            elif isinstance(event, BookEvent):
                t = event.time_ms / 1000 if event.time_ms else now
                if event.kind == "synced":
                    self._close_missing(event.market, t)
                    self._publish(event.market, books.book(event.market), books)
                else:
                    self._top[event.market] = None
                    self._unsynced_since.setdefault(event.market, t)
                self._gap(event.market, _ts(t), event.kind, None, event.detail)
            elif isinstance(event, StreamStatus) and event.kind == "error":
                for market in books.syncs:
                    self._gap(
                        market,
                        _ts(event.time_ms / 1000),
                        "stream_error",
                        None,
                        event.detail,
                    )

    def sample(self, second: int) -> int:
        """Buffer a book row stamped `second` for every synced market; returns how many."""
        with self._lock:
            count = 0
            for market, top in self._top.items():
                if top is None:
                    continue
                row: dict = {"time": _ts(second), "version": top.version}
                for i in range(self.depth):
                    bid = top.bids[i] if i < len(top.bids) else None
                    ask = top.asks[i] if i < len(top.asks) else None
                    row[f"bid_price_{i + 1}"] = bid.price if bid else None
                    row[f"bid_qty_{i + 1}"] = bid.quantity if bid else None
                    row[f"ask_price_{i + 1}"] = ask.price if ask else None
                    row[f"ask_qty_{i + 1}"] = ask.quantity if ask else None
                self._add(market, BOOK_1S, row)
                count += 1
            return count

    def alerts(self, now: float) -> list[str]:
        """Messages due now: markets unsynced beyond the threshold, and recoveries."""
        with self._lock:
            stalled = sorted(
                m
                for m, since in self._unsynced_since.items()
                if now - since >= self.alert_after_s and m not in self._alerted
            )
            recovered = sorted(m for m in self._alerted if self._top[m] is not None)
            self._alerted.update(stalled)
            self._alerted.difference_update(recovered)
        out = []
        if stalled:
            out.append(
                f"recorder '{self.name}': {len(stalled)} of {len(self.markets)} "
                f"markets without a synced book for over {self.alert_after_s:.0f} s: "
                + ", ".join(stalled)
            )
        if recovered:
            out.append(f"recorder '{self.name}': synced again: " + ", ".join(recovered))
        return out

    def take(self) -> Iterator[tuple[str, DataType, pd.DataFrame]]:
        """Hand out and clear every buffered (market, data type) frame."""
        with self._lock:
            rows, self._rows = self._rows, defaultdict(list)
        for (market, type_name), items in rows.items():
            data_type = {t.name: t for t in (TRADES, BOOK_1S, GAPS)}[type_name]
            yield (
                market,
                data_type,
                pd.DataFrame(items, columns=list(data_type.columns)),
            )

    # -- under the lock ------------------------------------------------------

    def _add(self, market: str, data_type: DataType, row: dict) -> None:
        self._rows[(market, data_type.name)].append(row)
        self.buffered[data_type.name] += 1

    def _gap(
        self, market: str, time: pd.Timestamp, kind: str, until, detail: str
    ) -> None:
        self._add(
            market, GAPS, {"time": time, "kind": kind, "until": until, "detail": detail}
        )

    def _close_missing(self, market: str, now: float) -> None:
        since = self._unsynced_since.pop(market, None)
        if since is not None and now > since:
            self._gap(
                market,
                _ts(since),
                "missing",
                _ts(now),
                f"{now - since:.1f} s without a synced book",
            )

    def _publish(self, market: str, book: OrderBook | None, books: LiveBooks) -> None:
        if book is None:
            self._top[market] = None
            return
        version = books.syncs[market].version or 0
        self._top[market] = Top(
            version, tuple(book.bids(self.depth)), tuple(book.asks(self.depth))
        )


def connection_groups(markets: Sequence[str]) -> list[list[str]]:
    """Split markets over connections of at most `MARKETS_PER_CONNECTION`."""
    size = MARKETS_PER_CONNECTION
    return [list(markets[i : i + size]) for i in range(0, len(markets), size)]


@dataclass
class Connection:
    markets: list[str]
    stream: MexcMarketStream
    books: LiveBooks
    thread: threading.Thread | None = None


class Recorder:
    """Runs a `Session` live: connection threads, 1 s sampler, flush, run/stop files."""

    def __init__(
        self,
        store: DatasetStore,
        dataset: str,
        venue: str,
        markets: Sequence[str],
        client: MexcClient,
        stream_factory: Callable[[list[str]], MexcMarketStream] = MexcMarketStream,
        notify: Callable[[str], None] | None = None,
        log: Callable[[str], None] | None = None,
        clock: Callable[[], float] = time.time,
        sleep: Callable[[float], None] = time.sleep,
        flush_interval_s: float = FLUSH_INTERVAL_S,
        alert_after_s: float = ALERT_AFTER_S,
        heartbeat_s: float = HEARTBEAT_S,
    ) -> None:
        self.store = store
        self.dataset = dataset
        self.venue = venue
        self.session = Session(dataset, markets, alert_after_s)
        self.connections = [
            Connection(group, stream, LiveBooks(group, client, stream))
            for group in connection_groups(markets)
            for stream in (stream_factory(group),)
        ]
        self.written: Counter[str] = Counter()
        self.flushes = 0
        self._notify = notify
        self._log = log or (lambda line: None)
        self._clock = clock
        self._sleep = sleep
        self._flush_interval_s = flush_interval_s
        self._heartbeat_s = heartbeat_s
        self._stop = threading.Event()
        self._sampler: threading.Thread | None = None
        self._started: float | None = None

    @property
    def run_path(self) -> Path:
        return self.store.dataset_dir(self.dataset) / RUN_FILE

    @property
    def stop_path(self) -> Path:
        return self.store.dataset_dir(self.dataset) / STOP_FILE

    def run(self, seconds: float | None = None) -> None:
        """Record until `stop()`, Ctrl-C, the stop file appears or `seconds` pass."""
        self.start()
        deadline = None if seconds is None else self._clock() + seconds
        next_flush = next_beat = self._clock()
        try:
            while not self._stop.is_set():
                now = self._clock()
                if self.stop_path.exists() or (deadline and now >= deadline):
                    break
                if now >= next_flush:
                    self.flush()
                    next_flush = now + self._flush_interval_s
                if now >= next_beat:
                    self._write_run_file()
                    next_beat = now + self._heartbeat_s
                for text in self.session.alerts(now):
                    self._alert(text)
                self._sleep(min(1.0, max(next_flush - now, 0.05)))
        except KeyboardInterrupt:
            self._log("stopping")
        finally:
            self.stop()

    def start(self) -> None:
        self._started = self._clock()
        self.stop_path.unlink(missing_ok=True)
        self.session.start(self._started)
        self._write_run_file()
        for c in self.connections:
            c.thread = threading.Thread(target=self._consume, args=(c,), daemon=True)
            c.thread.start()
        self._sampler = threading.Thread(target=self._sample_loop, daemon=True)
        self._sampler.start()

    def stop(self) -> None:
        """Stop the streams, flush everything and remove the run file. Idempotent."""
        if self._started is None:
            return
        self._stop.set()
        for c in self.connections:
            c.stream.stop()
        for t in [c.thread for c in self.connections] + [self._sampler]:
            if t is not None:
                t.join(JOIN_TIMEOUT_S)
        self.session.stop(self._clock())
        self.flush()
        self.run_path.unlink(missing_ok=True)
        self.stop_path.unlink(missing_ok=True)
        self._started = None

    def flush(self) -> Counter[str]:
        """Write every buffered row to the dataset; returns rows new per data type."""
        new: Counter[str] = Counter()
        for market, data_type, rows in self.session.take():
            new[data_type.name] += self.store.append(
                self.dataset, self.venue, market, data_type, rows
            )
        self.written.update(new)
        self.flushes += 1
        self._write_run_file()
        self._log(
            "flushed: "
            + ", ".join(f"{t} +{new[t]}" for t in ("trades", "book_1s", "gaps"))
            + f"; synced {len(self.session.synced)}/{len(self.session.markets)}"
        )
        return new

    # -- threads -------------------------------------------------------------

    def _consume(self, connection: Connection) -> None:
        for event in connection.books.events():
            self.session.on_event(event, connection.books, self._clock())
            if isinstance(event, BookEvent):
                self._log(f"{event.market} {event.kind} {event.detail}".rstrip())
            elif isinstance(event, StreamStatus) and event.kind != "subscribed":
                self._log(f"stream {event.kind} {event.detail}".rstrip())
            if self._stop.is_set():
                return

    def _sample_loop(self) -> None:
        second = math.floor(self._clock()) + 1
        while not self._stop.is_set():
            wait = second - self._clock()
            if wait > 0:
                self._sleep(min(wait, 0.5))
                continue
            self.session.sample(second)
            second = max(second + 1, math.floor(self._clock()))

    # -- files and alerts ----------------------------------------------------

    def _write_run_file(self) -> None:
        status = {
            "dataset": self.dataset,
            "pid": os.getpid(),
            "started": _iso(self._started),
            "updated": _iso(self._clock()),
            "markets": self.session.markets,
            "connections": len(self.connections),
            "synced": self.session.synced,
            "written": dict(self.written),
            "flushes": self.flushes,
        }
        path = self.run_path
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(".tmp")
        tmp.write_text(json.dumps(status, indent=1), encoding="utf-8")
        os.replace(tmp, path)

    def _alert(self, text: str) -> None:
        self._log(f"alert: {text}")
        if self._notify is not None:
            try:
                self._notify(text)
            except Exception as exc:  # noqa: BLE001 - recording must outlive Telegram
                self._log(f"alert not sent: {exc}")


def _iso(seconds: float | None) -> str | None:
    if seconds is None:
        return None
    return datetime.fromtimestamp(seconds, UTC).isoformat(timespec="seconds")


@dataclass(frozen=True)
class RunStatus:
    dataset: str
    pid: int
    started: datetime
    updated: datetime
    markets: int
    synced: int
    connections: int
    written: dict[str, int]
    age_s: float  # seconds since the last heartbeat

    @property
    def stale(self) -> bool:
        return self.age_s > STALE_AFTER_S


def read_status(store: DatasetStore, now: float) -> list[RunStatus]:
    """Run files of every dataset under the store, with their heartbeat age."""
    out = []
    for path in sorted(store.root.glob(f"*/{RUN_FILE}")):
        raw = json.loads(path.read_text(encoding="utf-8"))
        updated = datetime.fromisoformat(raw["updated"])
        out.append(
            RunStatus(
                dataset=raw["dataset"],
                pid=raw["pid"],
                started=datetime.fromisoformat(raw["started"]),
                updated=updated,
                markets=len(raw["markets"]),
                synced=len(raw["synced"]),
                connections=raw["connections"],
                written=raw["written"],
                age_s=now - updated.timestamp(),
            )
        )
    return out


def request_stop(
    store: DatasetStore,
    dataset: str,
    now: Callable[[], float] = time.time,
    sleep: Callable[[float], None] = time.sleep,
    timeout_s: float = 30.0,
) -> str:
    """Ask a running recorder to stop and wait for it; returns what happened.

    One of `"stopped"`, `"not running"` or `"cleared"` (the run file was stale:
    its process is gone, so the file was removed) or `"timeout"`.
    """
    run_path = store.dataset_dir(dataset) / RUN_FILE
    stop_path = store.dataset_dir(dataset) / STOP_FILE
    if not run_path.exists():
        return "not running"
    status = [s for s in read_status(store, now()) if s.dataset == dataset]
    if status and status[0].stale:
        run_path.unlink(missing_ok=True)
        stop_path.unlink(missing_ok=True)
        return "cleared"
    stop_path.touch()
    deadline = now() + timeout_s
    while now() < deadline:
        if not run_path.exists():
            return "stopped"
        sleep(0.5)
    return "timeout"
