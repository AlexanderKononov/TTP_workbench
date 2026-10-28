"""MEXC public REST connector and `ttp markets`, tested against saved MEXC responses."""

from pathlib import Path

import httpx
import pytest
from click.testing import CliRunner

from ttp.cli import main
from ttp.screener.universe import thin_markets
from ttp.venues.mexc import MexcClient, MexcError, WeightLimiter

FIXTURES = Path(__file__).parent / "fixtures" / "mexc"
ROUTES = {
    "/api/v3/exchangeInfo": "exchange_info.json",
    "/api/v3/ticker/24hr": "ticker_24hr.json",
}


def fixture_handler(request: httpx.Request) -> httpx.Response:
    body = (FIXTURES / ROUTES[request.url.path]).read_bytes()
    return httpx.Response(
        200, content=body, headers={"Content-Type": "application/json"}
    )


def client_with(handler) -> MexcClient:
    return MexcClient(transport=httpx.MockTransport(handler))


def run_markets(args, handler=fixture_handler):
    return CliRunner().invoke(
        main, ["markets", *args], obj={"mexc": client_with(handler)}, prog_name="ttp"
    )


def test_exchange_info_parses_api_tradability():
    symbols = {s.symbol: s for s in client_with(fixture_handler).exchange_info()}
    assert symbols["ADXUSDT"].quote_asset == "USDT"
    assert symbols["ADXUSDT"].api_tradable
    assert not symbols["ABELUSDT"].api_tradable  # isSpotTradingAllowed false
    assert not symbols["PRSMUSDT"].api_tradable  # status "2"


def test_tickers_parse_quote_volume():
    tickers = {t.symbol: t for t in client_with(fixture_handler).tickers_24h()}
    assert tickers["ADXUSDT"].quote_volume == pytest.approx(47664.9238)
    assert tickers["PRSMUSDT"].quote_volume == 0.0


def test_thin_markets_filters_band_quote_and_tradability_sorted_by_volume():
    client = client_with(fixture_handler)
    markets = thin_markets(
        client.exchange_info(), client.tickers_24h(), max_volume=50_000
    )
    assert [m.symbol for m in markets] == [
        "ADXUSDT",
        "AAVEUSDC",
        "2U2USDT",
        "ABEYUSDT",
        "DEBUSDT",
    ]


def test_markets_command_prints_band_sorted_by_volume():
    result = run_markets(["--max-volume", "50000", "--min-volume", "1000"])
    assert result.exit_code == 0, result.output
    lines = result.output.splitlines()
    rows = [line.split()[0] for line in lines[1:-1]]
    assert rows == ["ADXUSDT", "AAVEUSDC", "2U2USDT", "ABEYUSDT"]
    assert "47,664.92" in result.output
    assert "4 markets" in lines[-1]
    for excluded in (
        "DEBUSDT",
        "BNBUSDT",
        "ABELUSDT",
        "PRSMUSDT",
        "ABTC",
        "4STOCKUSD1",
    ):
        assert excluded not in result.output


def test_markets_rejects_min_above_max():
    result = run_markets(["--max-volume", "100", "--min-volume", "1000"])
    assert result.exit_code != 0
    assert "--min-volume" in result.output


def test_http_error_surfaces_mexc_message():
    def handler(request):
        return httpx.Response(
            400, json={"code": 700003, "msg": "Timestamp outside recvWindow"}
        )

    result = run_markets(["--max-volume", "50000"], handler)
    assert result.exit_code == 1
    assert "HTTP 400" in result.output
    assert "Timestamp outside recvWindow" in result.output
    assert "Traceback" not in result.output


def test_rate_limit_response_reports_retry_after():
    def handler(request):
        return httpx.Response(429, headers={"Retry-After": "7"})

    with pytest.raises(MexcError, match=r"rate limit.*7 s"):
        client_with(handler).tickers_24h()


def test_network_failure_is_a_clear_error():
    def handler(request):
        raise httpx.ConnectError("name resolution failed", request=request)

    result = run_markets(["--max-volume", "50000"], handler)
    assert result.exit_code == 1
    assert "could not reach MEXC" in result.output


def test_weight_limiter_waits_when_budget_spent():
    now = [0.0]
    sleeps = []

    def sleep(seconds):
        sleeps.append(seconds)
        now[0] += seconds

    limiter = WeightLimiter(limit=50, window_s=10.0, clock=lambda: now[0], sleep=sleep)
    limiter.acquire(25)
    now[0] = 2.0
    limiter.acquire(25)
    assert sleeps == []
    limiter.acquire(25)  # budget full until the first request leaves the window at t=10
    assert sleeps == [pytest.approx(8.0)]


@pytest.mark.live
def test_live_public_endpoints():
    with MexcClient() as client:
        symbols = client.exchange_info()
        tickers = client.tickers_24h()
    assert sum(s.api_tradable for s in symbols) > 500
    assert thin_markets(symbols, tickers, max_volume=100_000)
