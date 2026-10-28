"""Market events and fills: what a strategy reacts to.

Every event carries `time`, the tz-aware UTC instant at which the event became
known. For a kline that is its close time, not its open time: a strategy that saw
a candle's close at its open time would be looking into the future. The feed is
responsible for stamping events so, and for delivering them in `time` order.

Prices and quantities are floats, matching the dataset storage (DOUBLE); venue
precision is applied by the broker, not here.
"""

from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum


@dataclass(frozen=True, slots=True)
class Market:
    """One tradable pair on one venue, e.g. `Market("mexc", "ADXUSDT")`."""

    venue: str
    symbol: str

    def __str__(self) -> str:
        return f"{self.venue}:{self.symbol}"


class Side(StrEnum):
    BUY = "buy"
    SELL = "sell"


@dataclass(frozen=True, slots=True)
class Trade:
    """A public trade print. `side` is the aggressor (taker) side."""

    market: Market
    time: datetime
    price: float
    quantity: float
    side: Side


@dataclass(frozen=True, slots=True)
class BookLevel:
    price: float
    quantity: float


@dataclass(frozen=True, slots=True)
class BookSnapshot:
    """Top-of-book depth at one instant: bids best-first, asks best-first."""

    market: Market
    time: datetime
    bids: tuple[BookLevel, ...]
    asks: tuple[BookLevel, ...]

    @property
    def best_bid(self) -> BookLevel | None:
        return self.bids[0] if self.bids else None

    @property
    def best_ask(self) -> BookLevel | None:
        return self.asks[0] if self.asks else None


@dataclass(frozen=True, slots=True)
class Kline:
    """A closed OHLCV candle for [open_time, time). `time` is the close time."""

    market: Market
    time: datetime
    open_time: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float
    quote_volume: float


@dataclass(frozen=True, slots=True)
class Timer:
    """A periodic tick from the feed, for strategies that act on time, not data."""

    time: datetime


MarketEvent = Trade | BookSnapshot | Kline | Timer


@dataclass(frozen=True, slots=True)
class Fill:
    """An execution (possibly partial) of one of the strategy's orders.

    `fee` is in the quote currency; the broker that produced the fill decides it.
    """

    market: Market
    time: datetime
    client_id: str
    side: Side
    price: float
    quantity: float
    fee: float = 0.0
