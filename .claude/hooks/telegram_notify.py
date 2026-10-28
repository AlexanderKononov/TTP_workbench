"""One-way Telegram alert for Claude Code's Notification hook (Level 1 dev bot).

Reads TELEGRAM_DEV_BOT_TOKEN and TELEGRAM_DEV_CHAT_ID from the environment,
falling back to the repo-root .env. Silently does nothing if either is
missing, so the hook never blocks a session.
"""

from __future__ import annotations

import json
import os
import sys
import urllib.parse
import urllib.request
from pathlib import Path

KEYS = ("TELEGRAM_DEV_BOT_TOKEN", "TELEGRAM_DEV_CHAT_ID")


def load_config() -> dict[str, str]:
    config = {k: os.environ[k] for k in KEYS if os.environ.get(k)}
    env_file = Path(__file__).resolve().parents[2] / ".env"
    if len(config) < len(KEYS) and env_file.exists():
        for line in env_file.read_text(encoding="utf-8").splitlines():
            key, _, value = line.partition("=")
            key = key.strip()
            if key in KEYS and key not in config:
                config[key] = value.strip().strip("'\"")
    return config


def main() -> None:
    config = load_config()
    if len(config) < len(KEYS):
        return
    try:
        event = json.load(sys.stdin)
    except json.JSONDecodeError:
        event = {}
    project = Path(event.get("cwd", ".")).name
    text = f"[{project}] {event.get('message', 'Claude Code needs you')}"
    data = urllib.parse.urlencode(
        {"chat_id": config["TELEGRAM_DEV_CHAT_ID"], "text": text}
    ).encode()
    url = f"https://api.telegram.org/bot{config['TELEGRAM_DEV_BOT_TOKEN']}/sendMessage"
    try:
        urllib.request.urlopen(url, data=data, timeout=10)
    except OSError:
        pass


if __name__ == "__main__":
    main()
