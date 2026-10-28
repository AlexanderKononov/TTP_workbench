"""Verifier (ticket 11): screener v3 gates and ranking (tickets 04/12/14).

One synthetic market passes every gate; each test breaks exactly one gate and
checks the score drops to 0, with the passing side of the same boundary as the
control. Thresholds: returned >= 3, interval median >= 10 min, regularity > 0,
wick median >= 2 x base range, active share >= 0.5 (wicks.py constants).
"""

import math
import random

import pandas as pd
import pytest

from ttp.screener import wicks
from ttp.screener.wicks import COLUMNS, rank, wick_stats

MIN_WICK = 0.02
START = pd.Timestamp("2026-10-27 08:00", tz="UTC")


def market(
    sweeps=(20, 65, 110, 155, 200),  # starts, every 45 min: regular
    minutes=300,
    wick=0.06,
    base=0.004,  # (high - low) / close of a trading base candle
    flat_every=None,  # (k, n): minute i is flat (no range) when i % n < k
    unreturned=(),  # sweep starts that close at their high
) -> pd.DataFrame:
    rows = []
    for i in range(minutes):
        o = c = 1.0
        h, lo = 1.0 + base / 2, 1.0 - base / 2
        if flat_every and i % flat_every[1] < flat_every[0]:
            h = lo = 1.0
        if i in sweeps:
            h = 1.0 + wick
            # Unreturned: closes 46% of the rise below the high (retrace 0.46),
            # still a spike candle (upper wick 2.7% of the body top).
            c = 1.0 + wick * 0.54 if i in unreturned else 1.0
            lo = min(lo, 1.0)
        rows.append((START + pd.Timedelta(minutes=i), o, h, lo, c))
    df = pd.DataFrame(rows, columns=["open_time", "open", "high", "low", "close"])
    df["volume"] = df["quote_volume"] = 1.0
    return df


def score(**kw) -> float:
    return wick_stats(market(**kw), MIN_WICK).score


def test_reference_market_passes_every_gate():
    s = wick_stats(market(), MIN_WICK)
    assert s.returned_events == 5 and s.interval_median_min == 45
    assert s.regularity == 1.0 and s.active_share == 1.0
    assert s.base_range == pytest.approx(0.004)
    assert s.score == pytest.approx(5 * 0.06 * 2)


@pytest.mark.parametrize(
    "kw, gated",
    [
        # returned events < 3
        ({"sweeps": (20, 65)}, True),
        ({"sweeps": (20, 65, 110)}, False),
        ({"unreturned": (110, 155, 200)}, True),  # 5 events, only 2 returned
        # interval median < 10 min (events 5 min apart are still separate)
        ({"sweeps": (20, 25, 30, 35, 40)}, True),
        ({"sweeps": (20, 30, 40, 50, 60)}, False),  # exactly 10
        # regularity 0 (intervals 10, 10, 10, 100: cv > 1)
        ({"sweeps": (20, 30, 40, 50, 150)}, True),
        # wick < 2 x base
        ({"wick": 0.022, "base": 0.012}, True),
        ({"wick": 0.025, "base": 0.012}, False),
        # active share < 0.5 (base range 0 there, so the wick gate is vacuous)
        ({"flat_every": (6, 10)}, True),
        ({"flat_every": (4, 10)}, False),
    ],
)
def test_each_gate_alone_zeroes_the_score(kw, gated):
    s = wick_stats(market(**kw), MIN_WICK)
    if gated:
        assert s.score == 0.0, s
    else:
        assert s.score > 0.0, s


def test_regularity_zero_case_passes_the_other_gates():
    s = wick_stats(market(sweeps=(20, 30, 40, 50, 150)), MIN_WICK)
    assert s.regularity == 0.0
    assert s.returned_events == 5 and s.interval_median_min == 10
    assert s.wick_median >= wicks.MIN_WICK_TO_BASE * s.base_range


def test_active_share_case_isolates_the_active_gate():
    s = wick_stats(market(flat_every=(6, 10)), MIN_WICK)
    assert s.active_share < wicks.MIN_ACTIVE_SHARE
    assert s.returned_events == 5 and s.regularity == 1.0


def test_all_spike_market_has_nan_base_and_scores_zero():
    df = market(sweeps=tuple(range(0, 300, 2)), minutes=300)
    df = df[df.index % 2 == 0].reset_index(drop=True)  # every candle a spike
    s = wick_stats(df, MIN_WICK)
    assert math.isnan(s.active_share) and math.isnan(s.base_range)
    assert s.score == 0.0


def _rows():
    out = []
    for name, kw in [
        ("AAA", {}),
        ("BBB", {"wick": 0.04}),
        ("CCC", {"sweeps": (20, 30, 40, 50, 150)}),
        ("DDD", {"sweeps": (20, 65)}),
        ("EEE", {}),  # ties AAA on every stat
        ("FFF", {"unreturned": (110,)}),
    ]:
        out.append(
            {
                "market": name,
                "volume_24h": 1000.0,
                **vars(wick_stats(market(**kw), MIN_WICK)),
            }
        )
    return out


def test_ranking_is_deterministic_under_row_shuffles():
    rows = _rows()
    expected = rank(rows)
    assert list(expected.columns) == COLUMNS
    assert list(expected["rank"]) == list(range(1, 7))
    rng = random.Random(7)
    for _ in range(20):
        shuffled = rows[:]
        rng.shuffle(shuffled)
        pd.testing.assert_frame_equal(rank(shuffled), expected)
    # Score first, name breaks a full tie; zero scores ordered by events then name.
    assert list(expected["market"]) == ["AAA", "EEE", "BBB", "FFF", "CCC", "DDD"]
    assert list(expected["score"][4:]) == [0.0, 0.0]
    fff = expected.set_index("market").loc["FFF"]
    assert (fff["wick_count"], fff["returned_events"]) == (5, 4)
    assert (expected["score"].diff().dropna() <= 0).all()
