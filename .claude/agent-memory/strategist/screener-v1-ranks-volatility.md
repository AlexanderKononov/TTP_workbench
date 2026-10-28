---
name: screener-v1-ranks-volatility
description: Screener v1 score (events x wick x (1+regularity)) surfaced trending/gap/choppy markets, not sweep-and-return; strategist proposed v2 gates (return, calm base, spacing) on 2026-10-28
metadata:
  type: project
---

The first live screen (2026-10-28, 1,130 thin MEXC markets) produced no market showing the up-spike pattern in its top 10; 9 of 10 had regularity 0. The v2 rule (returned events only, calm-base and spacing gates) is in `src/ttp/strategies/up_spike_harvest/STRATEGY.md` §10 and awaits a platform-engineer ticket and a re-run on cached klines.

**Why:** Wick count x size rewards volatility; the pattern is defined by the return to a normal zone, which v1 never measured.

**How to apply:** When reviewing screens, open the charts before trusting the score; check retrace and base calm by eye. Until v2 runs, treat "no confirmed example market" as the state of evidence for gate 2/7 discussions. Likely v2 candidates to chart first: GMUSDT, TAPEFOURUSDT, BORDRUSDT, UMXMUSDT, UBIKUSDT, PYRUSDT.
