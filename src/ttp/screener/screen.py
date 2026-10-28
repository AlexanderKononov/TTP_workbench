"""Screener v1: scan thin markets' recent 1-minute klines for recurring upper wicks.

Klines are fetched through the downloader into the `screener` dataset, so a
re-run over the same window costs no requests and the report can be redrawn from
what is stored.
"""

from collections.abc import Callable, Iterable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime

import pandas as pd

from ttp.data.downloader import VENUE, download_klines
from ttp.data.store import KLINES_1M, DatasetStore
from ttp.screener.universe import MarketVolume, thin_markets
from ttp.screener.wicks import rank, wick_stats
from ttp.venues.mexc import MexcClient, MexcError, MexcRateLimited

SCREEN_DATASET = "screener"  # cache of scanned klines; not an approved dataset

# Markets fetched at once. MEXC round trips take ~0.4 s, so 6 workers use about
# half of the 300 weight / 10 s budget; the shared WeightLimiter caps the rest.
WORKERS = 6


@dataclass(frozen=True)
class ScreenParams:
    max_volume: float
    min_volume: float
    hours: int
    min_wick: float
    include_st: bool


@dataclass(frozen=True)
class Screen:
    screen_id: str
    start: pd.Timestamp  # window of klines scanned: [start, end)
    end: pd.Timestamp
    params: ScreenParams
    universe: int  # markets in the volume band
    table: pd.DataFrame  # one row per scanned market, ranked (see wicks.COLUMNS)
    skipped: dict[str, str]  # market -> why its klines could not be fetched


def screen_id(now: datetime) -> str:
    return pd.Timestamp(now).tz_convert("UTC").strftime("%Y%m%d-%H%M%S")


def window(now: datetime, hours: int) -> tuple[pd.Timestamp, pd.Timestamp]:
    end = pd.Timestamp(now).tz_convert("UTC").floor("min")
    return end - pd.Timedelta(hours=hours), end


def universe(client: MexcClient, params: ScreenParams) -> list[MarketVolume]:
    return thin_markets(
        client.exchange_info(),
        client.tickers_24h(),
        params.max_volume,
        params.min_volume,
        include_st=params.include_st,
    )


def scan(
    client: MexcClient,
    store: DatasetStore,
    markets: Iterable[MarketVolume],
    now: datetime,
    params: ScreenParams,
    universe_size: int,
    progress: Callable[[MarketVolume], None] | None = None,
    workers: int = WORKERS,
) -> Screen:
    """Fetch each market's klines for the window and rank by wick statistics.

    Markets are fetched `workers` at a time; `progress` is called as each one
    finishes. A market whose klines fail to download is skipped and reported; a
    venue rate-limit error stops the scan (continuing would get the IP banned).
    """
    start, end = window(now, params.hours)

    def stats_of(m: MarketVolume) -> dict:
        download_klines(client, store, SCREEN_DATASET, m.symbol, start, end)
        klines = store.read(SCREEN_DATASET, VENUE, m.symbol, KLINES_1M, start, end)
        stats = wick_stats(klines, params.min_wick)
        return {"market": m.symbol, "volume_24h": m.quote_volume_24h, **vars(stats)}

    rows, skipped = [], {}
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = {pool.submit(stats_of, m): m for m in markets}
        try:
            for future in as_completed(futures):
                m = futures[future]
                try:
                    rows.append(future.result())
                except MexcRateLimited:
                    raise
                except MexcError as exc:
                    skipped[m.symbol] = str(exc)
                if progress:
                    progress(m)
        except MexcRateLimited:
            pool.shutdown(cancel_futures=True)  # queued markets are not fetched
            raise
    return Screen(
        screen_id=screen_id(now),
        start=start,
        end=end,
        params=params,
        universe=universe_size,
        table=rank(rows),
        skipped=skipped,
    )
