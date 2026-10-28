---
name: tooling-gotchas
description: Repo tooling gotchas on the Owner's Windows PC (git index lock from slow commands, uv reusing root .venv)
metadata:
  type: reference
---

- `git status --ignored` walks the big local `.venv`s and can run for minutes, holding `.git/index.lock`; other git commands fail meanwhile. Avoid `--ignored`, or scope it to a path.
- `uv sync` reuses the existing root `.venv` and removes packages not in `uv.lock`; the first sync after the legacy env was slow (many uninstalls).
- Click `CliRunner` shows `Usage: main` unless you pass `prog_name="ttp"` to `invoke`.
- Single commands: `uv run pytest`, `uv run ruff check`, `uv run ruff format --check` (see CLAUDE.md).
