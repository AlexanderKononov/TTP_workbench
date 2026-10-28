"""Book maintenance from depth diffs: application, ordering, gaps and resync. Pure, no network."""

from ttp.venues.mexc.book import (
    BookSnapshot,
    BookSync,
    DepthDiff,
    Level,
    OrderBook,
)

M = "ADXUSDT"


def diff(frm: int, to: int, bids=(), asks=(), t: int = 1000) -> DepthDiff:
    return DepthDiff(
        M, frm, to, tuple(Level(*b) for b in bids), tuple(Level(*a) for a in asks), t
    )


def snapshot(
    version: int, bids=((0.080, 100.0),), asks=((0.081, 200.0),)
) -> BookSnapshot:
    return BookSnapshot(
        M, version, tuple(Level(*b) for b in bids), tuple(Level(*a) for a in asks)
    )


def kinds(events) -> list[str]:
    return [e.kind for e in events]


def test_order_book_sorts_sides_and_removes_zero_levels():
    book = OrderBook(
        bids=(Level(0.080, 1), Level(0.082, 2), Level(0.081, 3)),
        asks=(Level(0.085, 1), Level(0.083, 2)),
    )
    assert [b.price for b in book.bids()] == [0.082, 0.081, 0.080]
    assert [a.price for a in book.asks()] == [0.083, 0.085]
    assert book.best_bid == Level(0.082, 2)
    assert book.best_ask == Level(0.083, 2)
    book.apply(bids=(Level(0.082, 0), Level(0.081, 9)), asks=(Level(0.084, 5),))
    assert book.bids(2) == [Level(0.081, 9), Level(0.080, 1)]
    assert book.asks() == [Level(0.083, 2), Level(0.084, 5), Level(0.085, 1)]
    assert len(book) == 5
    assert OrderBook().best_bid is None


def test_snapshot_then_contiguous_diffs_keep_book_in_sync():
    sync = BookSync(M)
    assert sync.snapshot_wanted and not sync.synced
    assert kinds(sync.on_snapshot(snapshot(100))) == ["synced"]
    assert not sync.snapshot_wanted
    assert sync.on_diff(diff(101, 103, bids=[(0.0805, 50)])) == []
    assert sync.on_diff(diff(104, 104, asks=[(0.081, 0)])) == []
    assert sync.version == 104
    assert sync.book.best_bid == Level(0.0805, 50)
    assert sync.book.asks() == []


def test_diffs_buffered_before_snapshot_are_replayed_and_stale_ones_dropped():
    sync = BookSync(M)
    sync.on_diff(diff(98, 99, bids=[(0.079, 1)]))  # covered by the snapshot: dropped
    sync.on_diff(diff(100, 101, bids=[(0.0801, 7)]))  # spans the snapshot: applied
    sync.on_diff(diff(102, 102, asks=[(0.0809, 3)]))
    events = sync.on_snapshot(snapshot(100))
    assert kinds(events) == ["synced"]
    assert "2 buffered diffs" in events[0].detail
    assert sync.version == 102
    assert sync.book.best_bid == Level(0.0801, 7)
    assert sync.book.best_ask == Level(0.0809, 3)
    assert sync.book.bids(5) == [Level(0.0801, 7), Level(0.080, 100)]


def test_duplicate_and_out_of_order_diffs_are_ignored():
    sync = BookSync(M)
    sync.on_snapshot(snapshot(100))
    sync.on_diff(diff(101, 102, bids=[(0.0802, 1)]))
    assert sync.on_diff(diff(101, 102, bids=[(0.0802, 999)])) == []  # replayed push
    assert (
        sync.on_diff(diff(99, 100, bids=[(0.0802, 999)])) == []
    )  # older than the book
    assert sync.version == 102
    assert sync.book.best_bid == Level(0.0802, 1)


def test_gap_drops_book_asks_for_snapshot_and_buffers_the_diff():
    sync = BookSync(M)
    sync.on_snapshot(snapshot(100))
    events = sync.on_diff(diff(105, 106, bids=[(0.0803, 4)], t=2000))
    assert kinds(events) == ["gap"]
    assert events[0].detail == "expected version 101, got 105"
    assert events[0].time_ms == 2000
    assert not sync.synced and sync.snapshot_wanted
    sync.on_diff(diff(107, 107, asks=[(0.0808, 2)]))
    events = sync.on_snapshot(snapshot(104))
    assert kinds(events) == ["synced"]
    assert sync.version == 107
    assert sync.book.best_bid == Level(0.0803, 4)
    assert sync.book.best_ask == Level(0.0808, 2)


def test_snapshot_behind_buffered_stream_is_rejected_until_a_newer_one_arrives():
    sync = BookSync(M)
    sync.on_diff(diff(110, 110, bids=[(0.0804, 1)]))
    events = sync.on_snapshot(snapshot(100))
    assert kinds(events) == ["stale_snapshot"]
    assert "snapshot version 100, stream resumes at 110" in events[0].detail
    assert not sync.synced and sync.snapshot_wanted
    assert kinds(sync.on_snapshot(snapshot(109))) == ["synced"]
    assert sync.version == 110
    assert sync.book.best_bid == Level(0.0804, 1)


def test_gap_inside_buffered_diffs_resyncs_from_the_gap():
    sync = BookSync(M)
    sync.on_diff(diff(101, 101, bids=[(0.0801, 1)]))
    sync.on_diff(diff(103, 103, bids=[(0.0802, 1)]))  # 102 missing
    sync.on_diff(diff(104, 104, bids=[(0.0803, 1)]))
    events = sync.on_snapshot(snapshot(100))
    assert kinds(events) == ["synced", "gap"]
    assert not sync.synced
    assert kinds(sync.on_snapshot(snapshot(102))) == ["synced"]
    assert sync.version == 104
    assert [b.price for b in sync.book.bids(2)] == [0.0803, 0.0802]


def test_disconnect_forgets_book_and_buffer():
    sync = BookSync(M)
    sync.on_snapshot(snapshot(100))
    sync.on_diff(diff(101, 101, bids=[(0.0801, 1)]))
    events = sync.on_disconnect(3000, "connection closed")
    assert kinds(events) == ["disconnected"]
    assert events[0].detail == "connection closed"
    assert not sync.synced and sync.snapshot_wanted and sync.version is None
    # After reconnecting, versions restart from the new snapshot.
    sync.on_diff(diff(501, 501, asks=[(0.0811, 1)]))
    assert kinds(sync.on_snapshot(snapshot(500))) == ["synced"]
    assert sync.version == 501
