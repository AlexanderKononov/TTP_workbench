# Gate 7 recommendation: screener v2 run `20261028-113941`

strategist, 2026-10-28. Inputs: `reports/screens/20261028-113941/` (`report.md`, `stats.csv`,
`charts/01..10`, last 6 h of a 24 h window, 1,130 thin MEXC markets), ticket 12 comments,
`src/ttp/screener/wicks.py`, STRATEGY.md section 1/8/10. Every number below is from `stats.csv`
or read off a chart; anything marked [H] is a hypothesis.

## 1. One-command approval

```
uv run ttp dataset approve 20261028-113941 DRVUSDT ORAIUSDT PYRUSDT --name spike-harvest-01
```

Defaults apply (seed 0, band x2, controls with 0 spike events, 30 days of 1m klines). Run from
the repo root with the screen folder present under `reports/screens/`; the run lives in the
platform-engineer worktree today, so the Governor copies it first. Three candidates, three
auto-picked pattern-free controls, one dataset card. Nothing here is a confirmed example of the
section-1 pattern; these are the best three of 1,130 and the dataset exists to test the
calibration (M3), not to trade.

## 2. Chart review of the v2 top 10

| # | Market | Class | Verdict | Reasoning (chart = last 6 h; stats = 24 h) |
|--:|---|---|---|---|
| 1 | UMXMUSDT | gap market | reject | $15.9k/day, dashed no-trade stretches, `base_range` 0; the one spike (06:36) is a two-way print (+7% / -6% in one minute); retrace 120% |
| 2 | GMUSDT | trend (step-up) | reject | +24% in steps 02:36 to 07:00, then -8% at 07:55; wicks sit on step tops; the 07:15 wick does return, but the zone itself moves every hour |
| 3 | TAPEFOURUSDT | chop + regime break | reject | +-1% chop, one visible wick on a step (02:50), then a -12% dump at 07:25 with no return; 6 of 7 events are outside the chart window |
| 4 | BORDRUSDT | chop | reject | `base_range` 0.67% (widest in the top 10), 6% band of noisy steps; no event visible in 6 h; a 3% wick does not stand out |
| 5 | DRVUSDT | sweep-and-return | **approve** | calm base (0.08%), continuous volume; 02:58 single-minute +4.3% sweep, closes +1.5%, holds 15 min, returns to the zone; 6/6 returned, 99 min; regularity only 0.16 |
| 6 | XNTUSDT | gap market | reject | $5.4k/day, dashed flats, 25% swing, `base_range` 0, retrace 149%; same verdict as the v1 review |
| 7 | XTMUSDT | gap market / crash | reject | dashed flats, `base_range` 0, -35% crash at 06:45 then partial recovery; wicks are single prints inside the crash |
| 8 | PYRUSDT | calm base, violent bursts | **approve (marginal)** | 4 h flat at 0.11% base; 06:15 +7% run-up in bodies (not counted) returning in 20 min; 07:06 wick to +7% then -5% to 0.0177 before returning; 3/3 returned but only 2 intervals |
| 9 | ROBINUSDT | trend | reject | +20% from 06:40 in steps; the 4 visible wicks sit on step tops; v1 failure mode that v2 lets through |
| 10 | ORAIUSDT | sweep-and-return | **approve** | calm base (0.18%); 03:45 single-minute +4.5% sweep closing back in the zone; one -1.5% step-down at 06:00; 4/4 returned, 115 min, regularity 0.31 |

Reject list: UMXMUSDT, GMUSDT, TAPEFOURUSDT, BORDRUSDT, XNTUSDT, XTMUSDT, ROBINUSDT.

Caveats on the approve list: DRV and ORAI show 1 event each inside the 6 h chart; the other
5 + 3 events are only known from the stats. PYR's 07:06 burst drops 5% below the zone within
minutes; a `stop_pct` at its 3% floor would be hit, so PYR mostly tests the stop path. All three
sit at the calibration floor (3 returned events/day); 7 days of history will decide.

## 3. Verdict on ticket 12's observations: v2 stays, one v3 gate to add

1. **Calm-base gate removed nothing.** Keep `wick_median >= 2 x base_range` as is; it is
   principled and cheap, but it is not the lever: 1m ranges of thin markets are 0.1-0.7%, so 2x is
   below the 2% wick floor. Raising to 5x would cut only BORDRUSDT in this top 10 [H]. Not worth
   a ticket.
2. **`base_range = 0` markets are gap markets: confirmed** by charts 1, 6, 7 (UMXM, XNT, XTM); the
   other four scoring with base 0 (RWSUSDT, MIUUSDT, VEREMUSDT, SYMMUSDT) are $6k-$81k/day and
   unseen, same signature. **v3 rule (follow-up ticket, platform-engineer):**
   - `active_share` = share of non-spike candles with `high > low`, reported as a column;
   - score 0 unless `active_share >= 0.5` [H]. This is exactly `base_range > 0`, so on this run
     it removes the 7 base-0 markets and no other; the 0.5 floor is the place to tighten later.
     `volume > 0` is the alternative definition; `high > low` is preferred because a single print
     a minute is still an empty base for a resting order.
   - STRATEGY.md section 3 eligibility gains the same condition so screener and calibration agree.
3. **`retrace_median > 1`**: keep as a diagnostic, no gate. A last close below the first open means
   the rebuy at the anchor fills; not a defect for the strategy. Values >= 1.3 here (XNT 1.49,
   MHA 1.44, VEREM 1.32) all co-occur with base 0 or 0.04%, so rule 2 removes them.

Second v3 lever, lower priority [H]: ROBINUSDT and GMUSDT pass every v2 gate while trending,
because `retrace` compares the last close with the event's own first open, and a wick on top of a
step that happened minutes earlier "returns" to the step. Measuring the return against the
pre-event anchor `A_e` of STRATEGY.md section 2, `retrace' = (H_e - C_e) / (H_e - A_e)`, gives
ROBIN's wicks about 2.7 / (3 + 2.7) = 0.47 < 0.5 and leaves a sweep on a flat zone unchanged
(`A_e ~ O_e`). It needs the rolling anchor in the screener, which calibration needs anyway. Cut it
as a separate ticket only after the 7-day history shows the trend leak matters.

## 4. Decisions for the Owner

1. Approve the three candidates (command above), or trim to DRVUSDT + ORAIUSDT.
2. Cut the v3 ticket (active-share gate) now, or run the 7-day calibration on the dataset first.
3. Whether a later dataset version should add ROBINUSDT or GMUSDT as hard negatives (trend with
   returned wicks): the `approve` command only knows candidates and pattern-free controls, so hard
   negatives would appear on the card as candidates. Not recommended for v1; M3 can read them from
   the screener cache for one 24 h window.

## 5. Open risks

- Base rate: 3 candidates of 1,130 after two screens; one 24 h window; no market shows more than
  one clean sweep inside its chart. The pattern may be rarer than the spec's prior.
- 24h-volume controls are matched on volume only; the band x2 around DRV/ORAI/PYR ($54k-$63k) is
  dense with pattern-free markets, so the draw will succeed, but controls may be calmer than
  candidates in base range. The card records the draw; no action.
- Chart window: 6 h hides 18 h of events; a `--hours 24` chart or a per-event strip would make
  the next gate-7 review a 10-minute job instead of a stats-trust exercise. Worth a small ticket.
