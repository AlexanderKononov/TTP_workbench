"""Upper-wick metrics on 1-minute klines: evidence of a volume bot sweeping the book.

A spike candle has an upper wick (high above the body top) of at least `min_wick`,
as a fraction of the body top. Adjacent spike minutes are one event. A market is
scored by how many events it shows, how big they typically are and how regularly
they recur; fewer than `MIN_EVENTS` events is not a pattern and scores 0.
"""

import math
from dataclasses import dataclass

import pandas as pd

MIN_EVENTS = 3  # at least two intervals, so regularity means something


@dataclass(frozen=True)
class WickStats:
    candles: int
    wick_count: int  # spike events in the window
    wick_median: float  # typical spike size, fraction of the body top (NaN if none)
    wick_max: float
    interval_median_min: float  # typical minutes between events (NaN if < 2 intervals)
    regularity: float  # 1 - coefficient of variation of the intervals, in [0, 1]
    score: float  # wick_count * wick_median * (1 + regularity); 0 below MIN_EVENTS


def upper_wicks(klines: pd.DataFrame) -> pd.Series:
    """Upper wick of each candle as a fraction of its body top (0 when undefined)."""
    body_top = klines[["open", "close"]].max(axis=1)
    wick = (klines["high"] - body_top) / body_top.where(body_top > 0)
    return wick.fillna(0.0).clip(lower=0.0)


def spike_events(klines: pd.DataFrame, min_wick: float) -> pd.DataFrame:
    """One row per event (`start`, `wick`): runs of adjacent minutes with wick >= min_wick."""
    wick = upper_wicks(klines)
    spikes = pd.DataFrame(
        {"start": klines["open_time"], "wick": wick}, index=klines.index
    )[wick >= min_wick]
    if spikes.empty:
        return spikes
    new_event = spikes["start"].diff() != pd.Timedelta(minutes=1)
    return spikes.groupby(new_event.cumsum(), sort=True).agg(
        start=("start", "first"), wick=("wick", "max")
    )


def wick_stats(klines: pd.DataFrame, min_wick: float) -> WickStats:
    """Spike statistics of a market's klines (sorted by `open_time`)."""
    events = spike_events(klines, min_wick)
    n = len(events)
    intervals = events["start"].diff().dropna().dt.total_seconds() / 60
    regularity = 0.0
    if n >= MIN_EVENTS:
        cv = intervals.std(ddof=0) / intervals.mean()
        regularity = max(0.0, 1.0 - float(cv))
    median = float(events["wick"].median()) if n else math.nan
    return WickStats(
        candles=len(klines),
        wick_count=n,
        wick_median=median,
        wick_max=float(events["wick"].max()) if n else math.nan,
        interval_median_min=float(intervals.median()) if len(intervals) else math.nan,
        regularity=regularity,
        score=n * median * (1 + regularity) if n >= MIN_EVENTS else 0.0,
    )


COLUMNS = [
    "rank",
    "market",
    "score",
    "wick_count",
    "wick_median",
    "wick_max",
    "interval_median_min",
    "regularity",
    "volume_24h",
    "candles",
]


def rank(rows: list[dict]) -> pd.DataFrame:
    """Rank markets: score, then wick count, then market name; one row each."""
    table = pd.DataFrame(rows, columns=COLUMNS[1:])
    table = table.sort_values(
        ["score", "wick_count", "market"], ascending=[False, False, True]
    ).reset_index(drop=True)
    table.insert(0, "rank", range(1, len(table) + 1))
    return table
