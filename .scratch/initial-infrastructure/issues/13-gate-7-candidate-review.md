# 13: Review screener v2 candidates for gate 7

**Role:** strategist

**Status:** done

**Blocked by:** 12

**What to build:** A gate-7 recommendation the Owner can act on in one command: which markets from the screener v2 run to approve into the first dataset, with the chart evidence for each, and a verdict on whether the v2 gates need a v3 change (base-activity gate for gap markets) before the Owner relies on them.

Spec: [../spec.md](../spec.md)

- [x] Each of the v2 top-10 charts (`reports/screens/20261028-113941/charts/`) reviewed and classified: sweep-and-return / gap market / trend / chop, with one line of reasoning each
- [x] Recommended approve list (markets + the exact `ttp dataset approve 20261028-113941 <markets...> --name <name>` command) and a reject list, written to `.scratch/initial-infrastructure/gate-7-recommendation.md`
- [x] Verdict on ticket 12's three observations (vacuous calm-base gate, `base_range = 0` markets, `retrace_median > 1`): keep v2 as is, or specify the v3 rule precisely for a follow-up ticket
- [x] STRATEGY.md screening section updated if the rule changes; status line stays "awaiting Owner approval (gate 2)"

## Comments

strategist, 2026-10-28:

- **Recommendation:** [../gate-7-recommendation.md](../gate-7-recommendation.md). Approve DRVUSDT, ORAIUSDT, PYRUSDT (PYR marginal) into `spike-harvest-01`; reject UMXMUSDT, GMUSDT, TAPEFOURUSDT, BORDRUSDT, XNTUSDT, XTMUSDT, ROBINUSDT. Classes: sweep-and-return 2 (DRV, ORAI), calm base with violent bursts 1 (PYR), gap market 3 (UMXM, XNT, XTM), trend 2 (GM, ROBIN), chop 2 (TAPEFOUR, BORDR). No market is a confirmed example; the dataset exists to test the calibration.
- **v3 verdict:** v2 stays. One rule to add in a follow-up platform-engineer ticket: `active_share` = share of non-spike candles with `high > low`, reported as a column, score 0 unless `>= 0.5` [H]. Equals `base_range > 0`, so on this run it removes exactly the 7 base-0 markets (UMXM, XNT, XTM, RWS, MIU, VEREM, SYMM), three of which the charts confirm as gap markets. Calm-base multiplier stays at 2x; `retrace_median` stays a diagnostic. A second, lower-priority lever (retrace measured against the pre-event anchor, to stop ROBIN/GM-style trends with wicks on steps) is specified in the recommendation but not cut until 7-day history shows the leak matters.
- **STRATEGY.md:** section 10 gains the v3 rule; section 3 eligibility gains the matching `active_share` condition so screener and calibration agree; section 8 gains the v2 evidence. Status line unchanged.
- Chart window of 6 h shows at most one event per candidate; a 24 h chart option for gate-7 reviews is suggested as a small ticket (recommendation, section 5).
- QUESTION FOR OWNER: approve all three or only DRV + ORAI; cut the v3 ticket now or after the 7-day calibration run. Conservative default taken in the command: all three, v3 ticket after the Owner reads the recommendation.
