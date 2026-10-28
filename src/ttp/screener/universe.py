"""The screener's universe: API-tradable thin markets within a 24h volume band."""

from collections.abc import Iterable
from dataclasses import dataclass

from ttp.venues.mexc import SymbolInfo, Ticker24h

# Stablecoin quotes, so 24h quote volume reads as USD.
QUOTE_ASSETS = ("USDT", "USDC")


@dataclass(frozen=True)
class MarketVolume:
    symbol: str
    base_asset: str
    quote_asset: str
    quote_volume_24h: float


def thin_markets(
    symbols: Iterable[SymbolInfo],
    tickers: Iterable[Ticker24h],
    max_volume: float,
    min_volume: float = 0.0,
) -> list[MarketVolume]:
    """API-tradable USDT/USDC markets with min <= 24h quote volume <= max, highest first."""
    volume = {t.symbol: t.quote_volume for t in tickers}
    markets = [
        MarketVolume(s.symbol, s.base_asset, s.quote_asset, volume[s.symbol])
        for s in symbols
        if s.api_tradable
        and s.quote_asset in QUOTE_ASSETS
        and s.symbol in volume
        and min_volume <= volume[s.symbol] <= max_volume
    ]
    return sorted(markets, key=lambda m: (-m.quote_volume_24h, m.symbol))
