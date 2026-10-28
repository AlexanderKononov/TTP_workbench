# .scratch

Agent working area: specs, tickets, wayfinding maps and research drafts, one folder per feature or effort. Committed to git so work survives between sessions.

```
.scratch/
└── <feature-slug>/
    ├── spec.md            # what we're building and why
    ├── map.md             # wayfinding map (optional)
    ├── notes.md           # research / grilling notes (optional)
    └── issues/
        ├── 01-<slug>.md   # one ticket per file, Status: line at top
        └── 02-<slug>.md
```

Full conventions: [docs/agents/issue-tracker.md](../docs/agents/issue-tracker.md).

- Content that proves durable moves out: terms → `GLOSSARY.md`, decisions → `docs/adr/`, verified knowledge → `docs/knowledge-base/`.
- Keep secrets, API keys and account data out of here; this folder is committed.
- First planned effort: `project-scope/` (output of the scoping grilling session).
