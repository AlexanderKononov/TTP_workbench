"""MEXC spot public WebSocket: depth diffs and trades, with reconnect. The only I/O here.

Protocol (spot v3 docs, checked 2026-10-28): endpoint `wss://wbs-api.mexc.com/ws`;
JSON `{"method": "SUBSCRIPTION", "params": [streams]}` is answered by
`{"id": 0, "code": 0, "msg": "<streams joined by ,>"}`; pushes are binary
protobuf (`PushDataV3ApiWrapper`); `{"method": "PING"}` gets `{"msg": "PONG"}`
and keeps an idle connection open (the server drops it after 1 minute without
data, 30 s without a subscription, and always after 24 hours). At most 30
subscriptions per connection; two streams per market.

`MexcMarketStream.messages()` yields `StreamStatus`, `DepthDiff` and `Trade`
values and reconnects with backoff. `LiveBooks` sits on top: it keeps one
`BookSync` per market, fetches REST snapshots when a sync asks for one, and
yields the resulting `BookEvent`s as well, so the recorder gets its gap log and
`ttp watch` its display from one iterator.
"""

import json
import time
from collections.abc import Callable, Iterable, Iterator, Sequence
from contextlib import AbstractContextManager
from dataclasses import dataclass
from typing import Literal, Protocol

from websockets.exceptions import WebSocketException
from websockets.sync.client import connect as ws_connect

from ttp.venues.mexc.book import BookEvent, BookSync, DepthDiff, OrderBook, Trade
from ttp.venues.mexc.client import MexcClient, MexcError
from ttp.venues.mexc.proto import ProtoError, decode_push

WS_URL = "wss://wbs-api.mexc.com/ws"
MAX_SUBSCRIPTIONS = 30
DEPTH_STREAM = "spot@public.aggre.depth.v3.api.pb@100ms@{market}"
DEALS_STREAM = "spot@public.aggre.deals.v3.api.pb@100ms@{market}"
PING = json.dumps({"method": "PING"})
BACKOFF_S = (1.0, 2.0, 5.0, 10.0, 30.0)


def market_streams(markets: Iterable[str]) -> list[str]:
    return [
        pattern.format(market=m)
        for m in markets
        for pattern in (DEPTH_STREAM, DEALS_STREAM)
    ]


def subscribe_message(streams: Sequence[str]) -> str:
    return json.dumps({"method": "SUBSCRIPTION", "params": list(streams)})


StatusKind = Literal["connected", "subscribed", "disconnected", "error"]


@dataclass(frozen=True)
class StreamStatus:
    """Connection-level event; `detail` carries the venue's message or the error."""

    kind: StatusKind
    time_ms: int
    detail: str = ""


StreamMessage = StreamStatus | DepthDiff | Trade


class Connection(Protocol):
    """What we use of a `websockets.sync` connection (so tests can fake it)."""

    def send(self, message: str) -> None: ...

    def recv(self, timeout: float | None = None) -> str | bytes: ...


Connect = Callable[[str], AbstractContextManager[Connection]]


def _default_connect(url: str) -> AbstractContextManager[Connection]:
    return ws_connect(url, max_size=None, open_timeout=15)


class MexcMarketStream:
    """One connection carrying depth diffs and trades for up to 15 markets."""

    def __init__(
        self,
        markets: Sequence[str],
        url: str = WS_URL,
        connect: Connect = _default_connect,
        clock: Callable[[], float] = time.time,
        sleep: Callable[[float], None] = time.sleep,
        ping_interval_s: float = 20.0,
        recv_timeout_s: float = 1.0,
        backoff_s: Sequence[float] = BACKOFF_S,
    ) -> None:
        self.streams = market_streams(markets)
        if len(self.streams) > MAX_SUBSCRIPTIONS:
            raise ValueError(
                f"{len(markets)} markets need {len(self.streams)} subscriptions; "
                f"one connection takes at most {MAX_SUBSCRIPTIONS}"
            )
        self._url = url
        self._connect = connect
        self._clock = clock
        self._sleep = sleep
        self._ping_interval_s = ping_interval_s
        self._recv_timeout_s = recv_timeout_s
        self._backoff_s = backoff_s
        self._stopped = False

    def stop(self) -> None:
        self._stopped = True

    def messages(self) -> Iterator[StreamMessage]:
        """Decoded pushes and connection events, forever (until `stop()`)."""
        failures = 0
        while not self._stopped:
            try:
                with self._connect(self._url) as ws:
                    yield StreamStatus("connected", self._now_ms())
                    ws.send(subscribe_message(self.streams))
                    for message in self._session(ws):
                        if (
                            isinstance(message, StreamStatus)
                            and message.kind == "subscribed"
                        ):
                            failures = 0
                        yield message
                        if self._stopped:
                            return
            except (OSError, TimeoutError, WebSocketException) as exc:
                yield StreamStatus(
                    "disconnected", self._now_ms(), f"{type(exc).__name__}: {exc}"
                )
            if self._stopped:
                return
            self._sleep(self._backoff_s[min(failures, len(self._backoff_s) - 1)])
            failures += 1

    def _session(self, ws: Connection) -> Iterator[StreamMessage]:
        last_ping = self._clock()
        while not self._stopped:
            try:
                raw = ws.recv(timeout=self._recv_timeout_s)
            except TimeoutError:
                raw = None
            if self._clock() - last_ping >= self._ping_interval_s:
                ws.send(PING)
                last_ping = self._clock()
            if raw is None:
                continue
            if isinstance(raw, str):
                status = self._control(raw)
                if status is not None:
                    yield status
                continue
            try:
                decoded = decode_push(raw)
            except ProtoError as exc:
                yield StreamStatus("error", self._now_ms(), str(exc))
                continue
            if isinstance(decoded, DepthDiff):
                yield decoded
            elif decoded is not None:
                yield from decoded

    def _control(self, text: str) -> StreamStatus | None:
        try:
            body = json.loads(text)
        except ValueError:
            return StreamStatus(
                "error", self._now_ms(), f"unreadable control frame: {text[:200]}"
            )
        msg = str(body.get("msg", ""))
        if msg == "PONG":
            return None
        if body.get("code", 0) != 0 or msg.startswith("Not Subscribed"):
            # A refused subscription (unknown symbol) still comes with code 0.
            return StreamStatus(
                "error", self._now_ms(), f"{msg} (code {body.get('code')})"
            )
        return StreamStatus("subscribed", self._now_ms(), msg)

    def _now_ms(self) -> int:
        return int(self._clock() * 1000)


class MessageSource(Protocol):
    def messages(self) -> Iterator[StreamMessage]: ...


class LiveBooks:
    """Synced order books for the stream's markets, fed by REST snapshots on demand."""

    def __init__(
        self, markets: Sequence[str], client: MexcClient, stream: MessageSource
    ) -> None:
        self.syncs = {m: BookSync(m) for m in markets}
        self._client = client
        self._stream = stream
        self._live = False

    def book(self, market: str) -> OrderBook | None:
        return self.syncs[market].book

    def events(self) -> Iterator[StreamMessage | BookEvent]:
        """Stream messages interleaved with the book events they cause.

        A `DepthDiff` is yielded only once it has been applied to its book.
        """
        for message in self._stream.messages():
            if isinstance(message, StreamStatus):
                yield message
                if message.kind == "subscribed":
                    self._live = True
                    for sync in self.syncs.values():
                        yield from self._snapshot(sync)
                elif message.kind == "disconnected":
                    self._live = False
                    for sync in self.syncs.values():
                        yield from sync.on_disconnect(message.time_ms, message.detail)
            elif isinstance(message, DepthDiff):
                sync = self.syncs.get(message.market)
                if sync is None:
                    continue
                yield from sync.on_diff(message)
                if sync.synced:
                    yield message
                elif self._live and sync.snapshot_wanted:
                    yield from self._snapshot(sync)
                    if sync.synced:
                        yield message
            else:
                yield message

    def _snapshot(self, sync: BookSync) -> Iterator[BookEvent]:
        try:
            snapshot = self._client.depth(sync.market)
        except MexcError as exc:
            yield BookEvent(sync.market, "snapshot_failed", None, str(exc))
            return
        yield from sync.on_snapshot(snapshot)
