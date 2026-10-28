"""Screener v1: wick metrics and ranking on fixture kline series, and `ttp screen`."""

import random
import threading
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pandas as pd
import pytest
from click.testing import CliRunner

from ttp.cli import main
from ttp.data.downloader import klines_frame
from ttp.screener.report import candle_chart
from ttp.screener.wicks import MIN_EVENTS, rank, wick_stats
from ttp.venues.mexc import MexcClient, WeightLimiter
from ttp.venues.mexc.client import parse_klines

FIXTURES = Path(__file__).parent / "fixtures" / "mexc"
MIN_MS = 60_000
NOW = datetime(2026, 10, 28, 12, 0, 30, tzinfo=UTC)
END = datetime(2026, 10, 28, 12, 0, tzinfo=UTC)
START = END - timedelta(hours=24)
START_MS = int(START.timestamp() * 1000)
DAY = 24 * 60


def row(open_ms: int, price: float, high: float, volume: float = 10.0) -> list:
    p = str(price)
    return [
        open_ms,
        p,
        str(high),
        p,
        p,
        str(volume),
        open_ms + MIN_MS,
        str(volume * price),
    ]


def series(n: int, wicks: dict[int, float], price: float = 1.0) -> list[list]:
    """Flat 1m candles from START; minute i gets an upper wick of `wicks[i]`."""
    return [
        row(START_MS + i * MIN_MS, price, price * (1 + wicks.get(i, 0.0)))
        for i in range(n)
    ]


def periodic(
    size: float, every: int = 30, n: int = DAY, offset: int = 15
) -> list[list]:
    return series(n, {i: size for i in range(offset, n, every)})


def irregular(size: float, count: int = 48, n: int = DAY, seed: int = 1) -> list[list]:
    # Even minutes only, so no two spikes are adjacent (they would merge).
    minutes = random.Random(seed).sample(range(0, n, 2), count)
    return series(n, {i: size for i in minutes})


def random_walk(n: int = DAY, seed: int = 2) -> list[list]:
    """A control: price wanders, candles close at their high (no upper wicks)."""
    rng = random.Random(seed)
    price, rows = 1.0, []
    for i in range(n):
        nxt = price * (1 + rng.uniform(-0.01, 0.01))
        rows.append(
            [
                START_MS + i * MIN_MS,
                str(price),
                str(max(price, nxt)),
                str(min(price, nxt)),
                str(nxt),
                "10",
                START_MS + (i + 1) * MIN_MS,
                "10",
            ]
        )
        price = nxt
    return rows


def frame(rows: list[list]) -> pd.DataFrame:
    return klines_frame(parse_klines(rows))


def test_periodic_wicks_are_counted_sized_and_regular():
    s = wick_stats(frame(periodic(0.05)), min_wick=0.02)
    assert s.candles == DAY
    assert s.wick_count == 48
    assert s.wick_median == pytest.approx(0.05)
    assert s.wick_max == pytest.approx(0.05)
    assert s.interval_median_min == 30
    assert s.regularity == pytest.approx(1.0)
    assert s.score == pytest.approx(48 * 0.05 * 2)


def test_irregular_wicks_score_lower_than_regular_ones():
    regular = wick_stats(frame(periodic(0.05)), min_wick=0.02)
    jittered = wick_stats(frame(irregular(0.05)), min_wick=0.02)
    assert jittered.wick_count == regular.wick_count
    assert jittered.wick_median == pytest.approx(regular.wick_median)
    assert jittered.regularity < 0.5
    assert jittered.score < regular.score


def test_control_without_wicks_scores_zero():
    s = wick_stats(frame(random_walk()), min_wick=0.02)
    assert s.candles == DAY
    assert (s.wick_count, s.regularity, s.score) == (0, 0.0, 0.0)
    assert pd.isna(s.wick_median) and pd.isna(s.interval_median_min)


def test_wicks_below_threshold_do_not_count():
    s = wick_stats(frame(periodic(0.01)), min_wick=0.02)
    assert s.wick_count == 0 and s.score == 0.0


def test_too_few_spikes_are_not_a_pattern():
    s = wick_stats(frame(series(DAY, {100: 0.1, 700: 0.1})), min_wick=0.02)
    assert s.wick_count == MIN_EVENTS - 1
    assert s.interval_median_min == 600
    assert (s.regularity, s.score) == (0.0, 0.0)


def test_adjacent_spike_minutes_are_one_event():
    s = wick_stats(
        frame(series(DAY, {100: 0.04, 101: 0.06, 200: 0.04, 300: 0.04})), min_wick=0.02
    )
    assert s.wick_count == 3
    assert s.wick_max == pytest.approx(0.06)
    assert s.interval_median_min == 100
    assert s.regularity == pytest.approx(1.0)


def test_empty_series_has_zero_stats():
    s = wick_stats(frame([]), min_wick=0.02)
    assert (s.candles, s.wick_count, s.score) == (0, 0, 0.0)


def test_ranking_is_deterministic_and_prefers_big_regular_wicks():
    rows = {
        "CTRL": random_walk(),
        "SMALL": periodic(0.03),
        "BIG": periodic(0.10),
        "JITTER": irregular(0.10),
        "TWIN": periodic(0.10),  # identical to BIG: ties break by market name
    }
    table = rank(
        [
            {"market": m, "volume_24h": 1.0, **vars(wick_stats(frame(r), 0.02))}
            for m, r in rows.items()
        ]
    )
    assert table["market"].tolist() == ["BIG", "TWIN", "JITTER", "SMALL", "CTRL"]
    assert table["rank"].tolist() == [1, 2, 3, 4, 5]
    assert table["score"].is_monotonic_decreasing


def test_candle_chart_writes_png(tmp_path):
    path = tmp_path / "chart.png"
    candle_chart(frame(periodic(0.05, n=360)), min_wick=0.02, title="X", path=path)
    assert path.read_bytes()[:4] == b"\x89PNG"


# --- `ttp screen` against the saved MEXC universe and generated klines ----------

KLINES = {
    "ADXUSDT": periodic(0.10),
    "AAVEUSDC": random_walk(),
    "2U2USDT": irregular(0.10),
    "ABEYUSDT": periodic(0.03),
    "DEBUSDT": periodic(0.20),  # flagged `st` by MEXC
}


class FakeMexc:
    def __init__(self, klines=KLINES, failing: dict[str, int] | None = None) -> None:
        self.klines = klines
        self.failing = failing or {}
        self.kline_requests: list[str] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path
        if path == "/api/v3/exchangeInfo":
            return httpx.Response(
                200, content=(FIXTURES / "exchange_info.json").read_bytes()
            )
        if path == "/api/v3/ticker/24hr":
            return httpx.Response(
                200, content=(FIXTURES / "ticker_24hr.json").read_bytes()
            )
        assert path == "/api/v3/klines"
        q = dict(request.url.params)
        symbol = q["symbol"]
        self.kline_requests.append(symbol)
        if symbol in self.failing:
            return httpx.Response(
                self.failing[symbol], json={"code": -1, "msg": "nope"}
            )
        start, end = int(q["startTime"]), int(q["endTime"])
        rows = [r for r in self.klines.get(symbol, []) if start <= r[0] < end][:500]
        return httpx.Response(200, json=rows)


def run_screen(tmp_path, server, args):
    return CliRunner().invoke(
        main,
        ["screen", *args],
        obj={
            "mexc": MexcClient(transport=httpx.MockTransport(server)),
            "data_root": tmp_path / "data",
            "reports_root": tmp_path / "reports",
            "now": lambda: NOW,
        },
        prog_name="ttp",
    )


def test_screen_ranks_universe_and_writes_report(tmp_path):
    server = FakeMexc()
    result = run_screen(tmp_path, server, ["--max-volume", "50000", "--top", "3"])
    assert result.exit_code == 0, result.output
    screen_id = "20261028-120030"
    assert f"screen id: {screen_id}" in result.output
    out = tmp_path / "reports" / screen_id
    assert (out / "report.md").is_file()
    charts = sorted(p.name for p in (out / "charts").glob("*.png"))
    assert charts == ["01-ADXUSDT.png", "02-2U2USDT.png", "03-ABEYUSDT.png"]
    assert (out / "charts" / charts[0]).read_bytes()[:4] == b"\x89PNG"

    stats = pd.read_csv(out / "stats.csv")
    assert stats["market"].tolist() == ["ADXUSDT", "2U2USDT", "ABEYUSDT", "AAVEUSDC"]
    assert stats["rank"].tolist() == [1, 2, 3, 4]
    assert stats.loc[0, "wick_count"] == 48
    assert stats.loc[0, "wick_median"] == pytest.approx(0.10)
    assert stats.loc[0, "interval_median_min"] == 30
    assert stats.loc[0, "regularity"] == pytest.approx(1.0)
    assert stats.loc[0, "volume_24h"] == pytest.approx(47664.9238)
    assert stats.loc[3, "score"] == 0

    report = (out / "report.md").read_text(encoding="utf-8")
    assert "DEBUSDT" not in report  # `st` market excluded by default
    assert "charts/01-ADXUSDT.png" in report
    assert "2026-10-27 12:00" in report and "2026-10-28 12:00" in report
    assert "DEBUSDT" not in result.output


def test_screen_includes_st_markets_on_request(tmp_path):
    result = run_screen(
        tmp_path, FakeMexc(), ["--max-volume", "50000", "--top", "2", "--include-st"]
    )
    assert result.exit_code == 0, result.output
    stats = pd.read_csv(tmp_path / "reports" / "20261028-120030" / "stats.csv")
    assert stats["market"].tolist()[:2] == ["DEBUSDT", "ADXUSDT"]


def test_screen_reuses_stored_klines(tmp_path):
    server = FakeMexc()
    assert run_screen(tmp_path, server, ["--max-volume", "50000"]).exit_code == 0
    first = len(server.kline_requests)
    assert first == 4 * 3  # 4 non-st markets; 24 h = 1,440 minutes = 3 pages of 500
    assert run_screen(tmp_path, server, ["--max-volume", "50000"]).exit_code == 0
    assert len(server.kline_requests) == first


def test_screen_scans_the_requested_window(tmp_path):
    server = FakeMexc()
    result = run_screen(
        tmp_path, server, ["--max-volume", "50000", "--hours", "6", "--top", "1"]
    )
    assert result.exit_code == 0, result.output
    stats = pd.read_csv(tmp_path / "reports" / "20261028-120030" / "stats.csv")
    assert stats.loc[0, "market"] == "ADXUSDT"
    assert stats.loc[0, "candles"] == 360
    assert stats.loc[0, "wick_count"] == 12


def test_screen_skips_a_broken_market_but_stops_on_rate_limit(tmp_path):
    result = run_screen(
        tmp_path, FakeMexc(failing={"AAVEUSDC": 400}), ["--max-volume", "50000"]
    )
    assert result.exit_code == 0, result.output
    assert "skipped 1 market" in result.output
    report = (tmp_path / "reports" / "20261028-120030" / "report.md").read_text()
    assert "AAVEUSDC" in report and "nope" in report

    result = run_screen(
        tmp_path / "b", FakeMexc(failing={"ADXUSDT": 429}), ["--max-volume", "50000"]
    )
    assert result.exit_code == 1
    assert "rate limit" in result.output
    assert "Traceback" not in result.output


def test_weight_limiter_is_shared_safely_between_threads():
    """Admissions 4 apart must be at least a window apart, however many threads."""
    limiter = WeightLimiter(limit=4, window_s=0.25)
    admitted: list[float] = []

    def worker() -> None:
        for _ in range(4):
            limiter.acquire(1)
            admitted.append(time.monotonic())

    threads = [threading.Thread(target=worker) for _ in range(3)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    admitted.sort()
    assert len(admitted) == 12
    assert all(
        b - a >= 0.25 - 0.02 for a, b in zip(admitted, admitted[4:], strict=False)
    )
