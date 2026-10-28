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
from ttp.screener.wicks import (
    COLUMNS,
    EVENT_COLUMNS,
    MIN_ACTIVE_SHARE,
    MIN_EVENTS,
    MIN_WICK_TO_BASE,
    rank,
    spike_events,
    wick_stats,
)
from ttp.venues.mexc import MexcClient, WeightLimiter
from ttp.venues.mexc.client import parse_klines

FIXTURES = Path(__file__).parent / "fixtures" / "mexc"
MIN_MS = 60_000
NOW = datetime(2026, 10, 28, 12, 0, 30, tzinfo=UTC)
END = datetime(2026, 10, 28, 12, 0, tzinfo=UTC)
START = END - timedelta(hours=24)
START_MS = int(START.timestamp() * 1000)
DAY = 24 * 60


BASE_DIP = 0.001  # every fixture candle trades `BASE_DIP` below its open: active


def row(open_ms: int, price: float, high: float, volume: float = 10.0) -> list:
    p = str(price)
    return [
        open_ms,
        p,
        str(high),
        str(price * (1 - BASE_DIP)),
        p,
        str(volume),
        open_ms + MIN_MS,
        str(volume * price),
    ]


def series(n: int, wicks: dict[int, float], price: float = 1.0) -> list[list]:
    """Active 1m candles from START (a 0.1% dip below the open, close at the open);
    minute i gets an upper wick of `wicks[i]`."""
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


def candle(i: int, o: float, h: float, lo: float, c: float) -> list:
    open_ms = START_MS + i * MIN_MS
    return [open_ms, str(o), str(h), str(lo), str(c), "10", open_ms + MIN_MS, "10"]


def trending_steps(n: int = DAY, every: int = 30) -> list[list]:
    """Price steps up 5% every `every` minutes; each step prints a wick on top."""
    price, rows = 1.0, []
    for i in range(n):
        if i % every == 15:
            rows.append(candle(i, price, price * 1.08, price, price * 1.05))
            price *= 1.05  # retrace 0.375: the spike never returns
        else:
            rows.append(candle(i, price, price, price, price))
    return rows


def gap_prints(n: int = DAY, every: int = 30) -> list[list]:
    """Prints bounce between bid 1.00 and ask 1.04 every minute; now and then a
    single print at 1.06 shows as a wick, but the base is as wide as the wicks."""
    rows = []
    for i in range(n):
        if i % every == 15:
            rows.append(candle(i, 1.0, 1.06, 1.0, 1.0))
        elif i % 2 == 0:
            rows.append(candle(i, 1.0, 1.04, 1.0, 1.04))
        else:
            rows.append(candle(i, 1.04, 1.04, 1.0, 1.0))
    return rows


def sparse_prints(n: int = DAY, every: int = 30, active_every: int = 5) -> list[list]:
    """Most minutes print nothing (flat candle at the last price); one minute in
    `active_every` trades a little, and every `every` minutes a single print at
    1.06 returns at once. A returned, regular, "calm" series with an empty base."""
    rows = []
    for i in range(n):
        if i % every == 15:
            rows.append(candle(i, 1.0, 1.06, 1.0, 1.0))
        elif i % active_every == 0:
            rows.append(candle(i, 1.0, 1.001, 0.999, 1.0))
        else:
            rows.append(candle(i, 1.0, 1.0, 1.0, 1.0))
    return rows


def calm_sweeps(n: int = DAY, every: int = 45, seed: int = 3) -> list[list]:
    """A calm zone (noise within +-0.3%) swept 6% up every `every` minutes,
    closing most of the way back (retrace ~0.93)."""
    rng = random.Random(seed)
    rows = []
    for i in range(n):
        o = 1.0 + rng.uniform(-0.003, 0.003)
        if i % every == 20:
            rows.append(candle(i, o, o * 1.06, o, o * 1.004))
        else:
            c = 1.0 + rng.uniform(-0.003, 0.003)
            rows.append(candle(i, o, max(o, c) * 1.001, min(o, c) * 0.999, c))
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
    assert s.base_range == pytest.approx(BASE_DIP)
    assert s.active_share == 1.0
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
    assert pd.isna(s.base_range) and pd.isna(s.active_share)


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


def test_events_record_open_first_close_last_and_retrace():
    rows = series(DAY, {})
    rows[100] = candle(100, 1.0, 1.05, 1.0, 1.02)  # a sweep over two minutes...
    rows[101] = candle(101, 1.02, 1.06, 1.0, 1.01)  # ...closing most of the way back
    rows[500] = candle(500, 1.0, 1.08, 1.0, 1.05)  # returns less than half
    events = spike_events(frame(rows), min_wick=0.02)
    assert list(events.columns) == EVENT_COLUMNS
    assert len(events) == 2
    first = events.iloc[0]
    assert first["start"] == pd.Timestamp(START + timedelta(minutes=100))
    assert (first["open_first"], first["high"], first["close_last"]) == (
        1.0,
        1.06,
        1.01,
    )
    assert first["wick"] == pytest.approx(0.04 / 1.02)  # above the body top 1.02
    assert first["retrace"] == pytest.approx(0.05 / 0.06)
    assert events.iloc[1]["retrace"] == pytest.approx(0.375)
    s = wick_stats(frame(rows), min_wick=0.02)
    assert (s.wick_count, s.returned_events) == (2, 1)
    assert s.retrace_median == pytest.approx((0.375 + 0.05 / 0.06) / 2)
    assert s.wick_median == pytest.approx(0.04 / 1.02)  # over returned sweeps only


def test_trending_steps_score_zero():
    s = wick_stats(frame(trending_steps()), min_wick=0.02)
    assert s.wick_count == 48
    assert s.returned_events == 0
    assert s.retrace_median == pytest.approx(0.375)
    assert pd.isna(s.wick_median) and pd.isna(s.interval_median_min)
    assert s.score == 0.0


def test_gap_single_prints_score_zero():
    s = wick_stats(frame(gap_prints()), min_wick=0.02)
    assert s.returned_events == 48  # every print returns...
    assert s.regularity == pytest.approx(1.0)  # ...on schedule...
    assert s.base_range == pytest.approx(0.04 / 1.04, rel=0.05)
    assert s.active_share == 1.0  # every base minute trades...
    assert s.wick_median < MIN_WICK_TO_BASE * s.base_range  # ...but is not a sweep
    assert s.score == 0.0


def test_sparse_prints_score_zero():
    """Flat minutes are not a calm base: the active-share gate alone stops the score."""
    s = wick_stats(frame(sparse_prints()), min_wick=0.02)
    assert s.returned_events == s.wick_count == 48  # every print returns...
    assert s.regularity == pytest.approx(1.0)  # ...on schedule...
    assert s.base_range == 0.0  # ...over a base that mostly does not trade
    assert s.wick_median >= MIN_WICK_TO_BASE * s.base_range  # v2 gate is vacuous
    assert s.active_share == pytest.approx(240 / (DAY - 48))
    assert s.active_share < MIN_ACTIVE_SHARE
    assert s.score == 0.0
    # The same prints over a base that trades every minute do score.
    active = [
        candle(i, 1.0, 1.001, 0.999, 1.0) if r[2] == "1.0" else r
        for i, r in enumerate(sparse_prints())
    ]
    assert wick_stats(frame(active), min_wick=0.02).score > 0


def test_burst_of_returned_sweeps_is_one_episode():
    s = wick_stats(frame(series(DAY, {m: 0.05 for m in range(100, 110, 2)})), 0.02)
    assert s.returned_events == 5
    assert s.interval_median_min == 2
    assert s.score == 0.0


def test_calm_zone_with_returned_sweeps_scores_and_ranks_first():
    s = wick_stats(frame(calm_sweeps()), min_wick=0.02)
    assert s.returned_events == s.wick_count == 32
    assert s.retrace_median == pytest.approx(0.056 / 0.06)
    assert 0.002 < s.base_range < 0.008  # noise, far below the 5.6% sweeps
    assert s.active_share == 1.0
    assert s.interval_median_min == 45 and s.regularity == pytest.approx(1.0)
    assert s.score == pytest.approx(32 * s.wick_median * 2)

    rows = {
        "CTRL": random_walk(),
        "TREND": trending_steps(),
        "GAP": gap_prints(),
        "SPARSE": sparse_prints(),
        "SMALL": periodic(0.03),
        "CALM": calm_sweeps(),
    }
    table = rank(
        [
            {"market": m, "volume_24h": 1.0, **vars(wick_stats(frame(r), 0.02))}
            for m, r in rows.items()
        ]
    )
    assert list(table.columns) == COLUMNS
    assert table["market"].tolist() == [
        "CALM",
        "SMALL",
        "GAP",
        "SPARSE",
        "TREND",
        "CTRL",
    ]
    assert table["score"].tolist()[2:] == [0.0, 0.0, 0.0, 0.0]


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
    assert list(stats.columns) == COLUMNS
    assert stats.loc[0, "wick_count"] == 48
    assert stats.loc[0, "returned_events"] == 48
    assert stats.loc[0, "retrace_median"] == pytest.approx(1.0)
    assert stats.loc[0, "base_range"] == pytest.approx(BASE_DIP)
    assert stats.loc[0, "active_share"] == 1.0
    assert stats.loc[0, "wick_median"] == pytest.approx(0.10)
    assert stats.loc[0, "interval_median_min"] == 30
    assert stats.loc[0, "regularity"] == pytest.approx(1.0)
    assert stats.loc[0, "volume_24h"] == pytest.approx(47664.9238)
    assert stats.loc[3, "score"] == 0

    report = (out / "report.md").read_text(encoding="utf-8")
    assert "DEBUSDT" not in report  # `st` market excluded by default
    assert "charts/01-ADXUSDT.png" in report
    assert "| Returned | Events | Typical wick | Retrace | Base range | Active |" in (
        report
    )
    assert "| 1 | ADXUSDT | 9.60 | 48 | 48 | 10.00% | 100.00% | 0.10% | 100.00% |" in (
        report
    )
    assert "charts show the last 24 h" in report  # default --chart-hours
    assert "2026-10-27 12:00" in report and "2026-10-28 12:00" in report
    assert "DEBUSDT" not in result.output
    assert "RETURNED EVENTS    WICK RETRACE    BASE  ACTIVE" in result.output
    assert (
        "ADXUSDT           9.60       48     48  10.00% 100.00%   0.10% 100.00%"
        in result.output
    )


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
