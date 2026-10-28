"""Recorder: trades, 1 s book samples and gap log from a fake feed; `ttp record`."""

import json
import os
import threading
import time
from datetime import UTC, datetime

import httpx
import pandas as pd
import pytest
from click.testing import CliRunner

from ttp.cli import main
from ttp.core import BookLevel, BookSnapshot
from ttp.data.datasets import (
    Approval,
    DatasetDefinition,
    DatasetMarket,
    save_definition,
)
from ttp.data.recorder import (
    MARKETS_PER_CONNECTION,
    STALE_AFTER_S,
    Recorder,
    Session,
    connection_groups,
    read_status,
    request_stop,
)
from ttp.data.store import BOOK_1S, GAPS, TRADES, DatasetStore
from ttp.feeds import ReplayFeed
from ttp.venues.mexc import (
    DepthDiff,
    Level,
    LiveBooks,
    MexcClient,
    StreamStatus,
    Trade,
)

from .test_mexc_stream import ADX, DepthServer, FakeSocket, Sockets, frames, stream_with

T0 = 1_793_176_200.0  # 2026-10-28 08:30:00 UTC
MS = 1000


def ts(seconds: float) -> pd.Timestamp:
    return pd.Timestamp(round(seconds * MS), unit="ms", tz="UTC")


def snapshot(version: int, bids=(("0.0560", "10"),), asks=(("0.0570", "5"),)):
    return {"lastUpdateId": version, "bids": list(bids), "asks": list(asks)}


def diff(market, frm, to, bids=(), asks=(), t=T0):
    return DepthDiff(
        market,
        frm,
        to,
        tuple(Level(*b) for b in bids),
        tuple(Level(*a) for a in asks),
        int(t * MS),
    )


class HoldingSocket(FakeSocket):
    """Replays its frames, then idles (recv timeouts) instead of closing."""

    def recv(self, timeout=None):
        if not self.items:
            time.sleep(0.02)
            raise TimeoutError
        return super().recv(timeout)


class ScriptedStream:
    """A connection's message source: yields the script, then waits for `stop()`."""

    def __init__(self, script, hold: bool = True) -> None:
        self.script = script
        self.hold = hold
        self.stopped = threading.Event()

    def stop(self) -> None:
        self.stopped.set()

    def messages(self):
        for message in self.script:
            if self.stopped.is_set():
                return
            yield message
        while self.hold and not self.stopped.wait(0.02):
            pass


def client_with(*snapshots) -> MexcClient:
    return MexcClient(transport=httpx.MockTransport(DepthServer(list(snapshots))))


def feed_session(session: Session, books: LiveBooks, clock) -> list:
    events = []
    for event in books.events():
        session.on_event(event, books, clock())
        events.append(event)
    return events


def write_all(session: Session, store: DatasetStore, dataset="fx") -> None:
    for market, data_type, rows in session.take():
        store.append(dataset, "mexc", market, data_type, rows)


def test_session_buffers_trades_book_samples_and_gap_log(tmp_path):
    script = [
        StreamStatus("subscribed", int(T0 * MS)),
        diff("ADXUSDT", 101, 101, bids=[(0.0561, 1.0), (0.0559, 3.0)], t=T0 + 0.2),
        Trade("ADXUSDT", 0.057, 12.5, "buy", int((T0 + 0.5) * MS), "t1"),
        Trade("ADXUSDT", 0.056, 7.0, "sell", int((T0 + 0.75) * MS), "t2"),
        diff("ADXUSDT", 110, 110, asks=[(0.0570, 4.0)], t=T0 + 1.2),  # gap 102..109
        diff("ADXUSDT", 111, 111, asks=[(0.0571, 9.0)], t=T0 + 1.3),
    ]
    books = LiveBooks(
        ["ADXUSDT"],
        client_with(snapshot(100), snapshot(109)),
        ScriptedStream(script, hold=False),
    )
    session = Session("fx", ["ADXUSDT"], alert_after_s=60)
    session.start(T0 - 2)
    assert session.synced == []
    events = feed_session(session, books, lambda: T0)
    assert session.synced == ["ADXUSDT"]
    assert session.sample(int(T0) + 2) == 1
    session.stop(T0 + 3)
    assert session.buffered == {"trades": 2, "book_1s": 1, "gaps": 6}

    store = DatasetStore(tmp_path)
    write_all(session, store)

    trades = store.read("fx", "mexc", "ADXUSDT", TRADES)
    assert trades["price"].tolist() == [0.057, 0.056]
    assert trades["side"].tolist() == ["buy", "sell"]
    assert trades["time"].iloc[0] == ts(T0 + 0.5)

    book = store.read("fx", "mexc", "ADXUSDT", BOOK_1S)
    assert len(book) == 1 and book.shape[1] == 82
    row = book.iloc[0]
    assert row["time"] == ts(int(T0) + 2)
    assert row["version"] == 111
    assert (row["bid_price_1"], row["bid_qty_1"]) == (0.0560, 10.0)  # from snapshot 109
    assert (row["ask_price_1"], row["ask_qty_1"]) == (0.0570, 4.0)
    assert (row["ask_price_2"], row["ask_qty_2"]) == (0.0571, 9.0)
    assert pd.isna(row["bid_price_2"]) and pd.isna(row["ask_price_3"])

    gaps = store.read("fx", "mexc", "ADXUSDT", GAPS)
    assert gaps["kind"].tolist() == [
        "start",
        "missing",
        "synced",
        "gap",
        "synced",
        "stop",
    ]
    first_sync = gaps.iloc[2]
    assert first_sync["time"] == pd.Timestamp(
        T0, unit="s", tz="UTC"
    )  # stamped by clock
    missing = gaps.iloc[1]
    assert missing["time"] == ts(T0 - 2)
    assert missing["until"] == first_sync["time"]
    assert missing["detail"] == "2.0 s without a synced book"
    gap = gaps.iloc[3]
    assert gap["time"] == ts(T0 + 1.2)  # venue time
    assert gap["detail"] == "expected version 102, got 110"
    assert pd.isna(gap["until"])
    # The gap resynced within the same diff, so no `missing` interval opened.
    assert len(events) == 9


def test_unsynced_markets_are_not_sampled_and_stop_closes_missing_interval():
    script = [
        StreamStatus("subscribed", int(T0 * MS)),
        diff("AUSDT", 101, 101, bids=[(1.0, 1.0)]),
        StreamStatus("disconnected", int((T0 + 5) * MS), "ConnectionClosedError"),
    ]
    books = LiveBooks(
        ["AUSDT", "BUSDT"],
        client_with(snapshot(100), 429),
        ScriptedStream(script, hold=False),
    )
    session = Session("fx", ["AUSDT", "BUSDT"], alert_after_s=60)
    session.start(T0 - 1)
    feed_session(session, books, lambda: T0)
    assert session.synced == []  # both forgotten on disconnect
    assert session.sample(int(T0) + 6) == 0
    session.stop(T0 + 9)
    rows = {m: df for m, t, df in session.take() if t is GAPS}
    assert rows["AUSDT"]["kind"].tolist() == [
        "start",
        "missing",
        "synced",
        "disconnected",
        "missing",
        "stop",
    ]
    assert rows["AUSDT"]["until"].iloc[4] == ts(T0 + 9)
    assert rows["BUSDT"]["kind"].tolist() == [
        "start",
        "snapshot_failed",
        "disconnected",
        "missing",
        "stop",
    ]
    assert rows["BUSDT"]["time"].iloc[3] == ts(T0 - 1)


def test_alerts_once_per_outage_and_on_recovery():
    session = Session("fx", ["AUSDT", "BUSDT"], alert_after_s=120)
    session.start(T0)
    assert session.alerts(T0 + 119) == []
    assert session.alerts(T0 + 120) == [
        "recorder 'fx': 2 of 2 markets without a synced book for over 120 s: AUSDT, BUSDT"
    ]
    assert session.alerts(T0 + 500) == []  # not repeated
    books = LiveBooks(
        ["AUSDT"],
        client_with(snapshot(100)),
        ScriptedStream([StreamStatus("subscribed", int((T0 + 600) * MS))], hold=False),
    )
    feed_session(session, books, lambda: T0 + 600)
    assert session.alerts(T0 + 601) == ["recorder 'fx': synced again: AUSDT"]
    assert session.alerts(T0 + 602) == []


def test_markets_spread_over_connections_of_fifteen(tmp_path):
    markets = [f"M{i}USDT" for i in range(31)]
    assert [len(g) for g in connection_groups(markets)] == [15, 15, 1]
    assert MARKETS_PER_CONNECTION == 15
    made = []

    def factory(group):
        made.append(group)
        return ScriptedStream([])

    recorder = Recorder(
        DatasetStore(tmp_path),
        "fx",
        "mexc",
        markets,
        client_with(),
        stream_factory=factory,
    )
    assert len(recorder.connections) == 3 and made == connection_groups(markets)


def test_recorder_runs_threads_flushes_hourly_parts_and_cleans_up(tmp_path):
    """Real threads, real clock, a fake socket replaying the captured ADX session."""
    socket = HoldingSocket(frames(ADX))
    stream = stream_with(Sockets(socket), sleep=lambda s: time.sleep(0.01))
    store = DatasetStore(tmp_path)
    log: list[str] = []
    recorder = Recorder(
        store,
        "fx",
        "mexc",
        ["ADXUSDT"],
        client_with(),
        stream_factory=lambda group: stream,
        log=log.append,
        flush_interval_s=1.0,
        heartbeat_s=1.0,
    )
    recorder.run(seconds=1.6)

    assert not recorder.run_path.exists()
    assert recorder.written["gaps"] >= 4  # start, missing, synced, ..., stop
    assert recorder.written["book_1s"] >= 1  # at least one whole second passed
    assert recorder.flushes >= 2  # in the loop and on stop
    hour = datetime.now(UTC).strftime("%H")
    parts = sorted(p.name for p in tmp_path.glob("fx/**/*.parquet"))
    assert parts and set(parts) <= {
        f"part-{hour}.parquet",
        f"part-{int(hour) - 1:02d}.parquet",
    }
    gaps = store.read("fx", "mexc", "ADXUSDT", GAPS)
    assert gaps["kind"].tolist() == ["start", "missing", "synced", "stop"]
    assert gaps["until"].iloc[1] == gaps["time"].iloc[2]
    book = store.read("fx", "mexc", "ADXUSDT", BOOK_1S)
    assert book["bid_price_1"].notna().all()
    assert (book["bid_price_1"] < book["ask_price_1"]).all()
    assert any(line.startswith("flushed:") for line in log)
    assert any("synced version 54004657" in line for line in log)


def test_stop_file_stops_a_running_recorder(tmp_path):
    store = DatasetStore(tmp_path)
    recorder = Recorder(
        store,
        "fx",
        "mexc",
        ["ADXUSDT"],
        client_with(),
        stream_factory=lambda group: ScriptedStream([]),
        heartbeat_s=0.1,
    )
    thread = threading.Thread(target=recorder.run, daemon=True)
    thread.start()
    deadline = time.monotonic() + 5
    while not recorder.run_path.exists() and time.monotonic() < deadline:
        time.sleep(0.02)
    status = read_status(store, time.time())
    assert [s.dataset for s in status] == ["fx"] and not status[0].stale
    assert status[0].markets == 1 and status[0].synced == 0

    assert request_stop(store, "fx", timeout_s=5) == "stopped"
    thread.join(5)
    assert not thread.is_alive()
    assert not recorder.run_path.exists() and not recorder.stop_path.exists()
    assert request_stop(store, "fx") == "not running"


def test_stale_run_file_is_cleared(tmp_path):
    store = DatasetStore(tmp_path)
    path = store.dataset_dir("fx") / "recorder.json"
    path.parent.mkdir(parents=True)
    started = datetime.fromtimestamp(T0, UTC).isoformat()
    path.write_text(
        json.dumps(
            {
                "dataset": "fx",
                "pid": 4242,
                "started": started,
                "updated": started,
                "markets": ["AUSDT"],
                "connections": 1,
                "synced": [],
                "written": {},
                "flushes": 0,
            }
        )
    )
    status = read_status(store, T0 + STALE_AFTER_S + 1)[0]
    assert status.stale and status.pid == 4242
    assert request_stop(store, "fx", now=lambda: T0 + STALE_AFTER_S + 1) == "cleared"
    assert not path.exists()


def test_book_1s_replays_as_book_snapshots(tmp_path):
    store = DatasetStore(tmp_path)
    session = Session("fx", ["ADXUSDT"])
    books = LiveBooks(
        ["ADXUSDT"],
        client_with(snapshot(100, bids=[("0.0560", "10"), ("0.0559", "20")], asks=[])),
        ScriptedStream([StreamStatus("subscribed", int(T0 * MS))], hold=False),
    )
    feed_session(session, books, lambda: T0)
    session.sample(int(T0) + 1)
    session.sample(int(T0) + 2)
    write_all(session, store)

    events = list(ReplayFeed(store, "fx", data_types={"book_1s"}).events())
    assert len(events) == 2 and all(isinstance(e, BookSnapshot) for e in events)
    first = events[0]
    assert first.time == datetime.fromtimestamp(int(T0) + 1, UTC)
    assert first.market.symbol == "ADXUSDT" and first.market.venue == "mexc"
    assert first.bids == (BookLevel(0.056, 10.0), BookLevel(0.0559, 20.0))
    assert first.asks == () and first.best_ask is None
    # The gap log is stored but is not a market event.
    assert list(ReplayFeed(store, "fx", data_types={"gaps"}).events()) == []
    assert len(store.read("fx", "mexc", "ADXUSDT", GAPS)) == 1


def test_append_merges_within_the_hour_and_reads_with_day_files(tmp_path):
    store = DatasetStore(tmp_path)
    t = pd.Timestamp("2026-10-28 09:59:59", tz="UTC")

    def trades(*times):
        return pd.DataFrame(
            {"time": list(times), "price": 1.0, "quantity": 2.0, "side": "buy"}
        )

    assert store.write("fx", "mexc", "X", TRADES, trades(t)) == 1  # a download
    assert store.append("fx", "mexc", "X", TRADES, trades(t + pd.Timedelta("1s"))) == 1
    assert store.append("fx", "mexc", "X", TRADES, trades(t + pd.Timedelta("1s"))) == 0
    assert store.append("fx", "mexc", "X", TRADES, trades(t + pd.Timedelta("2s"))) == 1
    names = sorted(p.name for p in tmp_path.glob("fx/**/*.parquet"))
    assert names == ["data.parquet", "part-10.parquet"]
    assert len(store.read("fx", "mexc", "X", TRADES)) == 3


# -- CLI ---------------------------------------------------------------------


def approved(store: DatasetStore, name="fx", markets=("ADXUSDT",)) -> None:
    d = DatasetDefinition(name)
    d.approvals.append(Approval(1, "2026-10-28T08:00:00+00:00", "s", 0, 2.0, 0, "abc"))
    for m in markets:
        d.markets.append(DatasetMarket(m, "candidate", m, 1, "s", 1.0, 5, 1.0, 1.0))
    save_definition(store, d)


def test_record_start_runs_for_seconds_and_reports(tmp_path):
    store = DatasetStore(tmp_path)
    approved(store)
    socket = HoldingSocket(frames(ADX))
    stream = stream_with(Sockets(socket), sleep=lambda s: time.sleep(0.01))
    result = CliRunner().invoke(
        main,
        ["record", "start", "fx", "--seconds", "1.2", "--flush-interval", "1"],
        obj={
            "data_root": tmp_path,
            "mexc": client_with(),
            "stream": lambda group: stream,
            "env": {},
            "env_file": None,
        },
        prog_name="ttp",
    )
    assert result.exit_code == 0, result.output
    lines = result.output.splitlines()
    assert (
        f"recording dataset 'fx': 1 market over 1 connection -> {tmp_path.as_posix()}/fx"
    ) in lines
    assert "warning: Telegram alerts off" in result.output
    assert any("ADXUSDT synced version 54004657" in line for line in lines)
    assert lines[-1].startswith("stopped; rows written: trades ")
    assert store.series("fx")  # something stored
    assert not (tmp_path / "fx" / "recorder.json").exists()


def test_record_start_refuses_unknown_or_running_dataset(tmp_path):
    store = DatasetStore(tmp_path)
    runner = CliRunner()
    result = runner.invoke(
        main, ["record", "start", "nope"], obj={"data_root": tmp_path}, prog_name="ttp"
    )
    assert result.exit_code == 1 and "no approved dataset 'nope'" in result.output
    approved(store)
    recorder = Recorder(
        store,
        "fx",
        "mexc",
        ["ADXUSDT"],
        client_with(),
        stream_factory=lambda g: ScriptedStream([]),
    )
    recorder._started = time.time()
    recorder._write_run_file()
    result = runner.invoke(
        main, ["record", "start", "fx"], obj={"data_root": tmp_path}, prog_name="ttp"
    )
    assert result.exit_code == 1 and "already being recorded" in result.output


def test_record_status_and_stop_commands(tmp_path):
    store = DatasetStore(tmp_path)
    runner = CliRunner()
    result = runner.invoke(
        main, ["record", "status"], obj={"data_root": tmp_path}, prog_name="ttp"
    )
    assert result.output == "no recorder running\n"

    recorder = Recorder(
        store, "fx", "mexc", ["ADXUSDT", "BTCUSDT"], client_with(),
        stream_factory=lambda g: ScriptedStream([]), clock=lambda: T0,
    )  # fmt: skip
    recorder.written.update({"trades": 12, "book_1s": 3600})
    recorder._started = T0
    recorder._write_run_file()
    result = runner.invoke(
        main,
        ["record", "status"],
        obj={"data_root": tmp_path, "clock": lambda: T0 + 5},
        prog_name="ttp",
    )
    assert result.exit_code == 0, result.output
    lines = result.output.splitlines()
    assert lines[0].startswith("DATASET")
    assert lines[1].split() == [
        "fx", "running", str(os.getpid()),
        "0/2", "1", "12", "3,600", "0", "2026-10-28", "08:30:00",
    ]  # fmt: skip

    result = runner.invoke(
        main,
        ["record", "status"],
        obj={"data_root": tmp_path, "clock": lambda: T0 + 100},
        prog_name="ttp",
    )
    assert "stale 100s" in result.output and "probably gone" in result.output

    # stop: a live recorder sees the stop file and removes both files while we wait
    def exit_recorder(seconds: float) -> None:
        assert recorder.stop_path.exists()
        recorder.run_path.unlink()
        recorder.stop_path.unlink()

    result = runner.invoke(
        main,
        ["record", "stop", "fx"],
        obj={"data_root": tmp_path, "clock": lambda: T0 + 5, "sleep": exit_recorder},
        prog_name="ttp",
    )
    assert result.output == "dataset 'fx': recording stopped\n", result.output
    assert not recorder.stop_path.exists()

    result = runner.invoke(
        main, ["record", "stop", "fx"], obj={"data_root": tmp_path}, prog_name="ttp"
    )
    assert result.output == "dataset 'fx' is not being recorded\n"

    recorder._write_run_file()
    result = runner.invoke(
        main,
        ["record", "stop", "fx"],
        obj={"data_root": tmp_path, "clock": lambda: T0 + 100},
        prog_name="ttp",
    )
    assert "cleared the stale run file" in result.output


def test_record_stop_times_out(tmp_path):
    store = DatasetStore(tmp_path)
    recorder = Recorder(
        store, "fx", "mexc", ["ADXUSDT"], client_with(),
        stream_factory=lambda g: ScriptedStream([]), clock=lambda: T0,
    )  # fmt: skip
    recorder._started = T0
    recorder._write_run_file()
    ticks = iter([T0, T0, T0 + 1, T0 + 2, T0 + 31])
    result = CliRunner().invoke(
        main,
        ["record", "stop", "fx", "--timeout", "30"],
        obj={
            "data_root": tmp_path,
            "clock": lambda: next(ticks),
            "sleep": lambda s: None,
        },
        prog_name="ttp",
    )
    assert result.exit_code == 1 and "did not exit within 30 s" in result.output
    assert recorder.stop_path.exists()


@pytest.mark.live
def test_live_record_one_market_for_a_minute(tmp_path):
    """Opt-in: record BTCUSDT for 60 s against the real feed and check the output."""
    store = DatasetStore(tmp_path)
    approved(store, markets=("BTCUSDT",))
    result = CliRunner().invoke(
        main,
        ["record", "start", "fx", "--seconds", "60", "--flush-interval", "20"],
        obj={"data_root": tmp_path, "env": {}, "env_file": None},
        prog_name="ttp",
    )
    assert result.exit_code == 0, result.output
    book = store.read("fx", "mexc", "BTCUSDT", BOOK_1S)
    assert len(book) >= 50 and (book["bid_price_1"] < book["ask_price_1"]).all()
    assert book["bid_price_20"].notna().all()  # BTC has depth
    assert len(store.read("fx", "mexc", "BTCUSDT", TRADES)) > 0
    gaps = store.read("fx", "mexc", "BTCUSDT", GAPS)
    assert gaps["kind"].tolist()[:3] == ["start", "missing", "synced"]
    assert gaps["kind"].iloc[-1] == "stop"
    assert store.gaps("fx", "mexc", "BTCUSDT", BOOK_1S) == []
