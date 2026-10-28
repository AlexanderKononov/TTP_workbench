# 07: Live order book

**Role:** platform-engineer

**Status:** done

**Blocked by:** 01

**What to build:** The venue connector maintains a correct local order book for a MEXC market from the live WebSocket feed, recovering from gaps.

Spec: [../spec.md](../spec.md)

- [x] WebSocket client subscribes to MEXC depth diffs (and trades) for a market; book initialised from a REST snapshot and kept in sync by sequence/version numbers
- [x] A sequence gap or disconnect triggers resync; each event is reported so the recorder can write a gap log
- [x] `ttp watch <market>` shows live top-of-book and recent trades
- [x] Book maintenance tested against saved WebSocket message fixtures, including out-of-order and gap scenarios; no network in default tests
- [x] Own implementation, not the ccxt.pro MEXC book feed (ADR-0007)

## Comments

platform-engineer, 2026-10-28:

- **Layout** (all in `src/ttp/venues/mexc/`): `book.py` is the pure model (`OrderBook`, `BookSync` state machine, `DepthDiff`, `Trade`, `BookEvent`; no I/O), `proto.py` decodes the protobuf frames (pure), `stream.py` is the only I/O: `MexcMarketStream` (WebSocket, reconnect with backoff, PING) and `LiveBooks` (one `BookSync` per market, fetches REST snapshots on demand, yields trades, applied diffs and `BookEvent`s from one iterator). `MexcClient.depth()` added for the snapshot. Ticket 08's recorder drives `LiveBooks.events()` and samples `LiveBooks.book(market)` once a second; ticket 10 can lift `Trade`/`Level`/`OrderBook` into `core` when it defines events.
- **MEXC protocol** (spot v3 docs + `mexcdevelop/websocket-proto`, read 2026-10-28, verified live): streams `spot@public.aggre.depth.v3.api.pb@100ms@<SYMBOL>` and `spot@public.aggre.deals.v3.api.pb@100ms@<SYMBOL>`; pushes are binary protobuf `PushDataV3ApiWrapper`; snapshot `GET /api/v3/depth` (weight 3) gives `lastUpdateId`. Sync rule applied exactly as documented: drop diffs with `toVersion <= lastUpdateId`; first remaining diff needs `fromVersion <= lastUpdateId + 1`; thereafter `fromVersion == previous toVersion + 1`, otherwise gap -> new snapshot. Live checks on BTCUSDT and ADXUSDT showed versions chaining by exactly +1 and an uncrossed book after merging.
- **Protobuf without a toolchain:** the three messages we read hold only strings, varints and nested messages, so `proto.py` is a ~60-line schema-driven proto3 wire reader instead of `protobuf` + generated `_pb2` modules (no `protoc` on the PC, no 1,000-line generated files, no runtime-version coupling). Frames captured from the live feed (`tests/fixtures/mexc/ws_frames_*.json`) prove the field numbers. If MEXC changes the `.proto`, the schema dicts in `proto.py` are the place to update.
- **Snapshot timing:** the docs say "buffer the first diff, then snapshot". On a thin market the first diff can be minutes away, so `LiveBooks` snapshots as soon as the subscription is acknowledged; the version rules make that safe (diffs older than the snapshot are dropped, a snapshot older than the stream is rejected as `stale_snapshot` and refetched on the next diff). After a gap the snapshot is fetched immediately.
- **Events for the gap log** (`BookEvent.kind`): `synced` (version, buffered diffs replayed), `gap` (expected vs got), `stale_snapshot`, `snapshot_failed` (REST error, retried on the next diff), `disconnected`. Connection-level `StreamStatus`: `connected`, `subscribed`, `disconnected`, `error`.
- **Venue behaviour found live:** `limit=5000` on `/api/v3/depth` returns at most 2000 levels per side; the subscription ack lists streams in its own order; a refused subscription (unknown symbol) comes back with `code 0` and `msg "Not Subscribed successfully! [...]. Reason? Blocked!"`, so the client checks the text, not just the code; PONG is `{"id":0,"code":0,"msg":"PONG"}`; one connection takes 30 subscriptions, i.e. 15 markets (ticket 08 needs one connection per 15 markets).
- **Dependency:** `websockets` (sync client, threads) rather than asyncio: the rest of the package is synchronous and the recorder can run one thread per connection. No `protobuf` dependency.
- **`ttp watch`:** prints a line per top-of-book change, trade and sync event; `--seconds N` stops on its own (used by tests), otherwise Ctrl-C. A bad symbol exits 1 with the venue's message. Output is encoded with replacement so the cp1252 Windows console does not crash on MEXC's full-width characters.
- **Live test:** `uv run pytest -m live -k live_btcusdt` syncs the real BTCUSDT book and checks 10 applied diffs leave it uncrossed with no gap (passed 2026-10-28).
