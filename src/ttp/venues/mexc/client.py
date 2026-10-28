"""MEXC spot public REST client. Public endpoints only: no credentials here (ADR-0004)."""

import time
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any, Self

import httpx

BASE_URL = "https://api.mexc.com"

# MEXC spot v3: IP-weighted endpoints share 300 weight per 10 s; exceeding it
# returns 429, and continuing after 429 gets the IP banned (418).
IP_WEIGHT_LIMIT = 300
IP_WEIGHT_WINDOW_S = 10.0
WEIGHT_EXCHANGE_INFO = 25
WEIGHT_TICKER_24HR = 25


class MexcError(Exception):
    """A MEXC request failed; the message is meant for the Owner."""


class WeightLimiter:
    """Sliding-window request-weight budget; blocks until a request fits."""

    def __init__(
        self,
        limit: int = IP_WEIGHT_LIMIT,
        window_s: float = IP_WEIGHT_WINDOW_S,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        self._limit = limit
        self._window_s = window_s
        self._clock = clock
        self._sleep = sleep
        self._spent: deque[tuple[float, int]] = deque()

    def acquire(self, weight: int) -> None:
        if weight > self._limit:
            raise ValueError(f"weight {weight} exceeds limit {self._limit}")
        while True:
            now = self._clock()
            while self._spent and self._spent[0][0] <= now - self._window_s:
                self._spent.popleft()
            if sum(w for _, w in self._spent) + weight <= self._limit:
                self._spent.append((now, weight))
                return
            self._sleep(self._spent[0][0] + self._window_s - now)


@dataclass(frozen=True)
class SymbolInfo:
    """One spot market as described by `exchangeInfo`."""

    symbol: str
    base_asset: str
    quote_asset: str
    status: str
    spot_trading_allowed: bool
    permissions: tuple[str, ...]

    @property
    def api_tradable(self) -> bool:
        """Open for spot trading through the API."""
        return (
            self.status == "1"
            and self.spot_trading_allowed
            and "SPOT" in self.permissions
        )


@dataclass(frozen=True)
class Ticker24h:
    symbol: str
    last_price: float
    quote_volume: float


def parse_exchange_info(payload: dict[str, Any]) -> list[SymbolInfo]:
    return [
        SymbolInfo(
            symbol=s["symbol"],
            base_asset=s["baseAsset"],
            quote_asset=s["quoteAsset"],
            status=str(s["status"]),
            spot_trading_allowed=bool(s["isSpotTradingAllowed"]),
            permissions=tuple(s.get("permissions", ())),
        )
        for s in payload["symbols"]
    ]


def parse_tickers_24h(payload: list[dict[str, Any]]) -> list[Ticker24h]:
    return [
        Ticker24h(
            symbol=t["symbol"],
            last_price=float(t["lastPrice"] or 0),
            quote_volume=float(t["quoteVolume"] or 0),
        )
        for t in payload
    ]


class MexcClient:
    """Public MEXC spot REST endpoints, throttled by a shared weight budget."""

    def __init__(
        self,
        base_url: str = BASE_URL,
        transport: httpx.BaseTransport | None = None,
        limiter: WeightLimiter | None = None,
        timeout_s: float = 15.0,
    ) -> None:
        self._http = httpx.Client(
            base_url=base_url, transport=transport, timeout=timeout_s
        )
        self._limiter = limiter or WeightLimiter()

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def close(self) -> None:
        self._http.close()

    def exchange_info(self) -> list[SymbolInfo]:
        return parse_exchange_info(
            self._get("/api/v3/exchangeInfo", WEIGHT_EXCHANGE_INFO)
        )

    def tickers_24h(self) -> list[Ticker24h]:
        return parse_tickers_24h(self._get("/api/v3/ticker/24hr", WEIGHT_TICKER_24HR))

    def _get(self, path: str, weight: int, params: dict[str, Any] | None = None) -> Any:
        self._limiter.acquire(weight)
        try:
            response = self._http.get(path, params=params)
        except httpx.HTTPError as exc:
            raise MexcError(f"could not reach MEXC ({path}): {exc}") from exc
        if response.status_code in (418, 429):
            retry_after = response.headers.get("Retry-After", "?")
            raise MexcError(
                f"MEXC rate limit hit on {path} (HTTP {response.status_code}); "
                f"retry after {retry_after} s"
            )
        if response.is_error:
            raise MexcError(
                f"MEXC {path} returned HTTP {response.status_code}: {_error_text(response)}"
            )
        try:
            return response.json()
        except ValueError as exc:
            raise MexcError(f"MEXC {path} returned invalid JSON") from exc


def _error_text(response: httpx.Response) -> str:
    try:
        body = response.json()
    except ValueError:
        return response.text[:200] or response.reason_phrase
    if isinstance(body, dict) and "msg" in body:
        return f"{body['msg']} (code {body.get('code')})"
    return str(body)[:200]
