"""Telegram notifier against a fake Bot API, and `ttp screen --notify`."""

import logging
import os
from pathlib import Path

import httpx
import pytest
from click.testing import CliRunner

from ttp.cli import main
from ttp.notify import (
    DEV_BOT,
    TRADING_BOT,
    BotConfig,
    NotifyError,
    TelegramNotifier,
    env_names,
    load_bot_config,
)
from ttp.notify.telegram import TEXT_LIMIT, _split
from ttp.venues.mexc import MexcClient

from .test_screener import FakeMexc

TOKEN = "123456:ABC-secret"
CONFIG = BotConfig(TOKEN, "42")


class FakeTelegram:
    """Records Bot API calls; `fail` makes every call answer with that status."""

    def __init__(self, fail: int | None = None) -> None:
        self.calls: list[tuple[str, dict, bytes | None]] = []
        self.fail = fail

    def __call__(self, request: httpx.Request) -> httpx.Response:
        assert request.url.host == "api.telegram.org"
        prefix, _, method = request.url.path.rpartition("/")
        assert prefix == f"/bot{TOKEN}"
        if method == "sendPhoto":
            fields, photo = _parse_multipart(request)
        else:
            fields, photo = dict(httpx.QueryParams(request.content.decode())), None
        self.calls.append((method, fields, photo))
        if self.fail:
            return httpx.Response(
                self.fail,
                json={"ok": False, "error_code": self.fail, "description": "nope"},
            )
        return httpx.Response(200, json={"ok": True, "result": {"message_id": 1}})

    def texts(self) -> list[str]:
        return [f["text"] for m, f, _ in self.calls if m == "sendMessage"]


def _parse_multipart(request: httpx.Request) -> tuple[dict, bytes | None]:
    boundary = request.headers["content-type"].split("boundary=")[1].encode()
    fields, photo = {}, None
    for part in request.content.split(b"--" + boundary)[1:-1]:
        head, _, body = part.strip(b"\r\n").partition(b"\r\n\r\n")
        name = head.split(b'name="')[1].split(b'"')[0].decode()
        if name == "photo":
            photo = body
        else:
            fields[name] = body.decode()
    return fields, photo


def notifier(server: FakeTelegram) -> TelegramNotifier:
    return TelegramNotifier(CONFIG, transport=httpx.MockTransport(server))


def test_send_text_posts_plain_message():
    server = FakeTelegram()
    with notifier(server) as tg:
        assert tg.send_text("hello <owner>") == 1
    assert server.calls == [
        ("sendMessage", {"chat_id": "42", "text": "hello <owner>"}, None)
    ]


def test_monospace_text_is_an_escaped_pre_block():
    server = FakeTelegram()
    with notifier(server) as tg:
        tg.send_text("a < b & c", monospace=True)
    _, fields, _ = server.calls[0]
    assert fields == {
        "chat_id": "42",
        "text": "<pre>a &lt; b &amp; c</pre>",
        "parse_mode": "HTML",
    }


def test_long_text_is_split_on_lines_within_the_limit():
    server = FakeTelegram()
    text = "\n".join(f"line {i:04d} " + "x" * 90 for i in range(100))
    with notifier(server) as tg:
        assert tg.send_text(text, monospace=True) == 3
    texts = server.texts()
    assert all(len(t) <= TEXT_LIMIT for t in texts)
    assert all(t.startswith("<pre>line") and t.endswith("x</pre>") for t in texts)
    assert "".join(t[5:-6] + "\n" for t in texts) == text + "\n"


def test_split_cuts_a_single_overlong_line():
    assert _split("x" * 10, 4) == ["xxxx", "xxxx", "xx"]
    assert _split("ab\ncd\nef", 5) == ["ab\ncd", "ef"]
    assert _split("", 5) == [""]


def test_send_photo_uploads_file_with_caption(tmp_path):
    png = tmp_path / "chart.png"
    png.write_bytes(b"\x89PNG\r\n\x1a\nfake")
    server = FakeTelegram()
    with notifier(server) as tg:
        tg.send_photo(png, "#1 ADXUSDT")
    method, fields, photo = server.calls[0]
    assert method == "sendPhoto"
    assert fields == {"chat_id": "42", "caption": "#1 ADXUSDT"}
    assert photo == png.read_bytes()


def test_api_error_raises_without_leaking_the_token():
    with notifier(FakeTelegram(fail=400)) as tg, pytest.raises(NotifyError) as exc:
        tg.send_text("x")
    assert "nope" in str(exc.value) and TOKEN not in str(exc.value)

    def down(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError(f"boom {request.url}")

    tg = TelegramNotifier(CONFIG, transport=httpx.MockTransport(down))
    with tg, pytest.raises(NotifyError) as exc:
        tg.send_text("x")
    assert "could not reach Telegram" in str(exc.value)
    assert TOKEN not in str(exc.value)


def test_token_never_appears_in_httpx_logs_or_repr(caplog):
    with caplog.at_level(logging.DEBUG), notifier(FakeTelegram()) as tg:
        tg.send_text("x")
    assert TOKEN not in caplog.text
    assert TOKEN not in repr(CONFIG)


def test_config_comes_from_env_then_dotenv_per_bot_prefix(tmp_path):
    env_file = tmp_path / ".env"
    env_file.write_text(
        "# dev bot\n"
        "TELEGRAM_DEV_BOT_TOKEN='file-token'\n"
        "TELEGRAM_DEV_CHAT_ID=7\n"
        'export TELEGRAM_TRADING_BOT_TOKEN="t-token"\n'
        "TELEGRAM_TRADING_CHAT_ID=\n",
        encoding="utf-8",
    )
    assert env_names(DEV_BOT) == ("TELEGRAM_DEV_BOT_TOKEN", "TELEGRAM_DEV_CHAT_ID")
    assert load_bot_config(DEV_BOT, {}, env_file) == BotConfig("file-token", "7")
    env = {"TELEGRAM_DEV_BOT_TOKEN": "env-token"}
    assert load_bot_config(DEV_BOT, env, env_file) == BotConfig("env-token", "7")
    assert load_bot_config(TRADING_BOT, {}, env_file) is None  # chat id empty
    assert load_bot_config(DEV_BOT, {}, tmp_path / "missing") is None
    assert load_bot_config(DEV_BOT, {}, None) is None


def run_screen(tmp_path, obj_extra, args=("--max-volume", "50000", "--top", "2")):
    from .test_screener import NOW

    return CliRunner().invoke(
        main,
        ["screen", "--notify", *args],
        obj={
            "mexc": MexcClient(transport=httpx.MockTransport(FakeMexc())),
            "data_root": tmp_path / "data",
            "reports_root": tmp_path / "reports",
            "now": lambda: NOW,
            "env": {},
            "env_file": tmp_path / ".env",
            **obj_extra,
        },
        prog_name="ttp",
    )


def test_screen_notify_sends_summary_then_top_charts(tmp_path):
    server = FakeTelegram()
    result = run_screen(tmp_path, {"telegram": notifier(server)})
    assert result.exit_code == 0, result.output
    assert "sent to Telegram: summary and 2 charts" in result.output

    methods = [m for m, _, _ in server.calls]
    assert methods == ["sendMessage", "sendPhoto", "sendPhoto"]
    text = server.texts()[0]
    assert text.startswith("<pre>Screen 20261028-120030")
    assert "2026-10-27 12:00 to 2026-10-28 12:00 UTC, 24 h" in text
    assert "4 of 4 markets scanned" in text
    assert " 1 ADXUSDT" in text and " 2 2U2USDT" in text and "ABEYUSDT" not in text
    assert "$48k" in text
    rows = [line for line in text.splitlines() if "USDT" in line]
    assert len(rows) == 2 and all(len(r.removesuffix("</pre>")) <= 46 for r in rows)

    out = tmp_path / "reports" / "20261028-120030" / "charts"
    for (_, fields, photo), name in zip(
        server.calls[1:], ["01-ADXUSDT.png", "02-2U2USDT.png"], strict=True
    ):
        assert photo == (out / name).read_bytes()
    assert server.calls[1][1]["caption"].startswith("#1 ADXUSDT: score ")
    assert "48 events" in server.calls[1][1]["caption"]


def test_screen_notify_warns_when_credentials_are_missing(tmp_path):
    result = run_screen(tmp_path, {})
    assert result.exit_code == 0, result.output
    assert "warning: not sent to Telegram: set TELEGRAM_DEV_BOT_TOKEN" in result.output
    assert "screen id: 20261028-120030" in result.output


def test_screen_notify_reports_a_failed_send(tmp_path):
    result = run_screen(tmp_path, {"telegram": notifier(FakeTelegram(fail=401))})
    assert result.exit_code == 1
    assert "Error: Telegram: Telegram sendMessage failed: nope" in result.output
    assert "Traceback" not in result.output
    assert (tmp_path / "reports" / "20261028-120030" / "report.md").is_file()


@pytest.mark.live
def test_live_dev_bot_receives_a_message():
    config = load_bot_config(DEV_BOT, os.environ, Path(".env"))
    if config is None:
        pytest.skip("dev bot not configured")
    with TelegramNotifier(config) as tg:
        assert tg.send_text("[ttp live test] notify module ping") == 1
