# 05: Screen summary on Telegram

**Role:** platform-engineer

**Status:** ready-for-agent

**Blocked by:** 04

**What to build:** The screener summary and charts reach the Owner's phone via the dev Telegram bot.

Spec: [../spec.md](../spec.md)

- [ ] A notify module sends text and photos via the Telegram Bot API using `TELEGRAM_DEV_BOT_TOKEN` / `TELEGRAM_DEV_CHAT_ID` from the environment or `.env` (never logged)
- [ ] `ttp screen --notify` sends the summary table and top candidates' charts
- [ ] Missing credentials produce a clear warning, not a crash
- [ ] Tests use a fake HTTP layer; no real messages in the default suite
