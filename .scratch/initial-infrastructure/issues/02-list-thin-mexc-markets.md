# 02: List thin MEXC markets

**Role:** platform-engineer

**Status:** ready-for-agent

**Blocked by:** 01

**What to build:** The first live path through the MEXC venue connector: the Owner runs one command and sees which thin markets can be traded through the API.

Spec: [../spec.md](../spec.md)

- [ ] Venue connector for MEXC public REST (no credentials) fetches 24h tickers and exchange info
- [ ] `ttp markets --max-volume <usd> [--min-volume <usd>]` prints USDT/USDC markets within the band that are API-tradable (spot trading allowed, API permissions), with 24h quote volume, sorted by volume
- [ ] Connector parsing tested against saved MEXC response fixtures (no network in default tests); an opt-in `live` pytest marker hits the real endpoints
- [ ] Respects MEXC rate limits; HTTP errors surface as clear messages
