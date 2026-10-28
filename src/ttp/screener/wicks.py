"""Upper-wick metrics on 1-minute klines: evidence of a volume bot's sweep-and-return.

A spike candle has an upper wick (high above the body top) of at least `min_wick`,
as a fraction of the body top. Adjacent spike minutes are one event. An event has
**returned** when price retraced at least `MIN_RETRACE` of its rise by the close of
its last candle. A market is scored by how many returned sweeps it shows, how big
they typically are and how regularly they recur, and only when they stand out from
a calm base; otherwise it scores 0 (rule: `up_spike_harvest/STRATEGY.md` section 10).
"""

import math
from dataclasses import dataclass

import pandas as pd

MIN_EVENTS = 3  # returned events; at least two intervals, so regularity means something
MIN_RETRACE = 0.5  # returned when (high - close_last) / (high - open_first) >= this
MIN_INTERVAL_MIN = 10.0  # closer returned events are one episode, not a bot
MIN_WICK_TO_BASE = 2.0  # typical sweep must be this many times the base candle range

EVENT_COLUMNS = ["start", "wick", "open_first", "high", "close_last", "retrace"]


@dataclass(frozen=True)
class WickStats:
    candles: int
    wick_count: int  # spike events in the window, returned or not
    returned_events: int  # events whose retrace >= MIN_RETRACE
    wick_median: float  # typical returned sweep, fraction of the body top (NaN if none)
    wick_max: float  # biggest wick of any event
    retrace_median: float  # typical retrace over all events (NaN if none)
    base_range: (
        float  # median (high - low) / close over non-spike candles (NaN if none)
    )
    interval_median_min: float  # typical minutes between returned events (NaN if < 2)
    regularity: float  # 1 - coefficient of variation of those intervals, in [0, 1]
    score: float  # returned_events * wick_median * (1 + regularity); 0 unless gated in


def upper_wicks(klines: pd.DataFrame) -> pd.Series:
    """Upper wick of each candle as a fraction of its body top (0 when undefined)."""
    body_top = klines[["open", "close"]].max(axis=1)
    wick = (klines["high"] - body_top) / body_top.where(body_top > 0)
    return wick.fillna(0.0).clip(lower=0.0)


def spike_events(klines: pd.DataFrame, min_wick: float) -> pd.DataFrame:
    """One row per event (EVENT_COLUMNS): runs of adjacent minutes with wick >= min_wick.

    `open_first` and `close_last` are the open of the run's first candle and the close
    of its last; `high` its highest print; `retrace` = (high - close_last) /
    (high - open_first), or 0 when the run did not rise above its open.
    """
    wick = upper_wicks(klines)
    spike = wick >= min_wick
    if not spike.any():
        empty = pd.DataFrame(columns=EVENT_COLUMNS)
        return empty.astype({"start": "datetime64[ns, UTC]", "retrace": float})
    spikes = klines.loc[spike, ["open_time", "open", "high", "close"]]
    spikes = spikes.assign(wick=wick[spike])
    new_event = spikes["open_time"].diff() != pd.Timedelta(minutes=1)
    events = spikes.groupby(new_event.cumsum(), sort=True).agg(
        start=("open_time", "first"),
        wick=("wick", "max"),
        open_first=("open", "first"),
        high=("high", "max"),
        close_last=("close", "last"),
    )
    rise = events["high"] - events["open_first"]
    retrace = (events["high"] - events["close_last"]) / rise.where(rise > 0)
    return events.assign(retrace=retrace.fillna(0.0))


def base_range(klines: pd.DataFrame, min_wick: float) -> float:
    """Median (high - low) / close over non-spike candles; NaN when there are none."""
    calm = klines[upper_wicks(klines) < min_wick]
    if calm.empty:
        return math.nan
    ranges = (calm["high"] - calm["low"]) / calm["close"].where(calm["close"] > 0)
    return float(ranges.median())


def wick_stats(klines: pd.DataFrame, min_wick: float) -> WickStats:
    """Spike statistics of a market's klines (sorted by `open_time`)."""
    events = spike_events(klines, min_wick)
    returned = events[events["retrace"] >= MIN_RETRACE]
    n, r = len(events), len(returned)
    intervals = returned["start"].diff().dropna().dt.total_seconds() / 60
    interval_median = float(intervals.median()) if len(intervals) else math.nan
    regularity = 0.0
    if r >= MIN_EVENTS:
        cv = intervals.std(ddof=0) / intervals.mean()
        regularity = max(0.0, 1.0 - float(cv))
    wick_median = float(returned["wick"].median()) if r else math.nan
    base = base_range(klines, min_wick)
    is_pattern = (
        r >= MIN_EVENTS
        and interval_median >= MIN_INTERVAL_MIN
        and regularity > 0
        and wick_median >= MIN_WICK_TO_BASE * base  # False when base is NaN
    )
    return WickStats(
        candles=len(klines),
        wick_count=n,
        returned_events=r,
        wick_median=wick_median,
        wick_max=float(events["wick"].max()) if n else math.nan,
        retrace_median=float(events["retrace"].median()) if n else math.nan,
        base_range=base,
        interval_median_min=interval_median,
        regularity=regularity,
        score=r * wick_median * (1 + regularity) if is_pattern else 0.0,
    )


COLUMNS = [
    "rank",
    "market",
    "score",
    "returned_events",
    "wick_count",
    "wick_median",
    "retrace_median",
    "base_range",
    "wick_max",
    "interval_median_min",
    "regularity",
    "volume_24h",
    "candles",
]


def rank(rows: list[dict]) -> pd.DataFrame:
    """Rank markets: score, then returned events, then all events, then name."""
    table = pd.DataFrame(rows, columns=COLUMNS[1:])
    table = table.sort_values(
        ["score", "returned_events", "wick_count", "market"],
        ascending=[False, False, False, True],
    ).reset_index(drop=True)
    table.insert(0, "rank", range(1, len(table) + 1))
    return table
