# Strategy: up-spike-harvest

**Status:** awaiting Owner approval (gate 2)
**Stage:** backtest (not yet coded)
**Venue:** MEXC spot (ADR-0007) · **Author:** strategist, 2026-10-28
**Interface:** `ttp.core.strategy.Strategy` (ADR-0006); emits only `PlaceLimit` / `Cancel`

Every number below is either derived from a formula on the market's own klines
(deterministic, testable) or marked **[H]** = hypothesis, to be settled by the M3
backtest sweep or by paper trading. Nothing marked [H] is evidence.

## 1. Pattern

A **sweep** is a taker buying through the asks of a thin market, lifting the price by
several percent for seconds to minutes, after which the price returns to where it
was. A market shows the **spike pattern** when sweeps recur with roughly regular
spacing on top of a calm **normal zone** (a price band in which most trading happens).
The hypothesised cause is a volume bot; the strategy does not depend on the cause,
only on the recurrence.

What we harvest: a sell limit resting inside the sweep's reach fills at the top of the
sweep; the inventory is rebought in the normal zone after the return. With 0% maker
fee (unverified, see §9) each completed cycle earns the level's offset above the zone.

What the pattern is **not** (seen in the 2026-10-28 screen, §8): trending markets
whose wicks sit on top of upward steps, gap-trading markets where single prints in a
wide spread print as wicks, and choppy noise. None of those return to a zone.

## 2. Definitions (on 1-minute klines sorted by `open_time`)

| Symbol | Definition |
|---|---|
| `body_top_t` | `max(open_t, close_t)` |
| `wick_t` | `(high_t - body_top_t) / body_top_t`, clipped at 0 (same as `screener/wicks.py`) |
| spike candle | `wick_t >= min_wick` |
| event `e` | a maximal run of adjacent spike minutes; `O_e` = open of its first candle, `H_e` = max high, `C_e` = close of its last candle, `w_e` = max `wick_t` in the run |
| retrace `ρ_e` | `(H_e - C_e) / (H_e - O_e)` if `H_e > O_e` else 0 |
| returned event | `ρ_e >= min_retrace` |
| anchor `A_t` | median of `close` over the trailing `zone_window` closed candles **excluding spike candles**; if fewer than `zone_min_candles` remain, median over all `zone_window` candles |
| reach `g_e` | `H_e / A_(first candle of e, previous close) - 1` (anchor as of the candle before the event) |
| `base_range` | median over non-spike candles of `(high - low) / close` |
| `zone_dev_95` | 95th percentile over non-spike candles of `abs(close_t / A_t - 1)` |
| interval `Δ_i` | minutes between consecutive returned-event starts |
| `regularity` | `max(0, 1 - std(Δ)/mean(Δ))` (population std; same as the screener) |
| event quote volume `V_e` | sum of `quote_volume` over the event's candles |

Constants: `min_wick = 0.02`, `min_retrace = 0.5` [H], `zone_window = 60`,
`zone_min_candles = 20`. The anchor is computable incrementally in `on_kline`, so the
strategy tracks it live with the same definition the calibration uses.

## 3. Calibration (deterministic step; output is part of the case)

Input: the market's 1m klines for the last `cal_days = 7` days [H; MEXC keeps 30; 7
reflects current bot behaviour, M3 checks stability against 14], plus the venue's
symbol filters (min quantity, min notional, price tick). Output: a `Params` record.

1. Compute events, returned events `R`, `A_t`, `g_e`, `base_range`, `zone_dev_95`,
   `Δ`, `regularity`, `V_e` as in §2.
2. **Eligibility** (all must hold, else the market is not calibrated and not tradable):
   - `len(R) >= 3 * cal_days` (on average ≥ 3 returned sweeps per day);
   - `median(Δ) >= 10` minutes (bursts are one episode, not a bot) [H];
   - `regularity > 0` (interval cv < 1) [H];
   - `median(w_e over R) >= 2 * base_range` (sweeps stand out from zone noise) [H];
   - `r_1 >= min_profit` (see step 3).
3. **Sell levels** from the reach distribution of returned events:
   `r_1 = Q25(g_R)`, `r_2 = Q50(g_R)`, `r_3 = Q75(g_R)` with inventory shares
   `s = (0.40, 0.35, 0.25)` [H; M3 sweeps the quantiles]. Rationale: a sell at offset
   `r` fills in sweeps with `g_e >= r`, so lower levels fill often for less, higher
   levels rarely for more. `min_profit = 0.005` [H; must exceed the stop's taker fee and
   two spreads].
4. **Rebuy offset** `b = 0` [H]: the rebuy rests at the anchor. Alternative for M3:
   `b = median(abs(close_t / A_t - 1))`.
5. **Stop** `stop_pct = clamp(3 * zone_dev_95, 0.03, 0.10)` [H]: outside normal-zone
   noise, never tighter than 3% (noise would stop us out) nor wider than 10%.
6. **Inventory notional** `I = min(limit_per_market, 0.25 * median(V_e over R))` [H]:
   our sells must be a minority of a typical sweep's volume or they absorb it. If
   `I < 3 * min_notional`, drop the highest level and give its share to the previous
   one; repeat; if a single level is still below `min_notional`, the market is not
   tradable at this budget.
7. **Pattern timeout** `T_dead = max(6 h, 4 * median(Δ))`: how long without any event
   before the market is treated as dead (§5.6).
8. **Expected cycles/day** per level `k`: `count(g_R >= r_k) / cal_days`, and expected
   gross/day `= Σ_k I * s_k * r_k * cycles_k` — printed in the case as evidence, not
   used by the strategy.

The calibration is a pure function of (klines, symbol filters, constants); the same
input gives the same `Params`. `verifier` can fix a kline fixture and assert the
record field by field.

## 4. State

Per market: `params`, `anchor` (updated per closed kline), `inventory_qty`,
`avg_cost`, `pending_rebuy_qty`, resting orders by `client_id` (side, price, qty,
level index), `last_event_time`, `last_trade_price`, `halted` flag, realized PnL.

## 5. Cycle and rules

All prices are emitted unrounded; the broker applies tick and lot precision
(`core/events.py`). Quantities are base units; `qty_k = s_k * I / anchor` at the time
of the initial buy.

### 5.1 Start (`on_start`)
No orders until the first `Kline` has established `anchor` (backtest) or the first
`BookSnapshot` is seen (paper/live). Then place **one buy** for the full inventory:
`price = min(anchor * (1 - b), best_ask - tick)` if a book is known, else
`min(anchor * (1 - b), last close)`. Never price a buy at or above the best ask.

### 5.2 Buy fill (`on_fill`, side BUY)
Update `inventory_qty`, `avg_cost`. Once `inventory_qty * anchor >= min_notional`,
place the **sell ladder**: for each level `k`, `price_k = max(anchor * (1 + r_k),
avg_cost * (1 + min_profit))`, `qty_k = s_k * inventory_qty`. Never price a sell at or
below the best bid. Levels that the venue's price band would reject (§6) are held back
and placed on the first kline where they fit.

### 5.3 Sell fill (`on_fill`, side SELL)
Realized PnL `+= qty * (price - avg_cost) - fee`. Add `qty` to `pending_rebuy_qty`.
If `pending_rebuy_qty * anchor >= min_notional`: place a buy for `pending_rebuy_qty`
at the §5.1 price and reset it to 0. Partial fills leave the sell's remainder resting.

### 5.4 Requote (`on_kline`, every closed 1m candle)
Recompute `anchor`. For each resting order compute its target price (§5.1 / §5.2).
If `abs(target / resting_price - 1) >= requote_tol` (`0.005` [H]): emit `Cancel`
then `PlaceLimit` with a fresh `client_id`. Sells are never requoted below
`avg_cost * (1 + min_profit)`. A cancel whose fill arrives first is handled by §5.3
(the fill wins; the replacement is not placed). The anchor excludes spike candles, so
a sweep in progress does not move the sells.

### 5.5 Stop (`on_trade` and `on_kline`)
`stop_level = avg_cost * (1 - stop_pct)`. Trigger: a trade print or a 1m close below
`stop_level` while `inventory_qty > 0`. Action, in order: `Cancel` every resting order,
`PlaceLimit` sell of the full inventory at `best_bid * (1 - stop_slip)` (`stop_slip =
0.01` [H]; the one order that may take liquidity), set `halted`. A halted market
places nothing more for the rest of the case; the Owner restarts it with a new
confirmation. If the stop sell is not filled within `stop_retry = 60 s`, requote it
at the new best bid (cancel + place), at most once per minute.

### 5.6 Pattern gone
If `now - last_event_time > T_dead` (events detected live with §2 on closed klines):
cancel the buy, requote all sells to `avg_cost * (1 + min_profit)`, and once flat set
`halted`. Holding inventory in a coin whose bot has left is the main unpriced risk.

### 5.7 Stop of the case (`on_stop`, expiry or kill switch)
Emit `Cancel` for every resting order. Inventory is **not** liquidated automatically;
the report shows it and the Owner decides. (The kill switch's cancel-all in the
execution service is the hard guarantee; this is the strategy's cooperative part.)

## 6. MEXC constraints the rules respect

- **No amend**: every requote is `Cancel` + `PlaceLimit` (§5.4); the strategy never
  assumes a cancel succeeded before a fill — `on_fill` is authoritative.
- **12 req/s shared place+cancel budget**: per market at most `levels + 1 = 4` resting
  orders, each requoted at most once per closed minute: ≤ 8 requests/min/market,
  ≤ 40/min for a 5-market case — under 1% of the budget. Self-limit
  `max_intents_per_minute = 20` per market; beyond it, requotes wait for the next
  kline (stop orders are exempt).
- **Maker only**: buys always below best ask, sells always above best bid; the only
  taker order is the stop. Whether `PlaceLimit` maps to `LIMIT` or `LIMIT_MAKER` is a
  broker decision; the strategy's pricing never crosses, so either is safe [H: MEXC
  rejects rather than fills a LIMIT_MAKER that would cross — quant-engineer to
  confirm when wiring the execution service].
- **Price band**: MEXC rejects limit prices outside a band around the last price
  (`exchangeInfo`, band size unknown) [H]. Sell levels outside the band are held back
  (§5.2) and placed when they fit; calibration reports any level that exceeds the
  band at anchor.
- **Min quantity / min notional** per symbol: handled in calibration step 6 and in the
  `min_notional` checks of §5.2–5.3.
- **`tradeSideType` / API-disabled pairs**: filtered by the screener universe; the
  calibration refuses a symbol whose filters forbid either side.

## 7. Case limits (enforced by the execution service, ADR-0002/0004)

For the first live case (M6, spec): budget $50 total; `limit_per_market` $20;
`max_loss` $15 (realized + unrealized at best bid); expiry 7 days;
`max_open_orders` 4 per market; `max_slippage` 2% on the stop sell (reject the stop
order if the best bid is more than 2% below the stop level and alert; the Owner
decides). Parameters per market (`Params` from §3) are attached to the case. The
strategy's own stop (§5.5) is tighter than `max_loss` by construction:
`I * stop_pct <= 20 * 0.10 = $2` per market.

## 8. Evidence from the first live screen (2026-10-28 08:36 UTC)

Source: `reports/screens/20261028-083639/` (1,130 thin MEXC markets, 24 h of 1m
klines, `min_wick` 2%); inspected `report.md`, `stats.csv` and the charts of ranks
1–4, 7, 9, 10 (last 6 h each).

- 9 of the top 10 by the v1 score have `regularity = 0.00` (interval cv ≥ 1); the
  v1 score (events × typical wick × (1 + regularity)) ranked them on count and size.
- **None of the 7 inspected charts shows the pattern of §1.** RTUSDT, QUICKUSDT,
  MICRODUCKUSDT: wicks sit on top of upward steps of a trending price, no return.
  IRONUSDT: a 40% swing with gaps. CTXUSDT, XNTUSDT: ~$5k/day, dashed no-trade
  periods, wicks are single prints in a wide spread. HOOKEDUSDT: choppy ±1.5% noise.
- Candidates not charted that the v2 rule (§10) would surface for a look: GMUSDT (9
  events, reg 0.47, 155 min), TAPEFOURUSDT (7, 0.45, 170 min), BORDRUSDT (5, 0.59,
  106 min), UMXMUSDT (5, 0.40, 348 min), UBIKUSDT (3, 0.80, 44 min), PYRUSDT (3, 0.81,
  548 min). ZEPHUSDT (reg 1.00) and MPLXUSDT (0.71) have 3–4 min intervals: one burst.
- Consequence: **there is no confirmed example market yet.** The spec's prior (1 in a
  30-market hand sample) and this screen agree that the pattern is rare; this
  definition is approved on its logic, and the candidate list waits for the screener
  v2 re-run on the cached klines (no venue requests needed).

## 9. Open hypotheses and risks

1. **Fees**: 0% maker / 0.05% taker is from a secondary source only
   (venue-research.md [20]). A maker fee > 0 shifts `min_profit` and `r_1` up.
2. **The sweep sees us**: on a $5k–$100k/day market our $20 of asks is visible; a bot
   that sizes its sweep to the book may stop short of our level, or lift it only once.
   Only paper trading (M4) and M5/M6 at minimum size answer this (ADR-0005).
3. **Queue position**: at a given price other asks may rest ahead of ours; the M3
   queue-position fill model is the honest baseline, fill-on-touch the ceiling.
4. **Return assumption**: a sweep that is the start of a pump leaves us flat in USDT
   (we sold low) — a missed gain, not a loss. A zone that drifts down leaves us in
   inventory until the stop — the real loss path; §5.6 and the stop bound it.
5. **Calibration thresholds** (`min_retrace`, `cal_days`, quantiles, `stop_pct`
   multiplier, inventory fraction of sweep volume) are first guesses; M3 sweeps them
   against control markets and reports all three fill models.
6. **Zone anchor on klines only**: in backtest the anchor updates once a minute; live
   it could use trades, but keeping one definition in all stages (ADR-0006) wins.

## 10. Screening rule for this strategy (decision on ticket 04's question)

Question: should regularity weigh more than wick count? **Decision: regularity alone
is not the fix.** The v1 score's failure is that wick count × size rewards volatile
and gap-trading markets; a regularity multiplier only halves their score. The pattern's
defining features are the *return* and the *calm base*, which v1 does not measure.
Recommended v2 (same module, same `WickStats` shape plus the new fields):

- Count **returned events** only (`ρ_e >= 0.5`), replacing `wick_count`.
- Score 0 unless: `returned_events >= 3`, `interval_median_min >= 10`,
  `regularity > 0`, and `wick_median >= 2 * base_range`.
- Score `= returned_events × wick_median × (1 + regularity)` (unchanged form).
- Report `base_range`, `retrace_median`, `returned_events` as new columns; charts
  unchanged.

Code change needed (platform-engineer, ticket to be cut): `spike_events` gains
`open_first`/`close_last`/`retrace` per event; `wick_stats` gains `base_range`,
`retrace_median`, `returned_events` and the filters above; `COLUMNS`/report/table
updated; fixtures: a "trending steps" series and a "gap single prints" series must
score 0, a "calm zone + returned sweeps" series must rank first. Re-run on the cached
`data/datasets/screener` klines and chart the new top 10 for the strategist to review
before gate 7. Keep `--min-wick 0.02` until v2 output is seen.
