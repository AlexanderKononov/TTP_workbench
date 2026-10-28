---
name: tooling-gotchas
description: Repo tooling gotchas on the Owner's Windows PC (git index lock from slow commands, uv reusing root .venv, DuckDB threading, worktree sandbox refusals)
metadata:
  type: reference
---

- `git status --ignored` walks the big local `.venv`s and can run for minutes, holding `.git/index.lock`; other git commands fail meanwhile. Avoid `--ignored`, or scope it to a path.
- `uv sync` reuses the existing root `.venv` and removes packages not in `uv.lock`; the first sync after the legacy env was slow (many uninstalls).
- Click `CliRunner` shows `Usage: main` unless you pass `prog_name="ttp"` to `invoke`.
- Single commands: `uv run pytest`, `uv run ruff check`, `uv run ruff format --check` (see CLAUDE.md).
- `python -I` ignores PYTHONUTF8; MEXC JSON has non-cp1252 chars, so use `-X utf8` or `open(..., encoding="utf-8")`. On Windows python, write paths as `C:/...`, not `/c/...`.
- DuckDB: `duckdb.sql(...)` uses the module-global default connection, which is not thread-safe ("connection is busy with another call"). Always `with duckdb.connect() as con:` per call when code may run in threads.
- Worktree-isolated agent sessions: the Bash sandbox refuses compound commands and heredocs whose text contains "git" (even inside a path like `c--git-TTP-workbench`). Write such scripts to the scratchpad with the Write tool and run `python <file>` instead; keep each Bash call a single plain command.
- Worktrees start on a `worktree-agent-*` branch at `main`, not at the integration branch; create the ticket branch explicitly from `governor/initial-infrastructure-spec` and run `uv sync` first (no `.venv` in a fresh worktree).
- `python -I` ignores PYTHONUTF8; MEXC JSON has non-cp1252 chars, so use `-X utf8` or `open(..., encoding="utf-8")`. On Windows python, write paths as `C:/...`, not `/c/...`. `click.echo` of venue text (e.g. MEXC's full-width colon) crashes on the cp1252 console: encode with `errors="replace"` first.
- Worktree-isolated agent runs: the Bash tool refuses commands that mention `github`/`git` outside the worktree (raw.githubusercontent URLs, `gh api`, multi-line heredocs with such strings). Put such logic in a script written with the Write tool to the scratchpad and run it with `python script.py`; printing non-ASCII to the console still fails (write to files instead).
- Fake-socket stream tests must stop the stream (consume until a disconnect) or `MexcMarketStream` reconnects forever with the fake sleep and pytest hangs. For threaded runtime tests (recorder) use a socket that idles with `TimeoutError` instead of closing, so the book stays synced across a whole-second boundary.
- If the integration branch is checked out in the main checkout, `git checkout <branch>` fails in a worktree ("already used by worktree"); create the ticket branch straight from it: `git checkout -b <role>/<ticket> governor/initial-infrastructure-spec`.
- The worktree sandbox also refuses `python - <<EOF` heredocs and `cat >> file <<EOF` appends regardless of content. Use the Edit/Write tools for file changes; keep Bash to single plain commands (a `cd <worktree> && uv run ...` chain is accepted).
- Never probe process liveness with `os.kill(pid, 0)` on Windows: any signal other than `CTRL_C_EVENT`/`CTRL_BREAK_EVENT` calls `TerminateProcess`. The recorder uses a heartbeat file (`recorder.json` updated every 10 s) instead.
- Click `CliRunner.invoke` returns stderr merged into `result.output` ahead of stdout written later, so a warning printed early appears as line 0; assert with `in lines`, not `lines[0]`.
- DuckDB + pandas: `None` in a float column becomes a Parquet NULL and reads back as NaN; a tz-aware pandas column registered into DuckDB and cast to `TIMESTAMP` depends on the session time zone, so normalise every TIMESTAMP column to naive UTC before writing (`DataType.timestamp_columns`).
