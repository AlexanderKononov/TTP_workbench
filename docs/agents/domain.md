# Domain Docs

How agents consume this repo's domain documentation. Layout: **single-context**.

## Before exploring, read these

- **`GLOSSARY.md`** at the repo root.
- **`docs/adr/`**: ADRs that touch the area you're about to work in.
- **`CONTEXT.md`** when the task touches scope, goals or priorities.

## Use the glossary's vocabulary

When your output names a domain concept (spec, ticket title, case, test name, code identifier), use the term as defined in `GLOSSARY.md`, not a synonym it lists under `_Avoid_`. A concept missing from the glossary is a signal: either the language is invented (reconsider) or there's a real gap (note it for `/domain-modeling`).

## Flag ADR conflicts

If your output contradicts an existing ADR, surface it explicitly rather than silently overriding:

> _Contradicts ADR-0002 (human-confirmed execution), but worth reopening because…_
