---
name: venue-research-howto
description: How to research venue docs efficiently (MEXC/Hyperliquid URL quirks, what WebFetch can't do)
metadata:
  type: feedback
---

Venue doc research lessons (from 2026-10-28 MEXC vs Hyperliquid comparison).

- MEXC docs: per-page URLs under `https://www.mexc.com/api-docs/spot-v3/<section>/<page>` work; `general-info` and `spot-account-trade` paths 404, use `https://www.mexc.co/api-docs/spot-v3/introduction`. Search with `allowed_domains: [mexc.com]` to find exact page URLs first.
- Hyperliquid docs: `hyperliquid.gitbook.io/hyperliquid-docs/...` pages fetch cleanly; min $10 notional is not on the official tick/lot page.
- WebFetch cannot count markets from big JSON endpoints and there is no Bash for strategist; universe counts (e.g. markets < $100k 24h vol) must be delegated to a dev role.
- MEXC official fee page not found via search; fee numbers stayed unverified.

**Why:** saves several failed fetches next time.
**How to apply:** any venue/knowledge-base research task.
