# TTP_workbench

Workbench for a **human-confirmed crypto trading system** focused on low-liquidity venues: agents screen markets, propose strategies backed by backtests, and present cases; the owner sets budget and limits and confirms execution.

Status: initial infrastructure. The `ttp` package lives in `src/ttp/`; run `uv sync`, then `uv run ttp --help`. Tests: `uv run pytest`.

## Start here

- [CONTEXT.md](CONTEXT.md): vision, status, open questions
- [GLOSSARY.md](GLOSSARY.md): domain language
- [docs/adr/](docs/adr/): architecture decisions
- [docs/agents/roles.md](docs/agents/roles.md): agent roles and access levels
- [docs/knowledge-base/](docs/knowledge-base/): venues, strategies, datasets, backtests
- [.scratch/](.scratch/): specs and tickets in progress
- [archive/](archive/README.md): pre-pivot code (tearsheet app, Yahoo data pipeline, bot stubs)
