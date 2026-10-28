# 09: Write the up-spike-harvest strategy definition

**Role:** strategist

**Status:** done

**Blocked by:** 04

**What to build:** An exact definition of the first strategy for the Owner to approve at gate 2, before any strategy code is written.

Spec: [../spec.md](../spec.md)

- [x] `STRATEGY.md` for `up-spike-harvest` under the strategies package: pattern, normal zone, cycle (buy inventory in normal zone, resting sells at spike reach, rebuy), order placement and requote rules under MEXC limits (no amend, 12 req/s)
- [x] Per-market calibration from history: which statistics set spike levels, inventory size and stop; deterministic and testable
- [x] Protections as case limits: max inventory per market, stop below normal zone, expiry, max loss; stage = backtest
- [x] Evidence from a real screener run and kline data; open hypotheses marked as such
- [x] Status line: awaiting Owner approval (gate 2)

## Comments

strategist, 2026-10-28:

- **Deliverable:** `src/ttp/strategies/up_spike_harvest/STRATEGY.md`. Status line "awaiting Owner approval (gate 2)", stage backtest. Written against `core/strategy.py`, `events.py`, `intents.py`: the strategy uses `on_start`, `on_kline` (anchor + requote + stop), `on_trade` (stop), `on_fill` (cycle), `on_stop` (cancel-all) and emits only `PlaceLimit`/`Cancel`.
- **Core definitions:** spike candle and events reuse `screener/wicks.py`; added per event the retrace `(H - C_last)/(H - O_first)`, "returned" = retrace ≥ 0.5; anchor = trailing 60-min median of closes excluding spike candles; reach = event high / anchor − 1.
- **Calibration (pure function of klines + symbol filters):** sell levels at Q25/Q50/Q75 of returned-event reach with 40/35/25 shares; rebuy at the anchor; stop = clamp(3 × zone_dev_95, 3%, 10%) off average cost; inventory = min(per-market limit, 25% of median sweep quote volume), levels merged until each clears min notional; dead-pattern timeout = max(6 h, 4 × median interval). Eligibility: ≥ 3 returned sweeps/day, median interval ≥ 10 min, regularity > 0, sweep ≥ 2 × base range, r_1 ≥ 0.5%.
- **MEXC rules:** cancel + place requotes only when the target moves ≥ 0.5%, once per closed minute per order; ≤ 4 orders/market → ≤ 8 req/min/market; maker-only pricing (never cross the spread) except the stop sell; venue price band and min-size handling spelled out.
- **Evidence:** inspected 7 of the top-10 charts from screen `20261028-083639`; none shows the pattern (trending steps, gap markets, chop). 9 of 10 have regularity 0. There is no confirmed example market yet; the definition is approved on its logic and the candidate list waits for screener v2.
- **Screener decision (ticket 04 question):** regularity alone is not the fix; count only returned events, gate on return/spacing/calm base, keep the score form. Full rule in STRATEGY.md §10; note appended to ticket 04. **Code change needed** in `screener/wicks.py` (+ report columns, fixtures) and a re-run on the cached klines — Governor to ticket for platform-engineer.
- **QUESTION FOR OWNER (gate 2):** (1) `on_stop` cancels orders but does not sell inventory at expiry/kill — conservative choice, Owner decides on leftover inventory; confirm. (2) First-case limits taken from the spec's M6 line ($50 / $20 per market / $15 max loss / 7 days), plus max 4 open orders per market and 2% max slippage on the stop sell. (3) The 0% maker fee is unverified; if it is not 0, `min_profit` and the lowest level rise.
- **Process note:** this worktree was checked out at `main`, not at `governor/initial-infrastructure-spec`, so the ticket files and `src/ttp` were absent; inputs were read from the sibling worktree named in the task and the two ticket files were written in full here for the Governor to commit on `strategist/09-up-spike-harvest-strategy-definition`. No tests or lint apply (docs only).
