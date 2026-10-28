# 08: Recorder

**Role:** platform-engineer

**Status:** ready-for-agent

**Blocked by:** 05, 06, 07

**What to build:** Approved datasets get recorded live: every trade, 1-second top-20 book snapshots and a gap log, surviving network hiccups. Completes M1.

Spec: [../spec.md](../spec.md)

- [ ] `ttp record start <dataset>` records all dataset markets; `ttp record stop <dataset>` (or Ctrl-C) stops cleanly; `ttp record status` shows what is running
- [ ] Trades and 1 s top-20 snapshots written to the dataset's Parquet partitions, readable by the DuckDB reader
- [ ] Gap log records disconnects, resyncs and missing intervals
- [ ] Auto-reconnect with backoff; Telegram alert via the notify module if a market stays disconnected beyond a threshold
- [ ] Tested with a fake feed; a short opt-in live run on one market is documented
