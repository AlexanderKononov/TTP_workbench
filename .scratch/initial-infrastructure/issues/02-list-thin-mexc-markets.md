# 02: List thin MEXC markets

**Role:** platform-engineer

**Status:** done

**Blocked by:** 01

**What to build:** The first live path through the MEXC venue connector: the Owner runs one command and sees which thin markets can be traded through the API.

Spec: [../spec.md](../spec.md)

- [x] Venue connector for MEXC public REST (no credentials) fetches 24h tickers and exchange info
- [x] `ttp markets --max-volume <usd> [--min-volume <usd>]` prints USDT/USDC markets within the band that are API-tradable (spot trading allowed, API permissions), with 24h quote volume, sorted by volume
- [x] Connector parsing tested against saved MEXC response fixtures (no network in default tests); an opt-in `live` pytest marker hits the real endpoints
- [x] Respects MEXC rate limits; HTTP errors surface as clear messages

## Comments

platform-engineer, 2026-10-28:

- **HTTP client:** raw REST with `httpx` (new dependency) rather than ccxt. Two public GETs don't need ccxt, and `httpx.MockTransport` lets tests serve the saved fixtures without the network. Connector: `src/ttp/venues/mexc/client.py`. The universe filter is pure and lives in `src/ttp/screener/universe.py`, so ticket 04 can reuse it.
- **API-tradable** = `status == "1"`, `isSpotTradingAllowed`, and `SPOT` in `permissions`, as in venue-dev-ease.md. `tradeSideType` (4 on the 3 delisted symbols) and the `st` flag (62 symbols) are not filtered yet.
- **Volume:** 24h `quoteVolume` in USDT/USDC is shown as USD (stablecoin quotes). USD1 and other quotes are excluded per the ticket. Sorted by volume, highest first; ties are broken by symbol.
- **Rate limits:** the MEXC docs (introduction page, checked 2026-10-28) say IP-weighted endpoints share 300 weight per 10 s, and `exchangeInfo` and `ticker/24hr` weigh 25 each. A sliding-window `WeightLimiter` blocks before going over that budget, and ticket 04's kline scan will reuse it. On 429/418 the client stops with a message that includes `Retry-After` and does not retry, because MEXC bans IPs that keep sending after a 429.
- **Errors:** network failures, HTTP errors (with MEXC `msg`/`code`) and invalid JSON become a `MexcError`, and the CLI prints it as `Error: ...` with exit code 1 and no traceback.
- **Fixtures:** `tests/fixtures/mexc/` holds real responses captured 2026-10-28, cut down to 10 symbols that cover each filter case.
- **Live tests:** marked `live` and deselected by default (`-m "not live"` in pytest addopts). Run them with `uv run pytest -m live`.
