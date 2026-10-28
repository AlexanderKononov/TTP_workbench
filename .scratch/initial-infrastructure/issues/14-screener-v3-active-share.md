# 14: Screener v3 — base-activity gate (`active_share`)

**Role:** platform-engineer

**Status:** ready-for-agent

**Blocked by:** 12, 13

**What to build:** Gap markets (most minutes have no trade, so the "calm base" is empty, not calm) stop scoring. The screener reports `active_share` = share of non-spike candles with `high > low`, and a market scores 0 unless `active_share >= 0.5` (hypothesis [H] from the strategist; see `gate-7-recommendation.md` §v3 and STRATEGY.md §10).

Spec: [../spec.md](../spec.md)

- [ ] `wick_stats` adds `active_share` (NaN when there are no non-spike candles → score 0); gate `MIN_ACTIVE_SHARE = 0.5` applied with the v2 gates
- [ ] `COLUMNS`, CSV, `report.md`, chart titles and the `ttp screen` table carry the column; v1/v2 columns stay
- [ ] Fixture: the existing `gap_prints` series plus a new "sparse prints" series (most minutes flat, occasional returned spikes) score 0; `calm_sweeps` still ranks first
- [ ] `ttp screen --chart-hours` already exists: raise its default to 24 for gate-7 reviews (the strategist asked for a 24 h view)
- [ ] Offline re-run on the cached `screener` dataset (as in ticket 12; copy the cache from the ticket-12 worktree) and confirm in `## Comments` that exactly UMXMUSDT, XNTUSDT, XTMUSDT, RWSUSDT, MIUUSDT, VEREMUSDT, SYMMUSDT drop out and DRVUSDT, ORAIUSDT, PYRUSDT still score; leave the new report path
