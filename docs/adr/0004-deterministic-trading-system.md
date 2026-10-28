---
Status: accepted
---

# The trading system is deterministic; an execution service holds the credentials

Although the project is built with AI agents, the trading system itself runs no LLM: screening, signal generation, sizing, limit checks, order placement and monitoring are all plain code. Only the **execution service** holds venue credentials, and it places an order only when a strategy signal, an Owner confirmation and that confirmation's limits all allow it. We chose this because the first strategy (trading repeating spike patterns in low-liquidity markets with small sums) is mechanical and needs no judgement at runtime, and because deterministic code is testable, backtestable and auditable in ways an LLM in the money path is not.

## Consequences

- LLM agents add value at build time (designing, coding, testing, reviewing), not at run time.
- Putting an LLM into the runtime later (e.g. case narratives) is a new ADR, and it must stay out of the execution service.
