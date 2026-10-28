---
name: mexc-agg-trades-quirks
description: MEXC spot GET /api/v3/aggTrades and /api/v3/trades behaviour probed live 2026-10-28 (24 h depth, 1 h windows, inclusive bounds, no ids, newest first)
metadata:
  type: reference
---

- `aggTrades`: weight 1; `startTime` and `endTime` must be sent together (else code -1128); both inclusive; at most exactly 1 h apart (1 h + 1 ms gives -1127); `limit` max 1000; rows newest first; `T` is whole seconds; `a/f/l` ids are null. Pagination within an hour: drop the oldest second's rows and re-ask up to that second (see `MexcClient.agg_trades`).
- History depth is ~24 h for thin and busy markets alike (26 h back returns `[]`). Download daily or the prints are gone; the recorder (M1) is the real trade source.
- `trades` (recent trades) returns only the latest ~200 prints whatever `limit` says; ms timestamps, null ids, `tradeType` ASK/BID. Not usable for history.
- MEXC offers web downloads of klines and trades back to 2023-01-01 (docs page "Download Historical Market Data"); not an API, unexplored.
- Cold `httpx.Client` + 4 threads firing their first request at once gave `[SSL: TLSV1_ALERT_INTERNAL_ERROR]` on 3 of 4; the re-run was clean. If it recurs, warm the pool with one request before parallel work.
- `(T, p, m)` was unique in 1000 BTCUSDT rows (MEXC aggregates per price/side/second), so a row-level key is safe for dedup.
Related: [[mexc-klines-quirks]]
