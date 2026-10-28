"""Verifier (ticket 11): MEXC book sync rules on hand-built diffs (ticket 07).

Rules (book.py docstring, MEXC spot v3 docs): drop diffs with toVersion <=
lastUpdateId; the first remaining diff must have fromVersion <= lastUpdateId + 1;
later diffs must chain (fromVersion == previous toVersion + 1); anything else is
a gap and needs a new snapshot. Quantities are absolute; 0 removes a level.

The property test drives `BookSync` from a simulated venue whose book is never
crossed, delivering its diffs with drops, duplicates and swaps, and checks that
whenever the local book claims to be synced it equals the venue's book at that
version (and so is never crossed).
"""

import random

import pytest

from ttp.venues.mexc import BookSnapshot, BookSync, DepthDiff, Level

M = "ADXUSDT"


def lv(*pairs):
    return tuple(Level(p, q) for p, q in pairs)


def snap(version, bids=((1.00, 5.0),), asks=((1.10, 5.0),)):
    return BookSnapshot(M, version, lv(*bids), lv(*asks))


def d(frm, to, bids=(), asks=(), t=0):
    return DepthDiff(M, frm, to, lv(*bids), lv(*asks), t)


def synced_at(version, **kw) -> BookSync:
    s = BookSync(M)
    events = s.on_snapshot(snap(version, **kw))
    assert [e.kind for e in events] == ["synced"]
    return s


def test_stale_diff_after_sync_is_dropped_and_changes_nothing():
    s = synced_at(100)
    assert s.on_diff(d(95, 100, bids=[(1.00, 99.0)])) == []
    assert s.book.bids() == [Level(1.00, 5.0)]
    assert s.version == 100 and s.synced


def test_first_buffered_diff_bridging_the_snapshot_is_applied():
    s = BookSync(M)
    s.on_diff(d(90, 98, bids=[(0.5, 1.0)]))  # fully older than the snapshot: dropped
    s.on_diff(d(99, 102, bids=[(1.01, 2.0)]))  # straddles 100 -> 101: bridges
    s.on_diff(d(103, 103, asks=[(1.10, 0.0)]))
    events = s.on_snapshot(snap(100))
    assert [e.kind for e in events] == ["synced"]
    assert s.version == 103
    assert s.book.bids() == [Level(1.01, 2.0), Level(1.00, 5.0)]
    assert s.book.asks() == []


def test_first_diff_exactly_at_snapshot_plus_one_bridges():
    s = BookSync(M)
    s.on_diff(d(101, 101, asks=[(1.05, 1.0)]))
    assert [e.kind for e in s.on_snapshot(snap(100))] == ["synced"]
    assert s.version == 101 and s.book.best_ask == Level(1.05, 1.0)


def test_first_diff_not_bridging_rejects_snapshot_and_keeps_buffer():
    s = BookSync(M)
    s.on_diff(d(102, 104, bids=[(1.02, 1.0)]))
    events = s.on_snapshot(snap(100))
    assert [e.kind for e in events] == ["stale_snapshot"]
    assert not s.synced and s.snapshot_wanted
    # A newer snapshot covering the buffered diff syncs and drops it.
    assert [e.kind for e in s.on_snapshot(snap(104))] == ["synced"]
    assert s.version == 104 and s.book.bids() == [Level(1.00, 5.0)]


def test_gap_after_sync_resyncs_and_replays_the_diff_that_revealed_it():
    s = synced_at(100)
    s.on_diff(d(101, 101, bids=[(1.01, 1.0)]))
    events = s.on_diff(d(103, 103, bids=[(1.02, 1.0)]))  # 102 missing
    assert [e.kind for e in events] == ["gap"]
    assert "102" in events[0].detail and "103" in events[0].detail
    assert s.book is None and s.snapshot_wanted
    # Further diffs while unsynced are buffered, not applied.
    assert s.on_diff(d(104, 104, asks=[(1.09, 1.0)])) == []
    events = s.on_snapshot(snap(102, bids=((1.01, 1.0), (1.00, 5.0))))
    assert [e.kind for e in events] == ["synced"]
    assert s.version == 104
    assert s.book.best_bid == Level(1.02, 1.0)
    assert s.book.best_ask == Level(1.09, 1.0)


def test_duplicate_and_late_diffs_never_roll_quantities_back():
    s = synced_at(100)
    s.on_diff(d(101, 101, bids=[(1.00, 7.0)]))
    s.on_diff(d(102, 102, bids=[(1.00, 9.0)]))
    assert s.on_diff(d(101, 101, bids=[(1.00, 7.0)])) == []  # late
    assert s.on_diff(d(102, 102, bids=[(1.00, 9.0)])) == []  # duplicate
    assert s.book.bids() == [Level(1.00, 9.0)] and s.version == 102


def test_swapped_diffs_cause_a_gap_not_a_wrong_book():
    s = synced_at(100)
    events = s.on_diff(d(102, 102, bids=[(1.00, 9.0)]))  # arrives before 101
    assert [e.kind for e in events] == ["gap"]
    s.on_diff(d(101, 101, bids=[(1.00, 7.0)]))
    assert not s.synced


def test_zero_quantity_removes_level_and_unknown_level_removal_is_harmless():
    s = synced_at(100)
    s.on_diff(d(101, 101, bids=[(1.00, 0.0), (0.90, 0.0)], asks=[(1.20, 3.0)]))
    assert s.book.bids() == [] and s.book.best_bid is None
    assert s.book.asks() == [Level(1.10, 5.0), Level(1.20, 3.0)]


def test_disconnect_then_old_snapshot_cannot_resurrect_the_book():
    s = synced_at(100)
    s.on_disconnect(1, "net")
    assert not s.synced and s.snapshot_wanted
    s.on_diff(d(205, 205))
    assert [e.kind for e in s.on_snapshot(snap(150))] == ["stale_snapshot"]
    assert not s.synced


# -- property: a simulated venue, perturbed delivery -------------------------


class Venue:
    """An uncrossed book on an integer tick grid that emits aggregated diffs."""

    def __init__(self, rng: random.Random) -> None:
        self.rng = rng
        self.bids = {100 - i: float(i + 1) for i in range(5)}
        self.asks = {101 + i: float(i + 1) for i in range(5)}
        self.version = 1000
        self.history = {self.version: self._state()}

    def _state(self):
        return dict(self.bids), dict(self.asks)

    def snapshot(self, version: int) -> BookSnapshot:
        bids, asks = self.history[version]
        return BookSnapshot(
            M,
            version,
            tuple(Level(p / 100, q) for p, q in sorted(bids.items(), reverse=True)),
            tuple(Level(p / 100, q) for p, q in sorted(asks.items())),
        )

    def step(self) -> DepthDiff:
        frm = self.version + 1
        changed_b: dict[int, float] = {}
        changed_a: dict[int, float] = {}
        for _ in range(self.rng.randint(1, 3)):
            self.version += 1
            self._one_change(changed_b, changed_a)
            self.history[self.version] = self._state()
        return DepthDiff(
            M,
            frm,
            self.version,
            tuple(Level(p / 100, q) for p, q in changed_b.items()),
            tuple(Level(p / 100, q) for p, q in changed_a.items()),
            self.version,
        )

    def _one_change(self, cb, ca):
        r = self.rng.random()
        max(self.bids, default=None)
        best_ask = min(self.asks, default=None)
        if r < 0.15 and best_ask is not None:
            # Aggressive buy limit through the best ask: eats asks up to its
            # price, the rest rests as the new best bid. Never crossed after.
            price = best_ask + self.rng.randint(0, 2)
            for p in [p for p in self.asks if p <= price]:
                del self.asks[p]
                ca[p] = 0.0
            self.bids[price] = 1.0
            cb[price] = 1.0
            return
        side, other, changed = (
            (self.bids, self.asks, cb) if r < 0.575 else (self.asks, self.bids, ca)
        )
        is_bid = side is self.bids
        if side and self.rng.random() < 0.35:
            p = self.rng.choice(sorted(side))
            del side[p]
            changed[p] = 0.0
            return
        if is_bid:
            hi = (min(other) - 1) if other else 120
            p = self.rng.randint(hi - 8, hi)
        else:
            lo = (max(other) + 1) if other else 80
            p = self.rng.randint(lo, lo + 8)
        q = float(self.rng.randint(1, 50))
        side[p] = q
        changed[p] = q


def _check(sync: BookSync, venue: Venue) -> None:
    if not sync.synced:
        return
    want = venue.snapshot(sync.version)
    assert sync.book.bids() == list(want.bids)
    assert sync.book.asks() == list(want.asks)
    bb, ba = sync.book.best_bid, sync.book.best_ask
    if bb and ba:
        assert bb.price < ba.price, f"crossed at version {sync.version}"


@pytest.mark.parametrize("seed", range(12))
def test_book_matches_venue_and_is_never_crossed_under_perturbed_delivery(seed):
    rng = random.Random(seed)
    venue = Venue(rng)
    sync = BookSync(M)
    held: DepthDiff | None = None
    last: DepthDiff | None = None
    kinds: list[str] = []
    synced_steps = 0
    for _ in range(400):
        diff = venue.step()
        r = rng.random()
        if r < 0.04:
            deliver = []  # lost
        elif r < 0.08 and held is None:
            held, deliver = diff, []  # delivered after the next one (swap)
        else:
            deliver = [diff]
            if held is not None:
                deliver.append(held)
                held = None
        if last is not None and rng.random() < 0.05:
            deliver.append(last)  # duplicate of an earlier push
        last = diff
        for item in deliver:
            kinds += [e.kind for e in sync.on_diff(item)]
            _check(sync, venue)
        if sync.snapshot_wanted:
            # Snapshots sometimes lag the stream a little, as REST does.
            version = max(1000, venue.version - rng.randint(0, 4))
            kinds += [e.kind for e in sync.on_snapshot(venue.snapshot(version))]
            _check(sync, venue)
        synced_steps += sync.synced
    assert "gap" in kinds and "synced" in kinds
    assert synced_steps > 200  # the scenario actually exercised a synced book
