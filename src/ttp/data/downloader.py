"""Downloader: fetch available venue history into a dataset, filling only what is missing."""

from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Protocol

import pandas as pd

from ttp.data.store import KLINES_1M, TRADES, DatasetStore
from ttp.venues.mexc import AggTrade, Kline

VENUE = "mexc"


class KlineSource(Protocol):
    def klines(
        self, symbol: str, start_ms: int, end_ms: int, interval: str = "1m"
    ) -> list[Kline]: ...


class TradeSource(Protocol):
    def agg_trades(self, symbol: str, start_ms: int, end_ms: int) -> list[AggTrade]: ...


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


@dataclass(frozen=True)
class TradesDownloadResult:
    start: pd.Timestamp  # range asked from the venue: [start, end)
    end: pd.Timestamp
    fetched: int  # prints the venue returned
    added: int  # prints new to the dataset


def trades_frame(trades: list[AggTrade]) -> pd.DataFrame:
    df = pd.DataFrame(
        [
            {
                "time_ms": t.time_ms,
                "price": t.price,
                "quantity": t.quantity,
                "side": "sell" if t.buyer_is_maker else "buy",
            }
            for t in trades
        ],
        columns=["time_ms", "price", "quantity", "side"],
    )
    df.insert(0, "time", pd.to_datetime(df.pop("time_ms"), unit="ms", utc=True))
    return df


def download_trades(
    source: TradeSource,
    store: DatasetStore,
    dataset: str,
    market: str,
    start: datetime,
    end: datetime,
) -> TradesDownloadResult:
    """Fetch trade prints for [start, end) and store them.

    Trades have no grid, so a quiet hour and a missing hour look the same; the
    dataset cannot tell what it lacks. The venue is therefore asked from the
    last stored print (or `start`) onwards, and re-running extends the series.
    Prints at the last stored second are fetched again and deduplicated.
    """
    start = pd.Timestamp(start).tz_convert("UTC").floor("s")
    end = pd.Timestamp(end).tz_convert("UTC").floor("s")
    stored = store.read(dataset, VENUE, market, TRADES, start, end)
    if not stored.empty:
        start = max(start, stored[TRADES.time_column].iloc[-1])
    trades = source.agg_trades(market, _ms(start), _ms(end)) if start < end else []
    added = store.write(dataset, VENUE, market, TRADES, trades_frame(trades))
    return TradesDownloadResult(start, end, len(trades), added)
