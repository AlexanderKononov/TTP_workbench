---
Status: accepted (principle); role list pending
---

# Agent roles with least-privilege access, none holding venue credentials

Claude agents in this repo are **roles**: dev roles (build, test, validate code, data and infrastructure) and trading roles (help the Owner design strategies, risk and sizing, and plan and control the build). All roles work in the same repo on the same code; they are not separate systems. Each role gets only the tools it needs, set in its `.claude/agents/<role>.md` frontmatter. **No role ever holds venue credentials or places orders**; that belongs to the deterministic execution service ([ADR-0004](0004-deterministic-trading-system.md)). We chose role separation over one all-powerful agent to keep each role's prompt, tools and memory narrow enough to review.

The concrete roles live in [docs/agents/roles.md](../agents/roles.md).
