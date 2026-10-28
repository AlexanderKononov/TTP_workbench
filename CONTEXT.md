# Project Context

The "why" and "where are we" of this repo. Domain terms are defined in [GLOSSARY.md](GLOSSARY.md); decisions are recorded in [docs/adr/](docs/adr/). Update this file when the vision, status or open questions change.

## Vision

A trading assistant for **crypto on low-liquidity venues** (small exchanges and thin markets where spreads, slippage and order-book depth dominate outcomes). The system does the search and analysis work; the owner keeps the decision.

The intended loop:

1. **Screen**: scan venues and markets to find candidate coins.
2. **Propose**: pick or adapt a strategy for each candidate and back it with a backtest.
3. **Present a case**: a self-contained argument for the trade (thesis, strategy, backtest evidence, risks, liquidity constraints, suggested size).
4. **Confirm**: the owner reviews the case, sets budget and limits, and confirms or rejects.
5. **Execute & monitor**: only confirmed cases execute, within their limits.

## Pillars

- **Human-confirmed execution**: [ADR-0002](docs/adr/0002-human-confirmed-execution.md).
- **Multi-agent with least privilege**: separate agent roles with distinct responsibilities and access levels: [ADR-0003](docs/adr/0003-least-privilege-agent-roles.md), [docs/agents/roles.md](docs/agents/roles.md).
- **Reproducible backtesting**: backtest code lives in this repo, and every result is traceable to the data it used.
- **Documented knowledge**: a detailed knowledge base about venues, market behaviour, strategies and datasets: [docs/knowledge-base/](docs/knowledge-base/).

## How it's built

- One repo, one trading system. Claude agents are **roles** in two families of expertise: **dev roles** build and validate the code, data and infrastructure; **trading roles** work with the Owner on strategy, risk and sizing, and plan and control the build. See [GLOSSARY.md](GLOSSARY.md).
- The trading system itself is deterministic, with no LLM at runtime ([ADR-0004](docs/adr/0004-deterministic-trading-system.md)).
- First strategy: find robot-like **spike patterns** that repeat in low-liquidity markets and trade them with small sums.
- Dev-system autonomy: **Level 1** (interactive sessions, the Governor dispatches roles, tickets in `.scratch/`). Moving up a level is an Owner-approved decision.
- Notifications and confirmations go through **Telegram**, with separate bots for dev work and for trading.
- **Budget constraint:** a Claude Max plan for now, likely downgraded later. Stay token-frugal: concise outputs, few and focused sub-agents, rely on skills and docs rather than re-deriving.

## Current status (2026-10-27)

- **Phase: initial infrastructure.** Venue: MEXC spot ([ADR-0007](docs/adr/0007-mexc-spot-first-venue.md)). Structure: [docs/architecture.md](docs/architecture.md). First strategy: `up-spike-harvest`. Milestones M0 (venue and data feasibility), M1 (recorder), M2 (strategy interface and screener), M3 (backtest), M4 (paper trading), M5 (execution service at minimum size), M6 (first live case: $50). Spec and tickets: `.scratch/initial-infrastructure/`.
- **Pre-pivot code** in the repo (equities/Alpaca bot stubs, a Yahoo Finance data pipeline, a working trade tearsheet app) is archived under `archive/` and described in [archive/README.md](archive/README.md). It is kept for reference and possible reuse.

## Open questions for the scoping session

Starting points only; the grilling session owns the real list.

- **Venues**: which exchanges/brokers first? CEX, DEX, or both? What APIs and data do they expose?
- **"Low liquidity"**: what thresholds (volume, depth, spread) define the target universe?
- **Screening**: what signals make a coin a candidate? How often does screening run?
- **Strategies**: which strategy families are in scope (momentum, mean reversion, market making, listing/event plays…)?
- **Case format & confirmation channel**: what must a case contain, and how does the Owner confirm it (Telegram buttons, CLI, Streamlit)? The channel must authenticate the Owner and record budget, limits and expiry.
- **Limit values**: default budget and limit values per stage; any global exposure cap across cases?
- **Execution**: order types, partial fills, who monitors open positions, what triggers an exit?
- **Backtesting**: engine (hand-rolled, backtrader, vectorbt…), and how to model thin order books and slippage honestly.
- **Data**: sources for historical OHLCV/order-book/trade data, storage layout, retention.
- **Legacy code** (now in `archive/`): reuse (e.g. tearsheet for post-trade analysis, `data/` pipeline patterns) or delete.
- **Runtime**: where the system runs (local, server, cloud), and how it is scheduled.
