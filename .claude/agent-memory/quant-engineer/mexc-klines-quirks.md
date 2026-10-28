---
name: mexc-klines-quirks
description: MEXC spot GET /api/v3/klines behaviour probed live 2026-10-28 (page cap, start/end semantics, 30-day 1m depth, zero-volume fill)
metadata:
  type: reference
---

- Weight 1 per request; max 500 rows even if `limit=1000`.
- `startTime` alone (or `endTime` alone) is IGNORED: MEXC returns the latest candles. Always send both.
- Rows returned for open time in `[startTime, endTime)`; the current unclosed minute is included if in range.
- 1m history depth is exactly 30 days; older ranges return `[]` (HTTP 200). Paginators must skip empty pages, not stop.
- Idle minutes are returned as flat candles with volume "0", so a missing minute is a real venue gap.
- Bad symbol / interval -> HTTP 400 `{"msg":"Invalid symbol.","code":-1121}`.
- 30 days for one market = ~87 requests, ~37 s end to end incl. Parquet writes.
Related: [[uv-venv-corruption]]
