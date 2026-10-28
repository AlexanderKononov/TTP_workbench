# 15: Dataset approval — order-independent controls, no silent skips

**Role:** quant-engineer

**Status:** done

**Blocked by:** 11

**What to build:** `ttp dataset approve` gives the same controls whatever order the Owner lists the candidates in, and refuses (with a clear error) to approve a market that is already a control, instead of silently keeping it as a control. Findings 1 and 2 of the verifier in ticket 11 (`## Answer`).

Spec: [../spec.md](../spec.md)

- [x] Controls are drawn in sorted candidate order so `C1 C2 C3` and `C3 C2 C1` produce identical pairings for every seed; the verifier's `tests/test_verify_datasets.py` gets a test for this (the verifier's own file may be extended for this one case)
- [x] Approving a market that is already a control in the dataset raises a `ValueError` surfaced as a CLI error naming the market and its role; nothing is written
- [x] Docstrings of `approve`/`select_controls` state the order guarantee
- [x] Full suite, ruff check and format pass

## Comments

quant-engineer, 2026-10-28. Branch `quant-engineer/15-dataset-approve-fixes`.

- `select_controls` draws in `sorted(set(candidates))` order and returns the picks in that order; `approve` therefore lists the added markets sorted by candidate, not in command-line order. The CLI output follows that order.
- `approve` raises `ValueError("<market> is already in dataset '<name>' as the control for <candidate>; it cannot be approved as a candidate")` before any change; the existing `except ValueError` in `dataset_approve` already turns it into a `ClickException`, so `cli.py` needed no change. A candidate that is already a candidate is still skipped silently (unchanged behaviour).
- Tests: order-independence case added to `tests/test_verify_datasets.py`; the control-as-candidate error is covered at module level and through the CLI in `tests/test_dataset_approval.py`.
- `uv run pytest` -> 201 passed, 6 deselected; `uv run ruff check` -> All checks passed; `uv run ruff format --check` -> 114 files already formatted.
