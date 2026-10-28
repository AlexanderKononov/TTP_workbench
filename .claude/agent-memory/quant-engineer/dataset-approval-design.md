---
name: dataset-approval-design
description: Decisions behind ttp dataset approve (ticket 06): definition lives in data/datasets/<name>/dataset.json and is rendered into the committed card; control draw rules; why cards are only committed by the Owner
metadata:
  type: project
---

- Dataset definition = `dataset.json` next to the data (versioned approvals + markets with roles/pairings); the card's `## Definition` section is the committed copy. Cards for Owner-approved datasets are committed (Governor decision, ticket 03); `adhoc*` cards are gitignored. Never commit a card for a dataset the Owner did not approve (gate 7).
- Control rule: pattern-free = `wick_count <= 0` by default (screener's MIN_EVENTS is 3, so score is 0 anyway); band = volume within [v/2, v*2], widened to x4/x8 if empty, ratio recorded per control. Draw seeded per candidate (`f"{seed}/{candidate}"`) so later approvals don't reshuffle earlier controls.
- Pattern-free pool also demands full candle count (half-listed markets are trivially quiet).

**Why:** backtests compare candidates with controls; the control must be a fair negative example, and the whole choice must be reproducible from the card.
**How to apply:** when M3 backtest reports compare against controls, read pairings from `DatasetDefinition` (`paired_with`), not by position.
