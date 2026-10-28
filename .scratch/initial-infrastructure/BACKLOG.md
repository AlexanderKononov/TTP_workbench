# Backlog (not yet ticketed)

Items surfaced during M0–M2 that the Governor deferred. Promote to a ticket when its milestone starts.

- **MEXC bulk history (web download, not API):** klines + trades back to 2023-01-01 exist as a non-API download (found in ticket 06). Could give long history for approved markets, since the API serves only 30 d of klines and ~24 h of trades. Explore before M3 calibration if 30 days proves too short.
- **Screener v3 base-activity gate:** pending the strategist's verdict in ticket 13.
- **httpx cold-connection TLS errors** on the first parallel request burst (ticket 06): warm the pool with one request before fan-out if it recurs.
- **Ticket 07 `ttp watch`** is line-based; a refreshing display is a nicety for later.
- **M3–M6 tickets:** cut after the Owner has seen M2 (spec §Solution).
