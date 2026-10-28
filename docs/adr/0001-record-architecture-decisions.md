# Record architecture decisions as ADRs

Decisions in this repo are made across many agent sessions with no shared memory, so a decision that lives only in a chat is lost. We record decisions that are hard to reverse, surprising without context, and the result of a real trade-off as short ADRs in `docs/adr/`, numbered sequentially (`NNNN-slug.md`). An ADR can be one paragraph; add `Status`, `Considered Options` or `Consequences` only when they carry information. A superseded ADR stays, with `Status: superseded by ADR-NNNN`.
