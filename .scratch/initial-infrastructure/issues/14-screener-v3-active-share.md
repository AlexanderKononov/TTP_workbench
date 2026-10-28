# 14: Screener v3 — base-activity gate (`active_share`)

**Role:** platform-engineer

**Status:** done

**Blocked by:** 12, 13

**What to build:** Gap markets (most minutes have no trade, so the "calm base" is empty, not calm) stop scoring. The screener reports `active_share` = share of non-spike candles with `high > low`, and a market scores 0 unless `active_share >= 0.5` (hypothesis [H] from the strategist; see `gate-7-recommendation.md` §v3 and STRATEGY.md §10).

Spec: [../spec.md](../spec.md)

- [x] `wick_stats` adds `active_share` (NaN when there are no non-spike candles → score 0); gate `MIN_ACTIVE_SHARE = 0.5` applied with the v2 gates
- [x] `COLUMNS`, CSV, `report.md`, chart titles and the `ttp screen` table carry the column; v1/v2 columns stay
- [x] Fixture: the existing `gap_prints` series plus a new "sparse prints" series (most minutes flat, occasional returned spikes) score 0; `calm_sweeps` still ranks first
- [x] `ttp screen --chart-hours` already exists: raise its default to 24 for gate-7 reviews (the strategist asked for a 24 h view)
- [x] Offline re-run on the cached `screener` dataset (as in ticket 12; copy the cache from the ticket-12 worktree) and confirm in `## Comments` that exactly UMXMUSDT, XNTUSDT, XTMUSDT, RWSUSDT, MIUUSDT, VEREMUSDT, SYMMUSDT drop out and DRVUSDT, ORAIUSDT, PYRUSDT still score; leave the new report path

## Comments

platform-engineer, 2026-10-28:

- **Metric and gate** (`src/ttp/screener/wicks.py`): `active_share(klines, min_wick)` = share of non-spike candles with `high > low` (STRATEGY.md section 2 definition; `high > low` rather than `volume > 0`, per the gate-7 recommendation), NaN when every candle is a spike or the series is empty. `wick_stats` reports it as `WickStats.active_share` and the pattern test adds `active_share >= MIN_ACTIVE_SHARE` (0.5, [H]) to the v2 gates; a NaN fails the comparison, so the score is 0. `base_range` and `active_share` share one `base_candles` helper. `COLUMNS` inserts `active_share` after `base_range`; v1/v2 columns are unchanged.
- **Outputs:** `stats.csv` (via `COLUMNS`), the `report.md` header notes and table ("Active" after "Base range"), chart titles (`active NN%`) and the `ttp screen` console table (`ACTIVE` after `BASE`) carry the column. The Telegram phone summary is unchanged (fixed 46-char rows; the gate is reflected in the score). `--chart-hours` default is 24 (still capped at `--hours`).
- **Fixtures** (`tests/test_screener.py`, decision): the v1 `row()` fixture printed every candle flat (`low == open == close`), which is exactly the empty base the gate removes, so `periodic`/`irregular` series would have scored 0. Every `row()` candle now dips `BASE_DIP = 0.1%` below its open (`base_range` 0.10% instead of 0.00% in the `ttp screen` assertions; nothing else changes). New `sparse_prints` series: flat minutes, one minute in five trades a little (`active_share` = 240/1392 = 0.17), a 6% single print returns every 30 min: 48 returned, regularity 1, `base_range` 0, v2 wick-to-base gate vacuous, score 0 through the active-share gate alone; the same prints over a base that trades every minute score. `gap_prints` (active 1.0) still scores 0 via the wick-to-base gate; `calm_sweeps` ranks first ahead of SMALL, GAP, SPARSE, TREND, CTRL.
- **Re-run on the cached dataset (no venue requests):** window 2026-10-27 08:36 to 2026-10-28 08:36 UTC, the 1,130-market universe and 24h volumes of the v2 re-score `20261028-113941`, klines read only from `data/datasets/screener` (2,260 files copied from the ticket-12 worktree). Report (gitignored, in this worktree): `C:\git\TTP_workbench\.claude\worktrees\agent-a91954e1b4b6ba0b9\reports\screens\20261028-115908\` (`report.md`, `stats.csv`, `charts/01..10` at 24 h). **Confirmed:** scoring markets 33 -> 26; dropped exactly UMXMUSDT (active 0.19), XNTUSDT (0.09), XTMUSDT (0.09), RWSUSDT (0.29), MIUUSDT (0.09), VEREMUSDT (0.21), SYMMUSDT (0.03), all with `base_range` 0; nothing added. DRVUSDT (rank 4, score 0.25), PYRUSDT (5, 0.23) and ORAIUSDT (7, 0.19) still score. **Top 10:** GMUSDT, TAPEFOURUSDT, BORDRUSDT, DRVUSDT, PYRUSDT, ROBINUSDT, ORAIUSDT, ARGUSUSDT, FLORKUSDT, MASKSOLUSDT.
- **Observation for the strategist:** the 0.5 floor is far from the data on this run: every scoring market has `active_share >= 0.89` (median 0.999), and the dropped seven sit at 0.03-0.29. Of the 55 markets with >= 3 returned events, 10 are below 0.5 (the seven plus three that already failed a v2 gate), none lie in (0.5, 0.85], two in (0.85, 0.89], 43 above 0.95. Tightening the floor later is free up to about 0.85.
- **Tests:** `uv run pytest` (119 passed, 5 deselected), `uv run ruff check`, `uv run ruff format --check` all pass.
