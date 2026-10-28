# 06: Dataset approval with control markets

**Role:** quant-engineer

**Status:** ready-for-agent

**Blocked by:** 04

**What to build:** The Owner approves screener candidates with one command; the system builds a versioned dataset with matched control markets and their history (gate 7).

Spec: [../spec.md](../spec.md)

- [ ] `ttp dataset approve <screen-id> <market>... --name <dataset>` creates a versioned dataset definition listing candidates and controls
- [ ] One control per candidate, chosen at random (seeded, reproducible) from the same 24h-volume band among markets the screen scored as pattern-free
- [ ] Kline and trade history available from MEXC is downloaded for all dataset markets
- [ ] Dataset card written/updated; `ttp dataset list` and `ttp dataset show <name>` work
- [ ] Tests cover control selection and dataset definition with fixtures
