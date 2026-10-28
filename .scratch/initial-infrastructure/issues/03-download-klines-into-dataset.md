# 03: Download klines into a dataset

**Role:** quant-engineer

**Status:** ready-for-agent

**Blocked by:** 02

**What to build:** Kline history for a market lands in the project's dataset storage and can be queried, with a dataset card describing it. Completes M0.

Spec: [../spec.md](../spec.md)

- [ ] Connector fetches 1-minute klines with pagination over a requested range
- [ ] `ttp download klines <market> --days N [--dataset <name>]` writes Parquet partitioned by venue / market / data type / date under the gitignored `data/` root; re-running fills gaps without duplicating rows
- [ ] A DuckDB-based reader returns a market's klines for a time range as a DataFrame
- [ ] A dataset card is written per the docs/knowledge-base/README.md template (source, markets, type/resolution, range, location, collected by, gaps)
- [ ] Tests cover pagination, dedup/gap-fill and the reader using fixtures
