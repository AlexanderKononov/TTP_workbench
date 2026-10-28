# Agent Roles & Gates

How the Claude agents in this repo are organised. Principle: [ADR-0003](../adr/0003-least-privilege-agent-roles.md). Autonomy: **Level 1** (interactive; the Governor dispatches roles; tickets in `.scratch/`).

## Roles

The **Governor** is the main interactive session: it plans with the Owner, dispatches roles, and is the only agent that asks the Owner for decisions. Each other role is defined in `.claude/agents/<role>.md` and keeps its own committed memory in `.claude/agent-memory/<role>/`.

| Role | Family | Owns | Model |
|---|---|---|---|
| `strategist` | trading | Strategy design, spike-pattern definitions, risk, sizing, venue/coin research, on-demand review of results | Opus |
| `platform-engineer` | dev | Venue connectors, screener, trading engine, execution service, live monitoring + Telegram reports | Opus |
| `quant-engineer` | dev | Market data pipeline + dataset cards, backtest engine, strategies as code | Opus |
| `verifier` | dev | Tests and validation of others' work; writes tests, never production code | Opus |

Split a role when its memory or scope outgrows it. The first planned split is a Sonnet developer role for simple tasks, to cut cost.

No role holds venue credentials or places orders; the execution service does ([ADR-0004](../adr/0004-deterministic-trading-system.md)). Runtime monitoring is trading-system code, not an agent.

Boundaries are enforced by each role's `tools` list plus path rules in its prompt, and checked at the merge gate. `strategist` writes only to `.scratch/` and knowledge-base drafts; `verifier` writes only under `tests/`. Add a blocking hook only after a role actually breaks a boundary.

## Workflow

- Each ticket carries a `Role:` line, set in the ticket breakdown and approved at gate 3; the Governor dispatches by it.
- Each ticket is worked on a branch `<role>/<ticket-slug>`; the Governor opens a GitHub pull request. `main` is branch-protected: nobody, agents included, pushes to it directly.
- An approved strategy lives at `src/ttp/strategies/<name>/STRATEGY.md`, next to its code (pattern, entry/exit, sizing, risk, parameters, current stage); `.scratch/` holds only drafts.

## Knowledge

- **Role memory** (`.claude/agent-memory/<role>/`): how-to-work lessons. The role writes it itself.
- **Knowledge base** ([docs/knowledge-base/](../knowledge-base/)): verified facts. It grows only through changes the Owner merges.
- **`.scratch/`**: drafts, specs, tickets. Anyone writes freely.

## Gates

The Governor stops for the Owner at each of these. They are the minimum; early in the project the Governor should also ask at any other pivotal moment.

1. **Scope/spec approved**: before tickets are written.
2. **Strategy definition approved**: before it is coded.
3. **Ticket breakdown approved**: before implementation starts.
4. **Merge to `main`**: the Owner reviews the diff.
5. **Stage promotion**: backtest → paper → live ([ADR-0005](../adr/0005-three-stage-promotion.md)).
6. **Autonomy level change**.
7. **Dataset approval**: the screener's candidates (with price charts of recent hours and pattern statistics) are approved before history is downloaded or recording starts.

Dev roles build within [docs/architecture.md](../architecture.md).

In the trading system, the gate is the **confirmation** of a case ([ADR-0002](../adr/0002-human-confirmed-execution.md)).

## Notifications

Telegram, with separate bots for dev work and for the trading system. At Level 1 the dev bot is one-way: Claude Code's `Notification` hook (`.claude/hooks/telegram_notify.py`) alerts the Owner when a session needs input or sits waiting. Setup: create a bot with @BotFather, then set `TELEGRAM_DEV_BOT_TOKEN` and `TELEGRAM_DEV_CHAT_ID` in `.env` (see `.env.example`). Without them the hook does nothing.
