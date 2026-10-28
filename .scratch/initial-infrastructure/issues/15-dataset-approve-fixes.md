# 15: Dataset approval — order-independent controls, no silent skips

**Role:** quant-engineer

**Status:** ready-for-agent

**Blocked by:** 11

**What to build:** `ttp dataset approve` gives the same controls whatever order the Owner lists the candidates in, and refuses (with a clear error) to approve a market that is already a control, instead of silently keeping it as a control. Findings 1 and 2 of the verifier in ticket 11 (`## Answer`).

Spec: [../spec.md](../spec.md)

- [ ] Controls are drawn in sorted candidate order so `C1 C2 C3` and `C3 C2 C1` produce identical pairings for every seed; the verifier's `tests/test_verify_datasets.py` gets a test for this (the verifier's own file may be extended for this one case)
- [ ] Approving a market that is already a control in the dataset raises a `ValueError` surfaced as a CLI error naming the market and its role; nothing is written
- [ ] Docstrings of `approve`/`select_controls` state the order guarantee
- [ ] Full suite, ruff check and format pass
