---
name: worktree-inputs-may-be-elsewhere
description: Dispatched strategist worktrees can be checked out at main, missing the spec branch; find inputs in the sibling worktree the task names and write full files for the Governor to commit
metadata:
  type: feedback
---

When a task says "you are at the tip of `governor/initial-infrastructure-spec`" but `.scratch/<feature>/` or `src/ttp/` is missing, check the sibling worktree path given in the task (e.g. `C:\git\TTP_workbench\.claude\worktrees\<other-agent>\`) before concluding inputs are absent. Avoid `Glob` on `C:\git\TTP_workbench` root with `**` patterns: it times out (large `.venv`/data trees); target a worktree subfolder.

**Why:** On 2026-10-28 the strategist worktree was at `main`; all tickets, ADR-0005/0007, the screener code and the screen report lived only in the sibling worktree.

**How to apply:** Read from the sibling, write deliverables into your own worktree with full file content (tickets included, verbatim plus your appended comment), and say so in the ticket's `## Comments` and in the report so the Governor can commit cleanly.
