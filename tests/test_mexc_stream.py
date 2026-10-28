"""MEXC WebSocket stream and live books, driven by frames captured from the real feed.

Fixtures `tests/fixtures/mexc/ws_frames_*.json` hold raw text/binary frames plus
the REST depth snapshot taken during the capture; a scripted fake socket replays
them, so nothing here touches the network (except the `live` test).
"""

import base64
import json
import time
from collections import deque
from pathlib import Path

import httpx
import pytest
from click.testing import CliRunner
from websockets.exceptions import ConnectionClosedError

from ttp.cli import main
from ttp.venues.mexc import (
    BookEvent,
    DepthDiff,
    Level,
    LiveBooks,
    MexcClient,
    MexcMarketStream,
    StreamStatus,
    Trade,
)
from ttp.venues.mexc.proto import ProtoError, decode_push
from ttp.venues.mexc.stream import PING, subscribe_message

FIXTURES = Path(__file__).parent / "fixtures" / "mexc"
ADX = json.loads((FIXTURES / "ws_frames_adxusdt.json").read_text())
BTC = json.loads((FIXTURES / "ws_frames_btcusdt.json").read_text())


def frames(capture: dict) -> list[str | bytes]:
    return [
        f["text"] if "text" in f else base64.b64decode(f["binary"])
        for f in capture["frames"]
    ]


class FakeSocket:
    """Scripted connection: items are frames, None (recv timeout) or an exception to raise."""

    def __init__(self, items) -> None:
        self.items = deque(items)
        self.sent: list[str] = []

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return None

    def send(self, message: str) -> None:
        self.sent.append(message)

    def recv(self, timeout=None):
        if not self.items:
            raise ConnectionClosedError(None, None)
        item = self.items.popleft()
        if item is None:
            raise TimeoutError
        if isinstance(item, Exception):
            raise item
        return item


class Sockets:
    """`connect` factory handing out scripted sockets in order."""

    def __init__(self, *sockets: FakeSocket) -> None:
        self.sockets = deque(sockets)
        self.urls: list[str] = []

    def __call__(self, url: str) -> FakeSocket:
        self.urls.append(url)
        if not self.sockets:
            raise OSError("no more connections")
        return self.sockets.popleft()


class DepthServer:
    """Serves `/api/v3/depth` with the fixture snapshot, or scripted bodies."""

    def __init__(self, bodies=None) -> None:
        self.bodies = deque(bodies or [])
        self.requests: list[dict] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v3/depth"
        self.requests.append(dict(request.url.params))
        body = self.bodies.popleft() if self.bodies else ADX["snapshot"]
        if isinstance(body, int):
            return httpx.Response(body, json={"code": body, "msg": "nope"})
        return httpx.Response(200, json=body)


def stream_with(sockets: Sockets, markets=("ADXUSDT",), **kw) -> MexcMarketStream:
    kw.setdefault("sleep", lambda s: None)
    kw.setdefault("clock", lambda: 1_700_000_000.0)
    return MexcMarketStream(list(markets), connect=sockets, **kw)


def collect(events, disconnects: int = 1, of=StreamStatus, limit: int = 1000) -> list:
    """Consume until the n-th "disconnected" event of class `of` (or `limit` items)."""
    out = []
    for e in events:
        out.append(e)
        if isinstance(e, of) and e.kind == "disconnected":
            disconnects -= 1
            if disconnects == 0:
                break
        if len(out) >= limit:
            break
    return out


def kinds(events) -> list[str]:
    return [e.kind for e in events if isinstance(e, BookEvent | StreamStatus)]


def test_decodes_captured_trades_and_depth_frames():
    decoded = [decode_push(f) for f in frames(BTC) if isinstance(f, bytes)]
    diffs = [d for d in decoded if isinstance(d, DepthDiff)]
    trades = [t for d in decoded if isinstance(d, list) for t in d]
    assert len(diffs) == 1 and len(trades) == 6
    diff = diffs[0]
    assert diff.market == "BTCUSDT"
    assert diff.from_version == 84764086625 and diff.to_version == 84764086734
    assert diff.time_ms == 1793176221944
    assert len(diff.bids) == 48 and len(diff.asks) == 23
    assert all(isinstance(level, Level) for level in diff.bids + diff.asks)
    assert trades[0] == Trade(
        "BTCUSDT", 81438.74, 0.00124132, "buy", 1793176222180,
        "744044306389520384X0_744044306389520385X0",
    )  # fmt: skip
    assert trades[3].side == "sell" and trades[3].price == 81438.75


def test_malformed_frame_is_a_proto_error():
    with pytest.raises(ProtoError):
        decode_push(b"\x08")  # truncated varint
    assert decode_push(b"") is None  # no body we handle


def test_captured_session_syncs_book_from_snapshot_and_diffs():
    socket = FakeSocket(frames(ADX))
    sockets = Sockets(socket)
    server = DepthServer()
    client = MexcClient(transport=httpx.MockTransport(server))
    books = LiveBooks(["ADXUSDT"], client, stream_with(sockets))

    events = collect(books.events(), of=BookEvent)

    assert kinds(events)[:3] == ["connected", "subscribed", "synced"]
    assert kinds(events)[-2:] == ["disconnected", "disconnected"]  # stream, then book
    assert server.requests == [{"symbol": "ADXUSDT", "limit": "5000"}]
    diffs = [e for e in events if isinstance(e, DepthDiff)]
    assert len(diffs) == 21  # every captured push applied, in order
    assert [d.from_version for d in diffs][:2] == [54004658, 54004661]
    sync = books.syncs["ADXUSDT"]
    assert not sync.synced  # forgotten on disconnect
    synced = next(e for e in events if isinstance(e, BookEvent))
    assert synced.detail == "version 54004657, 0 buffered diffs"
    assert sockets.urls == ["wss://wbs-api.mexc.com/ws"]
    assert socket.sent[0] == subscribe_message(
        [
            "spot@public.aggre.depth.v3.api.pb@100ms@ADXUSDT",
            "spot@public.aggre.deals.v3.api.pb@100ms@ADXUSDT",
        ]
    )


def test_book_state_after_captured_session():
    sockets = Sockets(FakeSocket(frames(ADX)))
    client = MexcClient(transport=httpx.MockTransport(DepthServer()))
    books = LiveBooks(["ADXUSDT"], client, stream_with(sockets))
    last = None
    for e in books.events():
        if isinstance(e, DepthDiff):
            book = books.book("ADXUSDT")
            last = (e.to_version, book.best_bid, book.best_ask, len(book))
        if isinstance(e, BookEvent) and e.kind == "disconnected":
            break
    assert books.book("ADXUSDT") is None
    assert last[0] == 54004695
    assert last[1] == Level(0.0567, 1199.02)
    assert last[2] == Level(0.0568, 21241.0)
    assert last[1].price < last[2].price


def test_pings_an_idle_connection():
    ticks = iter(range(0, 200, 10))
    socket = FakeSocket([ADX["frames"][0]["text"], None, None, None])
    stream = stream_with(
        Sockets(socket), clock=lambda: float(next(ticks)), ping_interval_s=20
    )
    events = collect(stream.messages())
    assert kinds(events) == ["connected", "subscribed", "disconnected"]
    assert socket.sent.count(PING) >= 1 and socket.sent[0] != PING


def test_reconnects_resubscribes_and_resyncs_after_a_drop():
    all_frames = frames(ADX)
    first = FakeSocket(all_frames[:3] + [ConnectionClosedError(None, None)])
    second = FakeSocket([all_frames[0]] + all_frames[3:])
    sockets = Sockets(first, second)
    # The second snapshot is newer, as it would be live: diffs resume at 54004662.
    server = DepthServer(
        [ADX["snapshot"], {**ADX["snapshot"], "lastUpdateId": 54004661}]
    )
    client = MexcClient(transport=httpx.MockTransport(server))
    slept: list[float] = []
    stream = stream_with(sockets, sleep=slept.append)
    books = LiveBooks(["ADXUSDT"], client, stream)

    events = collect(books.events(), disconnects=2, of=BookEvent)

    assert kinds(events) == [
        "connected", "subscribed", "synced", "disconnected", "disconnected",
        "connected", "subscribed", "synced", "disconnected", "disconnected",
    ]  # fmt: skip
    assert [e.detail for e in events if isinstance(e, StreamStatus)][2].startswith(
        "ConnectionClosedError"
    )
    assert len(server.requests) == 2
    assert slept == [1.0]
    assert first.sent[0] == second.sent[0]  # resubscribed with the same request
    assert len([e for e in events if isinstance(e, DepthDiff)]) == 21


def test_gap_in_stream_drops_book_and_resyncs_from_a_new_snapshot():
    def snapshot(version: int) -> dict:
        return {
            "lastUpdateId": version,
            "bids": [["0.0560", "10"]],
            "asks": [["0.0570", "5"]],
        }

    def diff(frm: int, to: int, bid: tuple[str, float]) -> DepthDiff:
        return DepthDiff(
            "ADXUSDT", frm, to, (Level(float(bid[0]), bid[1]),), (), 1000 + frm
        )

    class Source:
        def messages(self):
            yield StreamStatus("subscribed", 1)
            yield diff(101, 101, ("0.0561", 1))
            yield diff(102, 103, ("0.0562", 2))
            yield diff(110, 110, ("0.0563", 3))  # 104..109 missing
            yield diff(111, 111, ("0.0564", 4))

    server = DepthServer([snapshot(100), snapshot(109)])
    client = MexcClient(transport=httpx.MockTransport(server))
    books = LiveBooks(["ADXUSDT"], client, Source())

    events = list(books.events())

    assert kinds(events) == ["subscribed", "synced", "gap", "synced"]
    gap = next(e for e in events if isinstance(e, BookEvent) and e.kind == "gap")
    assert gap.detail == "expected version 104, got 110" and gap.time_ms == 1110
    assert [e.from_version for e in events if isinstance(e, DepthDiff)] == [
        101,
        102,
        110,
        111,
    ]
    book = books.book("ADXUSDT")
    assert book.best_bid == Level(0.0564, 4) and books.syncs["ADXUSDT"].version == 111
    assert len(server.requests) == 2


def test_failed_snapshot_is_reported_and_retried_on_the_next_diff():
    class Source:
        def messages(self):
            yield StreamStatus("subscribed", 1)
            yield DepthDiff("ADXUSDT", 54004658, 54004660, (), (Level(0.06, 1),), 5)
            yield DepthDiff("ADXUSDT", 54004661, 54004661, (), (Level(0.06, 2),), 6)

    server = DepthServer([429])
    client = MexcClient(transport=httpx.MockTransport(server))
    books = LiveBooks(["ADXUSDT"], client, Source())
    events = list(books.events())
    assert kinds(events) == ["subscribed", "snapshot_failed", "synced"]
    assert "rate limit" in events[1].detail
    assert [e.from_version for e in events if isinstance(e, DepthDiff)] == [
        54004658,
        54004661,
    ]
    assert Level(0.06, 2) in books.book("ADXUSDT").asks()


def test_venue_error_and_undecodable_frames_surface_as_error_status():
    refused = (  # MEXC refuses an unknown symbol with code 0 (seen live 2026-10-28)
        '{"id":0,"code":0,"msg":"Not Subscribed successfully! '
        '[spot@public.aggre.deals.v3.api.pb@100ms@NOPEUSDT]. Reason： Blocked!"}'
    )
    sockets = Sockets(
        FakeSocket([refused, '{"id":0,"code":1,"msg":"Oops"}', b"\x08", "not json"])
    )
    events = collect(stream_with(sockets).messages())
    assert kinds(events) == [
        "connected",
        "error",
        "error",
        "error",
        "error",
        "disconnected",
    ]
    assert events[1].detail.startswith("Not Subscribed successfully!")
    assert events[2].detail == "Oops (code 1)"


def test_too_many_markets_for_one_connection_is_rejected():
    with pytest.raises(ValueError, match="32 subscriptions"):
        MexcMarketStream([f"M{i}USDT" for i in range(16)])


def test_watch_command_prints_top_of_book_trades_and_sync_events():
    class Source:
        def __init__(self, markets):
            assert markets == ["ADXUSDT"]

        def messages(self):
            yield StreamStatus("connected", 1793176158000)
            yield StreamStatus("subscribed", 1793176158100, "streams")
            yield DepthDiff(
                "ADXUSDT",
                54004658,
                54004660,
                (),
                (Level(0.0568, 21241.0),),
                1793176158541,
            )
            yield DepthDiff(
                "ADXUSDT", 54004661, 54004661, (), (Level(0.0569, 1.0),), 1793176158641
            )  # top unchanged
            yield Trade("ADXUSDT", 0.0568, 120.5, "buy", 1793176158700, "t1")
            yield DepthDiff(
                "ADXUSDT", 54004670, 54004670, (Level(0.0566, 9.0),), (), 1793176159000
            )  # gap

    server = DepthServer(
        [ADX["snapshot"], {**ADX["snapshot"], "lastUpdateId": 54004669}]
    )
    client = MexcClient(transport=httpx.MockTransport(server))
    result = CliRunner().invoke(
        main,
        ["watch", "adx/usdt"],
        obj={"mexc": client, "stream": Source},
        prog_name="ttp",
    )
    assert result.exit_code == 0, result.output
    lines = result.output.splitlines()
    assert lines[0] == "08:29:18.000 stream connected"
    assert lines[1] == "08:29:18.100 stream subscribed streams"
    assert lines[2] == "--:--:--.--- ADXUSDT SYNCED version 54004657, 0 buffered diffs"
    top = "ADXUSDT bid 0.0567 x 1199.02 | ask 0.0568 x 21241 | spread 0.18%"
    assert lines[3] == f"--:--:--.--- {top}"  # shown right after a sync
    assert lines[4] == "08:29:18.700 ADXUSDT TRADE buy  0.0568 x 120.5"
    assert (
        lines[5] == "08:29:19.000 ADXUSDT GAP expected version 54004662, got 54004670"
    )
    assert lines[6] == "08:29:19.000 ADXUSDT SYNCED version 54004669, 1 buffered diffs"
    assert lines[7] == f"08:29:19.000 {top}"
    assert len(lines) == 8  # diffs that leave the top unchanged print nothing


def test_watch_command_stops_after_seconds_and_reports_stream_errors():
    class Source:
        def __init__(self, markets):
            pass

        def messages(self):
            yield StreamStatus("subscribed", 1)
            while True:
                yield Trade("ADXUSDT", 0.05, 1.0, "sell", 2, "t")

    ticks = iter(
        [0.0, 0.5, 1.0, 1.5, 2.0, 2.5]
    )  # deadline, subscribed, synced, trades...
    client = MexcClient(transport=httpx.MockTransport(DepthServer()))
    result = CliRunner().invoke(
        main,
        ["watch", "ADXUSDT", "--seconds", "2"],
        obj={"mexc": client, "stream": Source, "clock": lambda: next(ticks)},
        prog_name="ttp",
    )
    assert result.exit_code == 0, result.output
    assert result.output.count("TRADE") == 2

    class Broken(Source):
        def messages(self):
            yield StreamStatus("error", 1, "Blocked")

    result = CliRunner().invoke(
        main,
        ["watch", "ADXUSDT"],
        obj={"mexc": client, "stream": Broken},
        prog_name="ttp",
    )
    assert result.exit_code == 1
    assert "Error: MEXC stream error: Blocked" in result.output


@pytest.mark.live
def test_live_btcusdt_book_syncs_and_stays_uncrossed():
    """Drift check against the real feed: subscribe, snapshot, apply a few diffs."""
    stream = MexcMarketStream(["BTCUSDT"])
    books = LiveBooks(["BTCUSDT"], MexcClient(), stream)
    applied, deadline = 0, time.monotonic() + 30
    for event in books.events():
        assert not (isinstance(event, BookEvent) and event.kind == "gap"), event
        if isinstance(event, DepthDiff):
            book = books.book("BTCUSDT")
            assert book.best_bid.price < book.best_ask.price
            applied += 1
        if applied >= 10 or time.monotonic() > deadline:
            stream.stop()
            break
    assert applied >= 10
