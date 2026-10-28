---
name: gate-7-chart-review
description: How to run a gate-7 screener candidate review (chart window limits, approve-command semantics, what gates actually bite on thin MEXC markets)
metadata:
  type: feedback
---

Review screener candidates from chart + stats together and say which events are
actually visible; then recommend with one exact `ttp dataset approve` command.

**Why:** Screen charts show the last 6 h of a 24 h window, so a candidate with 4-6
returned events usually shows one inside the chart; the rest are stats only. On the
2026-10-28 v2 run, gap markets (`base_range = 0`, dashed no-trade stretches) and
trends with wicks on step tops both passed every v2 gate; the calm-base gate
(`wick >= 2 x base_range`) removed nothing because 1m ranges on thin markets are
0.1-0.7%, below the 2% wick floor. `regularity > 0` did most of the filtering.

**How to apply:**
- Classify each chart as sweep-and-return / gap market / trend / chop with one line;
  mark which events are in-window. Calm base + single-minute spike closing back is
  the only class to approve.
- `ttp dataset approve <screen_id> <markets...> --name <name>` knows only candidates
  and auto-picked pattern-free controls (volume band x2, 0 events, seed 0). Hard
  negatives (trend with returned wicks) would show on the card as candidates; keep
  them out of v1 datasets and note them for the Owner instead.
- The screen folder must sit under the repo root `reports/screens/`; agent runs
  leave it in a worktree, so say that the Governor copies it.
- Candidates sit at the calibration floor (3 returned/day); say so and frame the
  dataset as a calibration test, not a trade list.
