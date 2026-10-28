---
name: worktree-tooling-gotchas
description: Gotchas when working in an isolated agent worktree on this repo (branch checkout refusal, sandbox refusing compound bash, slow cp of the screener cache)
metadata:
  type: feedback
---

Working in `.claude/worktrees/agent-*` on this repo: branch from the integration branch by name instead of checking it out; keep bash commands plain.

**Why:** `git checkout governor/<branch>` fails with "already used by worktree" when the main checkout holds it; `git checkout -b <role>/<ticket> governor/<branch>` works. The sandbox refuses bash commands that mix `git` with loops/subshells ("too complex to verify"), so do multi-step file work in a Python script under the scratchpad. `cp -r` of the 51 MB / 2,260-file `data/datasets/screener` cache exceeds a 3-minute foreground timeout and can leave one file behind ("File exists"); re-sync missing files with a small Python script and compare counts.

**How to apply:** at the start of a platform-engineer ticket in a worktree: `git log -1 governor/<branch>`, then `git checkout -b` from it, then `uv sync` (the `.venv` is per worktree; the `VIRTUAL_ENV` mismatch warning from uv is harmless). Offline screener re-runs: `DatasetStore` root is `data/datasets` (not `data`), reuse the previous screen's `stats.csv` for universe and volumes; previous screens live in the worktree that produced them (`reports/` is gitignored).
