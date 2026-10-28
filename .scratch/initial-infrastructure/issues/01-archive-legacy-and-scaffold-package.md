# 01: Archive legacy code and scaffold the ttp package

**Role:** platform-engineer

**Status:** ready-for-agent

**Blocked by:** None (can start immediately)

**What to build:** Legacy code moves out of the way and an empty but working `ttp` package exists that every later ticket builds in, following docs/architecture.md.

Spec: [../spec.md](../spec.md)

- [ ] All pre-pivot code (root stubs, Alpaca code, `data/` Yahoo pipeline incl. trades_example, `tearsheet/`, root `requirements.txt`, `package.json`/lockfile, `main.py`, `utils.py/`) moved to `archive/` with `git mv`; `docs/legacy.md` becomes `archive/README.md` and links in CLAUDE.md/README/CONTEXT are updated
- [ ] Dev container no longer auto-starts the tearsheet app; it installs uv and syncs the project
- [ ] `pyproject.toml` + `uv.lock` at repo root; package under `src/ttp/` with the subpackages from docs/architecture.md (empty `__init__` modules are fine); Python >= 3.11
- [ ] `uv run ttp --help` prints a CLI (subcommands added by later tickets)
- [ ] `uv run pytest` passes with at least one smoke test; `uv run ruff check` and `uv run ruff format --check` pass
- [ ] Root `data/` and `reports/` are gitignored; the Working conventions section of CLAUDE.md names the single test and lint commands
