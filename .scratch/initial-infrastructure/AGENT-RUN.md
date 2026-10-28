# Run rules for M0–M2 tickets (Owner away)

- Read your ticket, `spec.md`, `docs/architecture.md`, and the ADRs it touches. Use `GLOSSARY.md` terms in code and docs.
- Start from branch `governor/initial-infrastructure-spec` (the integration branch, clean tree). Create `<role>/<ticket-file-name-without-.md>` and commit there; messages end with `Co-Authored-By: Claude Fable 5.1 <noreply@anthropic.com>`. Do not push, merge, or touch `main`.
- Work test-first at the ticket's seam; keep code minimal and idiomatic; reuse what earlier tickets built (`src/ttp/`, `tests/`). Default tests never hit the network; live checks use the `live` pytest marker.
- Commands: `uv run pytest`, `uv run ruff check`, `uv run ruff format --check`. All must pass before you finish. Add dependencies with `uv add`.
- Do not ask the Owner questions. Decide with best practice and the ADRs; record decisions under `## Comments` at the bottom of your ticket. Product questions you can't settle: mark `QUESTION FOR OWNER` there and take the conservative option.
- Finish: tick the met criteria, set `**Status:** done`, commit, and report: branch, commits, test/lint commands with results, anything unmet, anything the Owner should check.
- You may be running in an isolated git worktree (a copy of the repo). Branches are shared with the main checkout, so create your ticket branch as usual and commit there; run `uv sync` first if `.venv` is missing. Never `git checkout` another branch in a worktree someone else may be using.
