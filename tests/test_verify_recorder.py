"""Verifier (ticket 11): recorder `Session` from a scripted feed (ticket 08).

The feed is a real `LiveBooks` over a scripted message source and a fake
snapshot client, so book sync, the gap log and 1 s samples are exercised
together without threads or network.
"""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pandas as pd
import pytest

from ttp.data.recorder import Session
from ttp.data.store import BOOK_1S, BOOK_DEPTH, GAPS, DatasetStore
from ttp.venues.mexc import (
    BookEvent,
    BookSnapshot,
    BookSync,
    DepthDiff,
    Level,
    LiveBooks,
    StreamStatus,
)

M = "ADXUSDT"
T0 = 1_793_176_200.0  # 2026-10-28 08:30:00 UTC


def ms(t: float) -> int:
    return round(t * 1000)


def ts(t: float) -> pd.Timestamp:
    return pd.Timestamp(ms(t), unit="ms", tz="UTC")


def deep_snapshot(version: int, levels: int = 25) -> BookSnapshot:
    bids = tuple(Level(round(1.0 - 0.01 * i, 4), 1.0 + i) for i in range(levels))
    asks = tuple(Level(round(1.1 + 0.01 * i, 4), 2.0 + i) for i in range(levels))
    return BookSnapshot(M, version, bids, asks)


class FakeClient:
    def __init__(self, *snapshots: BookSnapshot) -> None:
        self.snapshots = list(snapshots)

    def depth(self, market: str) -> BookSnapshot:
        return self.snapshots.pop(0)


class Script:
    def __init__(self, messages) -> None:
        self.messages_ = list(messages)

    def messages(self):
        yield from self.messages_


def diff(frm, to, t, bids=(), asks=()):
    return DepthDiff(
        M,
        frm,
        to,
        tuple(Level(*b) for b in bids),
        tuple(Level(*a) for a in asks),
        ms(t),
    )


def run(session: Session, books: LiveBooks, now: float, sample_after=None) -> None:
    """Feed every event; `sample_after` maps an event index to a sample second."""
    for i, event in enumerate(books.events()):
        session.on_event(event, books, now)
        if sample_after and i in sample_after:
            session.sample(sample_after[i])


def frames(session: Session) -> dict[str, pd.DataFrame]:
    return {dt.name: rows for _, dt, rows in session.take()}


def test_samples_are_top_20_best_first_with_the_version_they_were_taken_at():
    script = [
        StreamStatus("subscribed", ms(T0)),  # -> snapshot v100, synced
        diff(101, 101, T0 + 0.4, bids=[(1.0, 0.0), (1.005, 7.0)]),
        diff(102, 103, T0 + 1.4, asks=[(1.1, 0.0)]),
    ]
    books = LiveBooks([M], FakeClient(deep_snapshot(100)), Script(script))
    session = Session("v", [M])
    session.start(T0 - 1)
    # events: subscribed, synced, diff101, diff102
    run(session, books, T0, sample_after={2: int(T0) + 1, 3: int(T0) + 2})
    book = frames(session)["book_1s"]
    assert list(book.columns) == list(BOOK_1S.columns)
    assert len(BOOK_1S.columns) == 2 + 4 * BOOK_DEPTH
    assert list(book["version"]) == [101, 103]
    first, second = book.iloc[0], book.iloc[1]
    bids = [first[f"bid_price_{i}"] for i in range(1, BOOK_DEPTH + 1)]
    assert bids[0] == 1.005 and bids == sorted(bids, reverse=True)
    assert bids[1] == 0.99  # 1.0 was removed by the diff
    asks = [second[f"ask_price_{i}"] for i in range(1, BOOK_DEPTH + 1)]
    assert asks[0] == 1.11 and asks == sorted(asks)  # 1.1 removed
    assert all(first[f"bid_price_{i}"] < first[f"ask_price_{i}"] for i in (1,))
    assert list(book["time"]) == [ts(int(T0) + 1), ts(int(T0) + 2)]


def test_thin_book_levels_are_null_in_storage(tmp_path):
    thin = BookSnapshot(M, 5, (Level(1.0, 1.0),), (Level(1.1, 1.0), Level(1.2, 2.0)))
    books = LiveBooks([M], FakeClient(thin), Script([StreamStatus("subscribed", 0)]))
    session = Session("v", [M])
    run(session, books, T0)
    assert session.sample(int(T0)) == 1
    store = DatasetStore(tmp_path)
    for market, dt, rows in session.take():
        store.append("v", "mexc", market, dt, rows)
    row = store.read("v", "mexc", M, BOOK_1S).iloc[0]
    assert row["version"] == 5
    assert (row["bid_price_1"], row["ask_price_2"]) == (1.0, 1.2)
    assert pd.isna(row["bid_price_2"]) and pd.isna(row["ask_qty_3"])
    assert pd.isna(row[f"ask_price_{BOOK_DEPTH}"])


def test_gap_log_records_missing_synced_gap_and_stop_with_intervals():
    script = [
        StreamStatus("subscribed", ms(T0)),  # snapshot v100 -> synced (no venue time)
        diff(101, 101, T0 + 5),
        diff(105, 105, T0 + 10),  # gap -> snapshot v99 is stale
        diff(106, 106, T0 + 20),  # -> snapshot v105 -> synced at the diff's time
    ]
    client = FakeClient(deep_snapshot(100), deep_snapshot(99), deep_snapshot(105))
    books = LiveBooks([M], client, Script(script))
    session = Session("v", [M])
    session.start(T0 - 5)
    unsynced_samples = []
    for event in books.events():
        session.on_event(event, books, T0)
        if isinstance(event, BookEvent) and event.kind == "stale_snapshot":
            unsynced_samples.append(session.sample(int(T0) + 15))
    session.stop(T0 + 30)
    gaps = frames(session)["gaps"]
    got = [(r.kind, r.time, r.until) for r in gaps.itertuples()]
    nat = None
    assert [(k, t, None if pd.isna(u) else u) for k, t, u in got] == [
        ("start", ts(T0 - 5), nat),
        ("missing", ts(T0 - 5), ts(T0)),
        ("synced", ts(T0), nat),
        ("gap", ts(T0 + 10), nat),
        ("stale_snapshot", ts(T0 + 10), nat),
        ("missing", ts(T0 + 10), ts(T0 + 20)),
        ("synced", ts(T0 + 20), nat),
        ("stop", ts(T0 + 30), nat),
    ]
    assert unsynced_samples == [0]  # nothing sampled while the book is not synced
    assert session.synced == [M]


def test_disconnect_opens_missing_interval_closed_at_stop(tmp_path):
    script = [
        StreamStatus("subscribed", ms(T0)),
        StreamStatus("disconnected", ms(T0 + 3), "OSError: reset"),
    ]
    books = LiveBooks([M], FakeClient(deep_snapshot(100)), Script(script))
    session = Session("v", [M])
    session.start(T0)
    run(session, books, T0)
    assert session.synced == [] and session.sample(int(T0) + 4) == 0
    session.stop(T0 + 9)
    store = DatasetStore(tmp_path)
    for market, dt, rows in session.take():
        store.append("v", "mexc", market, dt, rows)
    gaps = store.read("v", "mexc", M, GAPS)
    kinds = set(gaps["kind"])
    assert {"start", "synced", "disconnected", "missing", "stop"} <= kinds
    last_missing = gaps[gaps["kind"] == "missing"].sort_values("time").iloc[-1]
    assert (last_missing["time"], last_missing["until"]) == (ts(T0 + 3), ts(T0 + 9))
    assert str(gaps["until"].dt.tz) == "UTC"


# -- alerts ------------------------------------------------------------------


def fake_books(markets):
    syncs = {m: BookSync(m) for m in markets}
    return SimpleNamespace(syncs=syncs, book=lambda m: syncs[m].book)


def sync(books, market, version=1):
    events = books.syncs[market].on_snapshot(
        BookSnapshot(market, version, (Level(1.0, 1.0),), (Level(1.1, 1.0),))
    )
    return events[0]


def test_alert_once_per_outage_once_on_recovery_and_again_on_a_new_outage():
    books = fake_books(["A", "B"])
    s = Session("v", ["A", "B"], alert_after_s=60)
    s.start(T0)
    assert s.alerts(T0 + 59) == []
    first = s.alerts(T0 + 60)
    assert len(first) == 1 and "A, B" in first[0]
    assert s.alerts(T0 + 61) == [] and s.alerts(T0 + 600) == []
    s.on_event(sync(books, "A"), books, T0 + 700)
    recovered = s.alerts(T0 + 701)
    assert len(recovered) == 1 and "synced again: A" in recovered[0]
    assert s.alerts(T0 + 702) == []  # B still down: no repeat
    s.on_event(BookEvent("A", "disconnected", None, "x"), books, T0 + 800)
    assert s.alerts(T0 + 859) == []
    again = s.alerts(T0 + 860)
    assert len(again) == 1 and ": A" in again[0] and "B" not in again[0]


def test_market_that_syncs_before_the_threshold_never_alerts():
    books = fake_books(["A"])
    s = Session("v", ["A"], alert_after_s=60)
    s.start(T0)
    s.on_event(sync(books, "A"), books, T0 + 30)
    assert s.alerts(T0 + 61) == [] and s.alerts(T0 + 1000) == []


# -- hourly part files ---------------------------------------------------------


def book_rows(times):
    rows = []
    for i, t in enumerate(times):
        row = {c: None for c in BOOK_1S.columns}
        row.update(time=t, version=i, bid_price_1=1.0, ask_price_1=1.1)
        rows.append(row)
    return pd.DataFrame(rows, columns=list(BOOK_1S.columns))


def test_hourly_parts_split_at_hour_and_date_and_re_flush_does_not_duplicate(tmp_path):
    store = DatasetStore(tmp_path)
    t = datetime(2026, 10, 28, 23, 59, 58, tzinfo=UTC)
    times = [t + timedelta(seconds=i) for i in range(4)]  # 23:59:58 .. 00:00:01
    assert store.append("v", "mexc", M, BOOK_1S, book_rows(times[:3])) == 3
    # Re-flush overlapping rows plus one new: only the new one is added.
    assert store.append("v", "mexc", M, BOOK_1S, book_rows(times)) == 1
    base = store.series_dir("v", "mexc", M, BOOK_1S)
    files = sorted(p.relative_to(base).as_posix() for p in base.rglob("*.parquet"))
    assert files == [
        "date=2026-10-28/part-23.parquet",
        "date=2026-10-29/part-00.parquet",
    ]
    got = store.read("v", "mexc", M, BOOK_1S)
    assert list(got["time"]) == [pd.Timestamp(x) for x in times]
    assert store.gaps("v", "mexc", M, BOOK_1S) == []


@pytest.mark.parametrize("flushes", [1, 3])
def test_session_flushes_merge_into_the_same_hour_file(tmp_path, flushes):
    books = fake_books([M])
    store = DatasetStore(tmp_path)
    s = Session("v", [M])
    s.start(T0)
    s.on_event(sync(books, M, version=9), books, T0)
    for k in range(6):
        s.sample(int(T0) + k)
        if k % (6 // flushes) == (6 // flushes) - 1:
            for market, dt, rows in s.take():
                store.append("v", "mexc", market, dt, rows)
    book = store.read("v", "mexc", M, BOOK_1S)
    assert len(book) == 6 and book["time"].is_unique
    assert set(book["version"]) == {9}
    base = store.series_dir("v", "mexc", M, BOOK_1S)
    assert len(list(base.rglob("*.parquet"))) == 1
