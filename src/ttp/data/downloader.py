"""Downloader: fetch available venue history into a dataset, filling only what is missing."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Protocol

import pandas as pd

from ttp.data.store import KLINES_1M, DatasetStore
from ttp.venues.mexc import Kline

VENUE = "mexc"


class KlineSource(Protocol):
    def klines(
        self, symbol: str, start_ms: int, end_ms: int, interval: str = "1m"
    ) -> list[Kline]: ...


@dataclass(frozen=True)
class DownloadResult:
    start: pd.Timestamp
    end: pd.Timestamp
    requested_ranges: int  # missing ranges asked from the venue
    fetched: int  # rows the venue returned
    added: int  # rows new to the dataset
    still_missing: int  # minutes in [start, end) the dataset still lacks


def missing_ranges(
    have: pd.Series, start: pd.Timestamp, end: pd.Timestamp, step: timedelta
) -> list[tuple[pd.Timestamp, pd.Timestamp]]:
    """Contiguous [from, to) ranges of grid times in [start, end) not in `have`."""
    grid = pd.date_range(start, end, freq=step, inclusive="left")
    missing = grid.difference(pd.DatetimeIndex(have))
    ranges: list[tuple[pd.Timestamp, pd.Timestamp]] = []
    for t in missing:
        if ranges and ranges[-1][1] == t:
            ranges[-1] = (ranges[-1][0], t + step)
        else:
            ranges.append((t, t + step))
    return ranges


def _ms(t: pd.Timestamp) -> int:
    return int(t.timestamp() * 1000)


def klines_frame(klines: list[Kline]) -> pd.DataFrame:
    df = pd.DataFrame(
        [vars(k) for k in klines],
        columns=[
            "open_time_ms",
            "open",
            "high",
            "low",
            "close",
            "volume",
            "quote_volume",
        ],
    )
    df.insert(
        0, "open_time", pd.to_datetime(df.pop("open_time_ms"), unit="ms", utc=True)
    )
    return df


def download_klines(
    source: KlineSource,
    store: DatasetStore,
    dataset: str,
    market: str,
    start: datetime,
    end: datetime,
) -> DownloadResult:
    """Fetch 1-minute klines for [start, end) that the dataset lacks and store them."""
    step = KLINES_1M.interval
    start = pd.Timestamp(start).tz_convert("UTC").floor(step)
    end = pd.Timestamp(end).tz_convert("UTC").floor(step)

    def stored_minutes() -> pd.Series:
        df = store.read(dataset, VENUE, market, KLINES_1M, start, end)
        return df[KLINES_1M.time_column]

    todo = missing_ranges(stored_minutes(), start, end, step)
    klines: list[Kline] = []
    for lo, hi in todo:
        klines.extend(source.klines(market, _ms(lo), _ms(hi), "1m"))
    added = store.write(dataset, VENUE, market, KLINES_1M, klines_frame(klines))
    still = missing_ranges(stored_minutes(), start, end, step)
    return DownloadResult(
        start=start,
        end=end,
        requested_ranges=len(todo),
        fetched=len(klines),
        added=added,
        still_missing=sum((hi - lo) // step for lo, hi in still),
    )
