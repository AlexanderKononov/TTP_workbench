# 05: Screen summary on Telegram

**Role:** platform-engineer

**Status:** done

**Blocked by:** 04

**What to build:** The screener summary and charts reach the Owner's phone via the dev Telegram bot.

Spec: [../spec.md](../spec.md)

- [x] A notify module sends text and photos via the Telegram Bot API using `TELEGRAM_DEV_BOT_TOKEN` / `TELEGRAM_DEV_CHAT_ID` from the environment or `.env` (never logged)
- [x] `ttp screen --notify` sends the summary table and top candidates' charts
- [x] Missing credentials produce a clear warning, not a crash
- [x] Tests use a fake HTTP layer; no real messages in the default suite

## Comments

- platform-engineer (2026-10-28): built `src/ttp/notify/telegram.py`. `TelegramNotifier(config)` exposes `send_text(text, monospace=False)` (splits at Telegram's 4096-char limit on line breaks; `monospace` wraps each piece in an HTML `<pre>` block so tables stay aligned on a phone) and `send_photo(path, caption)`. Errors raise `NotifyError`; the token is redacted from messages and httpx's INFO request log (which prints the URL, i.e. the token) is filtered for Telegram URLs. Ticket 08's recorder can reuse it as-is for alerts.
- Bots are selected by env-var prefix: `load_bot_config(DEV_BOT)` reads `TELEGRAM_DEV_BOT_TOKEN` / `TELEGRAM_DEV_CHAT_ID`; `TRADING_BOT` (`TELEGRAM_TRADING_*`, placeholders added to `.env.example`) is for M5. The process environment wins over a `.env` in the working directory (the CLI is run from the repo root, like `data/` and `reports/`). The `.claude/hooks/telegram_notify.py` hook keeps its own copy of the lookup so hooks stay dependency-free.
- `ttp screen --notify` sends one monospace summary (window, universe, top-N table with score, events, typical wick, interval, regularity, 24h volume) and then one chart per top candidate with a stats caption. Missing credentials print a warning on stderr and exit 0 after the report is written; a failed send exits 1 via `ClickException`, since the Owner explicitly asked for delivery. No extra dependency (httpx multipart upload).
- Tests fake the Bot API with `httpx.MockTransport` and inject `obj["telegram"]`, `obj["env"]`, `obj["env_file"]` into the CLI so the default suite can never read a real `.env` or send. One opt-in `live` test pings the dev bot.
- Live check: `uv run ttp screen --notify --max-volume 3000 --min-volume 2500 --hours 6 --top 3` scanned 5 markets and reported `sent to Telegram: summary and 3 charts` (screen id 20261028-085236).
