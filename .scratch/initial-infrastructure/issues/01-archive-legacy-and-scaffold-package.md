# 01: Archive legacy code and scaffold the ttp package

**Role:** platform-engineer

**Status:** done

**Blocked by:** None (can start immediately)

**What to build:** Legacy code moves out of the way and an empty but working `ttp` package exists that every later ticket builds in, following docs/architecture.md.

Spec: [../spec.md](../spec.md)

- [x] All pre-pivot code (root stubs, Alpaca code, `data/` Yahoo pipeline incl. trades_example, `tearsheet/`, root `requirements.txt`, `package.json`/lockfile, `main.py`, `utils.py/`) moved to `archive/` with `git mv`; `docs/legacy.md` becomes `archive/README.md` and links in CLAUDE.md/README/CONTEXT are updated
- [x] Dev container no longer auto-starts the tearsheet app; it installs uv and syncs the project
- [x] `pyproject.toml` + `uv.lock` at repo root; package under `src/ttp/` with the subpackages from docs/architecture.md (empty `__init__` modules are fine); Python >= 3.11
- [x] `uv run ttp --help` prints a CLI (subcommands added by later tickets)
- [x] `uv run pytest` passes with at least one smoke test; `uv run ruff check` and `uv run ruff format --check` pass
- [x] Root `data/` and `reports/` are gitignored; the Working conventions section of CLAUDE.md names the single test and lint commands

## Comments

platform-engineer, 2026-10-28:

- **CLI library: click** (`click>=8.1,<9`). One small, stable dependency with no transitive deps; typer adds rich/shellingham and type-hint magic we don't need. Click's explicit decorators keep subcommands for later tickets (`ttp screen`, `ttp dataset approve`, `ttp record ...`) plain and easy to test with `CliRunner`.
- **Build backend: `uv_build`** (uv's native backend, `src/` layout default). Dev tools live in the `dev` dependency group so `uv sync` installs them; `ruff` is pinned to a minor (`<0.18`) because ruff changes lint/format output between minors.
- **Ruff:** defaults plus `I` (import sorting), `target-version = py311`, `archive/` excluded. Pytest uses `testpaths = ["tests"]`, so archived test suites (tearsheet, Alpaca smoke check) never get collected from the root.
- **Archived local data:** the Owner's gitignored Yahoo data (`data/raw/`, `data/processed/`, `data/metadata.db`) was moved with plain `mv` to `archive/data/` next to its pipeline (gitignore updated), so root `data/` starts clean for recorded datasets. Nothing was deleted.
- **Archived code paths not rewritten:** `archive/config/settings.py` now loads `.env` from `archive/` (not the repo root) and the archived scripts still assume their old cwd. They are reference code; `archive/README.md` notes this. Fix only if a piece gets revived.
- **Root `.venv`:** `uv sync` reused the existing root `.venv` (Python 3.13) and removed the legacy packages installed there (streamlit, yfinance, ...). Recreate a legacy env from `archive/requirements.txt` if needed.
- **Dev container:** installs uv with `pip3 install --user uv` and runs `uv sync --locked`; no app auto-start, no port forward. Not tested in an actual container build here.
- `.claude/hooks/telegram_notify.py` was reformatted by `ruff format` (whitespace/line wrapping only) so the repo-wide `ruff format --check` passes.
