# 11: Verify M0-M2 independently

**Role:** verifier

**Status:** done

**Blocked by:** 07, 08, 10, 12, 14

**What to build:** Independent validation of everything built in M0-M2 against the spec and the tickets' acceptance criteria. Completes M2 (together with 09 at gate 2).

Spec: [../spec.md](../spec.md)

- [x] Independent tests at the seams: venue connector book maintenance, screener ranking, dataset/control selection, recorder output, engine
- [x] Full suite and lint run; commands and results pasted
- [x] Verdict pass/fail with each failure's expected vs actual and location, appended to this ticket under ## Answer

## Answer

verifier, 2026-10-28. Branch `verifier/11-verify-m0-m2` (from `governor/initial-infrastructure-spec` @ ba0921c).

**Verdict: pass.** I found no failing acceptance criterion in tickets 01-08, 10, 12 or 14.

New tests: 66 cases. I wrote them from the spec, the tickets and ADR-0006. I read the existing tests only to avoid duplicating them.

- `tests/test_verify_engine.py` (12 cases):
  - **No look-ahead.** A broker that fills every resting order on the *next* event it sees shows that an intent from event k never fills on event k.
  - **Callback order** is broker, then `on_fill`, then the event's own callback.
  - **Stopping.** `stop()` called from a callback or from `on_start` still runs `on_stop`, and its intents reach the broker. An empty feed still starts and stops.
  - **Replay ordering.** Klines, trades and `book_1s` are written through `DatasetStore` across a UTC midnight and replay in time order. Klines are stamped at their close, so a 23:59 candle never comes before the 23:59:30 trade. Events at the same time are ordered by market, then by data type, and the order is the same on every run.
  - **Window and book rows.** The replay window applies to event time for every data type. NULL book levels are dropped.
  - **Timers** fill quiet stretches and come before data at the same time. They reach `on_timer` with the clock at the tick time.
- `tests/test_verify_book.py` (21 cases):
  - **Hand-built diffs** cover each MEXC version rule:
    - a stale diff is dropped;
    - the first diff must bridge the snapshot (both straddling and exactly `last + 1`);
    - a snapshot the buffered diffs don't bridge is rejected as `stale_snapshot` and the buffer is kept;
    - a gap triggers a resync that replays the diff which revealed it;
    - duplicate or late diffs never roll quantities back;
    - swapped diffs cause a gap;
    - a zero quantity removes the level;
    - after a disconnect, an old snapshot cannot bring the book back.
  - **Property test** (12 seeds x 400 steps): a simulated venue keeps an uncrossed book and emits aggregated multi-version diffs, including aggressive orders. Its diffs arrive with drops, swaps, duplicates and lagging snapshots. Whenever `BookSync` says it is synced, its book equals the venue's book at that version and is never crossed.
  - **Mutation check:** making `on_diff` ignore gaps fails all 12 seeds, so the property test does catch that bug.
- `tests/test_verify_recorder.py` (9 cases): `Session` runs on a real `LiveBooks` with a scripted stream and a fake snapshot client.
  - **Book rows:** top-20 levels best-first, with the version they were sampled at, 82 columns. Levels a thin book lacks are stored as NULL.
  - **Gap log:** exactly `start, missing[start,synced), synced, gap, stale_snapshot, missing[gap,resync), synced, stop`, with venue times.
  - **Unsynced books:** no samples while a book is unsynced. A disconnect opens a `missing` interval that is closed at stop, with a tz-aware `until`.
  - **Alerts:** one per outage, one on recovery, another on a new outage. None if the market syncs before the threshold.
  - **Hourly parts** split at the hour and at the date. A re-flush adds only new rows, and several flushes within one hour merge into one file without duplicates.
- `tests/test_verify_screener.py` (15 cases):
  - **Gates:** one synthetic market passes every v3 gate. Breaking any single gate zeroes the score; the passing side of the same boundary is the control:
    - returned events: 2 vs 3, and 5 events with only 2 returned;
    - interval: 5 min vs exactly 10;
    - regularity 0, from intervals of 10, 10, 10 and 100 min;
    - wick vs base: 2.2% vs 2.5% over a 1.2% base;
    - active share: 0.4 vs 0.6.
  - A market where every candle is a spike has a NaN base and scores 0.
  - **Ranking:** `rank` gives the same table under 20 row shuffles, with ties broken by events, then name.
- `tests/test_verify_datasets.py` (9 cases):
  - **Control draw:**
    - identical when the stats rows are shuffled;
    - earlier controls don't change when later approvals are added, and later controls avoid every market already in the dataset;
    - over 30 seeds, controls are always pattern-free, inside the recorded band and never a candidate, including a zero-event candidate;
    - earlier candidates are never drawn as later controls.
  - **Band widening:** the band goes from x2 to x4 and the x4 is recorded on the control, while the approval keeps the requested band. The definition survives a JSON round trip.
  - **Klines:** re-downloading across midnight adds nothing, even when the venue returns extra rows. Gaps across midnight are detected, and only the gaps are re-requested.
  - **UTC:** timestamps given at +02:00 are stored in the right UTC date partitions and read back as UTC. Read bounds select by instant.
  - **Trades:** a re-download deduplicates the seam second, and `buyer_is_maker` maps to aggressor `sell`.

Commands (worktree, 2026-10-28):

```
uv run pytest              -> 198 passed, 6 deselected in 103.49s
uv run ruff check          -> All checks passed!
uv run ruff format --check -> 111 files already formatted
```

Observations for the Owner (not failures; no acceptance criterion is violated):

1. **Within one approval, the controls depend on the order the candidates are listed** (`src/ttp/data/datasets.py:194-219`). Each draw is seeded per candidate, but its pool excludes the earlier picks. In a probe, `approve ... C1 C2 C3` and `... C3 C2 C1` (same screen and seed) gave different controls for 194 of 200 seeds. The same command always gives the same result, but the module docstring ("same screen, candidates and seed always pick the same controls") reads as if order did not matter. A cheap fix, if wanted: draw in sorted candidate order.
2. **Approving a market that is already a control, as a candidate, is silently skipped** (`src/ttp/data/datasets.py:240-243`). The CLI prints "all markets already in it" (`src/ttp/cli.py:574`). The market stays a control, but the Owner may believe it became a candidate. Suggest an explicit message or an error.
3. **After sync, an overlapping diff is applied instead of being treated as a gap** (`src/ttp/venues/mexc/book.py:139`). The documented rule after the first diff is `fromVersion == previous toVersion + 1`. The code also accepts a diff whose `fromVersion` is at or below the current version, as long as its `toVersion` is newer. MEXC's diffs are aggregated with absolute quantities, so this is harmless (the property test agrees); it is only a strictness note.
