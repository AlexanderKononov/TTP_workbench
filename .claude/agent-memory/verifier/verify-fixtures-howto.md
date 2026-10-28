---
name: verify-fixtures-howto
description: How to build verifier fixtures in TTP (BookSync property sim, recorder Session without threads, screener gate series) and env quirks (test file naming, worktree bash limits)
metadata:
  type: feedback
---

Reusable how-tos from ticket 11 (M0-M2 verification, 2026-10-28):

- Test files must be named `tests/test_*.py` (pytest default), not `verify_*.py`; use `tests/test_verify_<area>.py`.
- Recorder `Session` without threads: real `LiveBooks(markets, FakeClient, Script)` where FakeClient has `depth(market)` popping queued `BookSnapshot`s and Script has `messages()`; for alert-only tests a `SimpleNamespace(syncs=..., book=...)` over `BookSync` suffices.
- BookSync property test: simulated uncrossed venue on an integer tick grid emitting aggregated diffs, delivered with drops/swaps/dups and lagging snapshots; check book == venue history at `sync.version`. Validate teeth with a monkeypatch mutation script in the scratchpad.
- Screener gates: synthetic 1 m series (flat base with small range, sweeps at chosen minutes); an "unreturned" spike needs close ~54% up the rise so it is still a spike candle (upper wick >= 2%).
- Worktree-isolated bash refuses compound commands that mix `git` with heredocs/loops; run git commands alone, write scratch scripts with the Write tool.

**Why:** these took trial and error; re-deriving them costs tokens.
**How to apply:** start from these patterns when verifying engine/book/recorder/screener work.
