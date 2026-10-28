"""Telegram Bot API notifier: `sendMessage` and `sendPhoto` over httpx.

A bot is configured by an environment-variable prefix: the dev bot reads
`TELEGRAM_DEV_BOT_TOKEN` / `TELEGRAM_DEV_CHAT_ID` (M0-M4 reports and alerts),
the trading bot `TELEGRAM_TRADING_BOT_TOKEN` / `TELEGRAM_TRADING_CHAT_ID` (from
M5). Values come from the process environment, falling back to a `.env` file
in the working directory. The token never appears in output, errors or logs.
"""

from __future__ import annotations

import html
import logging
import os
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Self

import httpx

DEV_BOT = "TELEGRAM_DEV"
TRADING_BOT = "TELEGRAM_TRADING"
API_URL = "https://api.telegram.org"
TEXT_LIMIT = 4096  # Telegram's per-message limits
CAPTION_LIMIT = 1024
ENV_FILE = Path(".env")


class NotifyError(Exception):
    """A message could not be delivered."""


@dataclass(frozen=True, repr=False)
class BotConfig:
    bot_token: str
    chat_id: str

    def __repr__(self) -> str:
        return f"BotConfig(bot_token='***', chat_id='{self.chat_id}')"


def env_names(prefix: str = DEV_BOT) -> tuple[str, str]:
    """The (token, chat id) variable names of the bot with this prefix."""
    return f"{prefix}_BOT_TOKEN", f"{prefix}_CHAT_ID"


def read_env_file(path: Path) -> dict[str, str]:
    """Parse `KEY=value` lines of a dotenv file; comments and blanks are skipped."""
    values: dict[str, str] = {}
    if not path.is_file():
        return values
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip().removeprefix("export ")
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip().strip("'\"")
    return values


def load_bot_config(
    prefix: str = DEV_BOT,
    env: Mapping[str, str] | None = None,
    env_file: Path | None = ENV_FILE,
) -> BotConfig | None:
    """Bot credentials from `env` (default: the process environment), then `env_file`.

    Returns None when either value is missing, so callers can warn and go on.
    """
    sources: list[Mapping[str, str]] = [os.environ if env is None else env]
    if env_file is not None:
        sources.append(read_env_file(env_file))
    found: dict[str, str] = {}
    for name in env_names(prefix):
        for source in sources:
            if source.get(name):
                found[name] = source[name]
                break
    if len(found) < 2:
        return None
    token_name, chat_name = env_names(prefix)
    return BotConfig(found[token_name], found[chat_name])


class _DropTelegramUrls(logging.Filter):
    """httpx logs every request URL at INFO; Telegram URLs contain the token."""

    def filter(self, record: logging.LogRecord) -> bool:
        return "api.telegram.org/bot" not in record.getMessage()


logging.getLogger("httpx").addFilter(_DropTelegramUrls())


class TelegramNotifier:
    """Sends to one chat through one bot. Raises `NotifyError` on failure."""

    def __init__(
        self,
        config: BotConfig,
        transport: httpx.BaseTransport | None = None,
        timeout_s: float = 30.0,
        api_url: str = API_URL,
    ) -> None:
        self._token = config.bot_token
        self._chat_id = config.chat_id
        self._http = httpx.Client(
            base_url=f"{api_url}/bot{config.bot_token}",
            transport=transport,
            timeout=timeout_s,
        )

    def __enter__(self) -> Self:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def close(self) -> None:
        self._http.close()

    def send_text(self, text: str, monospace: bool = False) -> int:
        """Send `text`, split on line breaks into messages within Telegram's limit.

        With `monospace`, each message is an HTML `<pre>` block (tables stay
        aligned on a phone). Returns how many messages were sent.
        """
        wrap = ("<pre>", "</pre>") if monospace else ("", "")
        room = TEXT_LIMIT - len(wrap[0]) - len(wrap[1])
        chunks = _split(html.escape(text) if monospace else text, room)
        for chunk in chunks:
            data: dict[str, Any] = {
                "chat_id": self._chat_id,
                "text": f"{wrap[0]}{chunk}{wrap[1]}",
            }
            if monospace:
                data["parse_mode"] = "HTML"
            self._post("sendMessage", data)
        return len(chunks)

    def send_photo(self, path: Path, caption: str = "") -> None:
        """Send an image file (PNG/JPEG) with an optional plain-text caption."""
        data = {"chat_id": self._chat_id}
        if caption:
            data["caption"] = caption[:CAPTION_LIMIT]
        with path.open("rb") as photo:
            self._post("sendPhoto", data, files={"photo": (path.name, photo)})

    def _post(
        self, method: str, data: dict[str, Any], files: dict[str, Any] | None = None
    ) -> Any:
        try:
            response = self._http.post(f"/{method}", data=data, files=files)
        except httpx.HTTPError as exc:
            raise NotifyError(
                f"could not reach Telegram ({method}): {self._redact(exc)}"
            ) from exc
        try:
            payload = response.json()
        except ValueError:
            payload = {}
        if response.is_error or not payload.get("ok"):
            why = payload.get("description") or f"HTTP {response.status_code}"
            raise NotifyError(f"Telegram {method} failed: {self._redact(why)}")
        return payload.get("result")

    def _redact(self, value: object) -> str:
        return str(value).replace(self._token, "***")


def _split(text: str, limit: int) -> list[str]:
    """Split on line breaks into pieces of at most `limit` characters."""
    chunks: list[str] = []
    current = ""
    for line in text.splitlines() or [""]:
        while len(line) > limit:  # a single over-long line is cut hard
            if current:
                chunks.append(current)
                current = ""
            chunks.append(line[:limit])
            line = line[limit:]
        candidate = f"{current}\n{line}" if current else line
        if len(candidate) > limit:
            chunks.append(current)
            current = line
        else:
            current = candidate
    chunks.append(current)
    return chunks
