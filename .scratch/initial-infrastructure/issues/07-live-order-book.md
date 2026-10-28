# 07: Live order book

**Role:** platform-engineer

**Status:** ready-for-agent

**Blocked by:** 01

**What to build:** The venue connector maintains a correct local order book for a MEXC market from the live WebSocket feed, recovering from gaps.

Spec: [../spec.md](../spec.md)

- [ ] WebSocket client subscribes to MEXC depth diffs (and trades) for a market; book initialised from a REST snapshot and kept in sync by sequence/version numbers
- [ ] A sequence gap or disconnect triggers resync; each event is reported so the recorder can write a gap log
- [ ] `ttp watch <market>` shows live top-of-book and recent trades
- [ ] Book maintenance tested against saved WebSocket message fixtures, including out-of-order and gap scenarios; no network in default tests
- [ ] Own implementation, not the ccxt.pro MEXC book feed (ADR-0007)
