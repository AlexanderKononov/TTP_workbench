# CLAUDE.md

Guidance for Claude Code and its sub-agents working in this repository.

## What this repo is becoming

A **human-confirmed crypto trading system** for low-liquidity venues: agents screen the market, find candidate coins, propose a strategy, and present a case; the owner sets budget and limits and confirms before anything executes. The repo also holds backtesting code, the provenance of the data used for backtests, and the project knowledge base.

Scope is still being defined (a grilling session is next). Read [CONTEXT.md](CONTEXT.md) for vision, current status and open questions before proposing design or code.

## Hard rules

These hold for every agent, every role, every task:

- **Execution is human-confirmed.** Live orders happen only inside a case the Owner confirmed, within its budget, limits and expiry; stopping never needs confirmation. See [ADR-0002](docs/adr/0002-human-confirmed-execution.md).
- **The trading system is deterministic.** No LLM in the runtime path; only the execution service holds venue credentials. No agent role ever does. See [ADR-0004](docs/adr/0004-deterministic-trading-system.md).
- **Stop at the gates.** The Governor stops for the Owner at every gate in [docs/agents/roles.md](docs/agents/roles.md), and early on at any other pivotal moment too.
- **Work through pull requests.** One branch per ticket, merged by the Owner; nothing is pushed to `main` directly.
- **Secrets live in `.env` / Streamlit secrets only.** Reference them by variable name; keep their values out of code, logs, specs and commits.
- **Backtest results cite their data.** Every backtest records which dataset (source, venue, symbols, resolution, date range) it ran on; see [docs/knowledge-base/](docs/knowledge-base/).

## Where things live

| Path | Holds |
|---|---|
| [CONTEXT.md](CONTEXT.md) | Project vision, goals, status, open questions |
| [GLOSSARY.md](GLOSSARY.md) | Domain language. Use its terms; avoid its `_Avoid_` synonyms |
| [docs/adr/](docs/adr/) | Architecture decisions. Read the ones touching your area; flag conflicts explicitly |
| [docs/agents/roles.md](docs/agents/roles.md) | Roles, gates, branch/PR workflow. **Read before dispatching or acting as a role** |
| [docs/agents/](docs/agents/) | Issue tracker and domain-doc rules |
| `src/ttp/strategies/<name>/STRATEGY.md` | Approved strategy definition, next to its code |
| [docs/knowledge-base/](docs/knowledge-base/) | Venues, markets, strategies research, dataset cards |
| [.scratch/](.scratch/) | Agent working area: specs, tickets, maps, per feature |
| [docs/legacy.md](docs/legacy.md) | Pre-pivot code (`tearsheet/`, `data/`, root bot stubs). Read before touching those dirs |

## Working conventions

- No shared build/lint/test command exists yet; there is no linter or formatter config. Each legacy piece runs from its own directory (see [docs/legacy.md](docs/legacy.md)).
- Platform is Windows (PowerShell primary); a Python 3.11 dev container also exists in `.devcontainer/`.
- Gitignored and absent from fresh checkouts: `.env`, `.streamlit/`, `data/raw/`, `data/metadata.db`.

## Agent skills

### Issue tracker

Local markdown under `.scratch/<feature-slug>/`. See [docs/agents/issue-tracker.md](docs/agents/issue-tracker.md).

### Domain docs

Single-context: root `GLOSSARY.md` + `docs/adr/`. See [docs/agents/domain.md](docs/agents/domain.md).
