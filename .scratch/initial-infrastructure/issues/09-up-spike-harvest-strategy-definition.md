# 09: Write the up-spike-harvest strategy definition

**Role:** strategist

**Status:** ready-for-agent

**Blocked by:** 04

**What to build:** An exact definition of the first strategy for the Owner to approve at gate 2, before any strategy code is written.

Spec: [../spec.md](../spec.md)

- [ ] `STRATEGY.md` for `up-spike-harvest` under the strategies package: pattern, normal zone, cycle (buy inventory in normal zone, resting sells at spike reach, rebuy), order placement and requote rules under MEXC limits (no amend, 12 req/s)
- [ ] Per-market calibration from history: which statistics set spike levels, inventory size and stop; deterministic and testable
- [ ] Protections as case limits: max inventory per market, stop below normal zone, expiry, max loss; stage = backtest
- [ ] Evidence from a real screener run and kline data; open hypotheses marked as such
- [ ] Status line: awaiting Owner approval (gate 2)
