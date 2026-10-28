---
name: telegram-and-secrets-howto
description: How to run live checks that need .env secrets from an isolated worktree, plus Telegram Bot API / httpx gotchas found building the notify module (2026-10-28)
metadata:
  type: reference
---

- Worktrees have no `.env` and agents may not read or copy it (the `cp` was denied). Load it into the process instead: `uv run --env-file C:/git/TTP_workbench/.env ttp <cmd>` run from the worktree. Nothing is printed, and the CLI's cwd-relative `.env` fallback is simply skipped.
- httpx logs `HTTP Request: POST <url>` at INFO on the `httpx` logger; Telegram URLs embed the bot token, so `ttp.notify.telegram` installs a filter on that logger. Keep it if the notifier is refactored.
- Telegram limits: 4096 chars per `sendMessage`, 1024 per photo caption. `<pre>` with `parse_mode=HTML` keeps tables aligned on a phone; keep table rows under ~46 chars (12-char market names fit).
- `sendPhoto` works as a plain multipart upload through `httpx.Client.post(files=...)`; no extra dependency needed.
- Under pytest's `--import-mode=importlib` (this repo), `from .test_screener import FakeMexc` works between test modules even without `tests/__init__.py`; plain `import test_screener` does not.
