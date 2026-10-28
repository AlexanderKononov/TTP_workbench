"""Verifier (ticket 11): dataset approval and control draw (ticket 06), store and
downloader (tickets 03/06): dedup on re-download, gap detection, UTC round trip.
"""

import random
from datetime import UTC, datetime, timedelta, timezone

import pandas as pd

from ttp.data.datasets import (
    CANDIDATE,
    CONTROL,
    DatasetDefinition,
    approve,
    select_controls,
)
from ttp.data.downloader import download_klines, download_trades
from ttp.data.store import KLINES_1M, TRADES, DatasetStore
from ttp.venues.mexc import AggTrade, Kline

NOW = datetime(2026, 10, 28, 12, 0, tzinfo=UTC)


def stats(n_quiet=60, seed=1, extra=()) -> pd.DataFrame:
    """Candidates C1..C4 (scored), quiet markets Q00.. spread over volumes 1k..1M."""
    rng = random.Random(seed)
    rows = [
        ("C1USDT", 0.9, 12, 50_000.0),
        ("C2USDT", 0.5, 8, 52_000.0),
        ("C3USDT", 0.3, 6, 48_000.0),
        ("C4USDT", 0.2, 5, 400_000.0),
        *extra,
    ]
    rows += [
        (f"Q{i:02d}USDT", 0.0, 0, round(10 ** rng.uniform(3, 6), 2))
        for i in range(n_quiet)
    ]
    return pd.DataFrame(
        [
            {"market": m, "score": s, "wick_count": e, "volume_24h": v, "candles": 1440}
            for m, s, e, v in rows
        ]
    )


def picks(table, candidates, seed=42, **kw):
    return {
        p.candidate: (p.control, p.band)
        for p in select_controls(table, candidates, seed, **kw)
    }


def test_draw_is_reproducible_under_shuffled_stats_rows():
    table = stats()
    want = picks(table, ["C1USDT", "C2USDT", "C4USDT"])
    for k in range(10):
        shuffled = table.sample(frac=1, random_state=k).reset_index(drop=True)
        assert picks(shuffled, ["C1USDT", "C2USDT", "C4USDT"]) == want


def test_draw_does_not_depend_on_candidate_order():
    # Ticket 15: C1 C2 C3 and C3 C2 C1 pair identically for every seed.
    table = stats()
    cands = ["C1USDT", "C2USDT", "C3USDT"]
    for seed in range(50):
        assert picks(table, cands, seed) == picks(table, cands[::-1], seed)


def test_earlier_controls_are_unchanged_by_later_approvals():
    table = stats()
    alone = DatasetDefinition("d")
    approve(alone, table, "s1", ["C1USDT"], NOW, 42, 2.0, 0, "abc")
    seq = DatasetDefinition("d")
    approve(seq, table, "s1", ["C1USDT"], NOW, 42, 2.0, 0, "abc")
    added = approve(seq, table, "s2", ["C2USDT", "C3USDT"], NOW, 42, 2.0, 0, "abc")
    assert seq.markets[:2] == alone.markets
    assert seq.version == 2 and {m.version for m in added} == {2}
    # Later controls avoid every market already in the dataset.
    first = {m.market for m in alone.markets}
    assert not first & {m.market for m in added if m.role == CONTROL}


def test_controls_are_pattern_free_in_band_and_never_candidates():
    table = stats(extra=[("C5USDT", 0.0, 0, 49_000.0)])  # a candidate with no events
    cands = ["C1USDT", "C2USDT", "C3USDT", "C5USDT"]
    for seed in range(30):
        for p in select_controls(table, cands, seed):
            row = table.set_index("market").loc[p.control]
            assert p.control not in cands
            assert row["wick_count"] == 0
            v = table.set_index("market").loc[p.candidate, "volume_24h"]
            assert v / p.band <= row["volume_24h"] <= v * p.band


def test_earlier_candidates_are_never_drawn_as_later_controls():
    # Earlier candidate E has no spike events (looks quiet) and sits in band.
    table = stats(
        n_quiet=0,
        extra=[
            ("EUSDT", 0.0, 0, 50_000.0),
            ("QXUSDT", 0.0, 0, 51_000.0),
            ("QYUSDT", 0.0, 0, 49_500.0),
        ],
    )
    d = DatasetDefinition("d")
    approve(d, table, "s1", ["EUSDT"], NOW, 1, 2.0, 0, "x")
    for seed in range(20):
        dd = DatasetDefinition.from_json(d.to_json())
        added = approve(dd, table, "s2", ["C1USDT"], NOW, seed, 2.0, 0, "x")
        control = next(m.market for m in added if m.role == CONTROL)
        assert control not in {"EUSDT", "C1USDT"}
        assert control not in {m.market for m in d.markets}


def test_band_widening_is_recorded_on_the_control():
    # Nearest quiet market is 3x the candidate's volume: x2 empty, x4 used.
    table = pd.DataFrame(
        [
            {
                "market": "CUSDT",
                "score": 1.0,
                "wick_count": 9,
                "volume_24h": 10_000.0,
                "candles": 1440,
            },
            {
                "market": "QUSDT",
                "score": 0.0,
                "wick_count": 0,
                "volume_24h": 30_000.0,
                "candles": 1440,
            },
        ]
    )
    d = DatasetDefinition("d")
    approve(d, table, "s", ["CUSDT"], NOW, 3, 2.0, 0, "x")
    by_role = {m.role: m for m in d.markets}
    assert by_role[CONTROL].market == "QUSDT" and by_role[CONTROL].band == 4.0
    assert by_role[CANDIDATE].band == 1.0
    assert d.approvals[-1].band == 2.0  # the requested band, not the widened one
    restored = DatasetDefinition.from_json(d.to_json())
    assert restored.markets == d.markets


# -- downloader and store -----------------------------------------------------

MIN_MS = 60_000


class Klines:
    """Venue stub: one 1 m kline per minute, returned with one extra minute either side."""

    def __init__(self, missing=()):
        self.calls = []
        self.missing = set(missing)

    def klines(self, symbol, start_ms, end_ms, interval="1m"):
        self.calls.append((start_ms, end_ms))
        out = []
        for t in range(start_ms - MIN_MS, end_ms + MIN_MS, MIN_MS):
            if t not in self.missing:
                out.append(Kline(t, 1.0, 1.1, 0.9, 1.0, 1.0, 1.0))
        return out


def test_re_download_adds_nothing_even_when_the_venue_over_returns(tmp_path):
    store = DatasetStore(tmp_path)
    start = datetime(2026, 10, 27, 23, 50, tzinfo=UTC)
    end = start + timedelta(minutes=20)  # crosses midnight
    src = Klines()
    first = download_klines(src, store, "d", "ADXUSDT", start, end)
    assert first.still_missing == 0
    rows = store.read("d", "mexc", "ADXUSDT", KLINES_1M)
    assert rows["open_time"].is_unique
    again = download_klines(src, store, "d", "ADXUSDT", start, end)
    assert (again.requested_ranges, again.fetched, again.added) == (0, 0, 0)
    assert len(store.read("d", "mexc", "ADXUSDT", KLINES_1M)) == len(rows)
    days = sorted(
        p.name for p in store.series_dir("d", "mexc", "ADXUSDT", KLINES_1M).iterdir()
    )
    assert days == ["date=2026-10-27", "date=2026-10-28"]


def test_gaps_are_detected_and_only_gaps_are_re_requested(tmp_path):
    store = DatasetStore(tmp_path)
    start = datetime(2026, 10, 27, 23, 55, tzinfo=UTC)
    t = int(start.timestamp() * 1000)
    hole = {t + 3 * MIN_MS, t + 4 * MIN_MS, t + 7 * MIN_MS}  # 23:58, 23:59, 00:02
    res = download_klines(
        Klines(missing=hole),
        store,
        "d",
        "ADXUSDT",
        start,
        start + timedelta(minutes=10),
    )
    assert res.still_missing == 3
    gaps = store.gaps("d", "mexc", "ADXUSDT", KLINES_1M)
    ts = lambda ms_: pd.Timestamp(ms_, unit="ms", tz="UTC")
    assert gaps == [
        (ts(t + 3 * MIN_MS), ts(t + 5 * MIN_MS)),
        (ts(t + 7 * MIN_MS), ts(t + 8 * MIN_MS)),
    ]
    src = Klines()
    res = download_klines(
        src, store, "d", "ADXUSDT", start, start + timedelta(minutes=10)
    )
    assert src.calls == [
        (t + 3 * MIN_MS, t + 5 * MIN_MS),
        (t + 7 * MIN_MS, t + 8 * MIN_MS),
    ]
    assert (
        res.still_missing == 0 and store.gaps("d", "mexc", "ADXUSDT", KLINES_1M) == []
    )


def test_non_utc_input_round_trips_as_utc_across_a_date_boundary(tmp_path):
    store = DatasetStore(tmp_path)
    plus2 = timezone(timedelta(hours=2))
    # 01:30 and 02:30 at +02:00 are 23:30 (day before) and 00:30 UTC.
    local = [
        datetime(2026, 10, 28, 1, 30, tzinfo=plus2),
        datetime(2026, 10, 28, 2, 30, tzinfo=plus2),
    ]
    rows = pd.DataFrame(
        {
            "time": local,
            "price": [1.0, 2.0],
            "quantity": [1.0, 1.0],
            "side": ["buy", "sell"],
        }
    )
    store.write("d", "mexc", "ADXUSDT", TRADES, rows)
    days = sorted(
        p.name for p in store.series_dir("d", "mexc", "ADXUSDT", TRADES).iterdir()
    )
    assert days == ["date=2026-10-27", "date=2026-10-28"]
    back = store.read("d", "mexc", "ADXUSDT", TRADES)
    assert str(back["time"].dt.tz) == "UTC"
    assert list(back["time"]) == [pd.Timestamp(t).tz_convert("UTC") for t in local]
    # Bounds in another zone select by instant.
    window = store.read(
        "d", "mexc", "ADXUSDT", TRADES, start=datetime(2026, 10, 28, 2, 0, tzinfo=plus2)
    )
    assert list(window["price"]) == [2.0]


class Trades:
    def __init__(self, prints):
        self.prints = prints

    def agg_trades(self, symbol, start_ms, end_ms):
        return [p for p in self.prints if start_ms <= p.time_ms <= end_ms]


def test_trades_re_download_deduplicates_the_seam_second(tmp_path):
    store = DatasetStore(tmp_path)
    start = datetime(2026, 10, 27, 23, 59, tzinfo=UTC)
    t = int(start.timestamp() * 1000)
    prints = [
        AggTrade(t + i * 20_000, 1.0 + i, 1.0, i % 2 == 0) for i in range(6)
    ]  # to 00:00:40
    src = Trades(prints)
    first = download_trades(
        src, store, "d", "ADXUSDT", start, start + timedelta(minutes=2)
    )
    assert first.added == 6
    again = download_trades(
        src, store, "d", "ADXUSDT", start, start + timedelta(minutes=2)
    )
    assert again.added == 0 and again.fetched >= 1  # the last stored second, re-fetched
    back = store.read("d", "mexc", "ADXUSDT", TRADES)
    assert len(back) == 6
    assert list(back["side"]) == ["sell", "buy"] * 3  # buyer_is_maker -> aggressor sold
