"""Kline pagination, dataset storage (dedup / gap-fill), the DuckDB reader and the card."""

import json
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx
import pandas as pd
import pytest
from click.testing import CliRunner

from ttp.cli import main
from ttp.data.downloader import download_klines, klines_frame
from ttp.data.store import KLINES_1M, DatasetStore
from ttp.venues.mexc import MexcClient
from ttp.venues.mexc.client import parse_klines

FIXTURES = Path(__file__).parent / "fixtures" / "mexc"
MIN_MS = 60_000
T0 = datetime(2026, 10, 27, 23, 0, tzinfo=UTC)  # spans a UTC date boundary
T0_MS = int(T0.timestamp() * 1000)


def row(open_ms: int, close: float = 1.0, volume: float = 0.0) -> list:
    """A kline row in MEXC's wire format."""
    p = str(close)
    return [open_ms, p, p, p, p, str(volume), open_ms + MIN_MS, str(volume * close)]


class FakeKlineServer:
    """Serves `/api/v3/klines` like MEXC: startTime is ignored without endTime,
    rows open in [startTime, endTime), at most 500 per response."""

    def __init__(self, rows: list[list]) -> None:
        self.rows = sorted(rows)
        self.requests: list[dict] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v3/klines"
        q = dict(request.url.params)
        self.requests.append(q)
        assert q["interval"] == "1m"
        start, end = int(q["startTime"]), int(q["endTime"])
        limit = min(int(q.get("limit", 500)), 500)
        page = [r for r in self.rows if start <= r[0] < end][:limit]
        return httpx.Response(200, json=page)


def minutes(start_ms: int, n: int, skip: set[int] = frozenset()) -> list[list]:
    return [
        row(start_ms + i * MIN_MS, close=1 + i / 1000)
        for i in range(n)
        if i not in skip
    ]


def client(server) -> MexcClient:
    return MexcClient(transport=httpx.MockTransport(server))


def test_klines_fixture_parses_mexc_rows():
    payload = json.loads((FIXTURES / "klines_adxusdt_1m.json").read_text())
    start = payload[0][0]
    server = FakeKlineServer(payload)
    klines = client(server).klines("ADXUSDT", start, start + 6 * MIN_MS)
    assert len(klines) == 6
    trade_minute = klines[2]
    assert trade_minute.open_time_ms == 1792897140000
    assert (trade_minute.open, trade_minute.low, trade_minute.close) == (
        0.0565,
        0.0564,
        0.0564,
    )
    assert trade_minute.volume == pytest.approx(592.01)
    assert trade_minute.quote_volume == pytest.approx(33.4187)


def test_klines_paginate_over_requested_range():
    server = FakeKlineServer(minutes(T0_MS, 1200))
    klines = client(server).klines("ADXUSDT", T0_MS, T0_MS + 1200 * MIN_MS)
    assert [k.open_time_ms for k in klines] == [T0_MS + i * MIN_MS for i in range(1200)]
    assert len(server.requests) == 3
    assert all("startTime" in q and "endTime" in q for q in server.requests)


def test_klines_skip_empty_pages_before_history_starts():
    # Venue history starts 700 minutes into the range: first page comes back empty.
    server = FakeKlineServer(minutes(T0_MS + 700 * MIN_MS, 300))
    klines = client(server).klines("ADXUSDT", T0_MS, T0_MS + 1000 * MIN_MS)
    assert len(klines) == 300
    assert klines[0].open_time_ms == T0_MS + 700 * MIN_MS


def test_klines_range_is_end_exclusive():
    server = FakeKlineServer(minutes(T0_MS, 20))
    klines = client(server).klines("ADXUSDT", T0_MS + 5 * MIN_MS, T0_MS + 8 * MIN_MS)
    assert [k.open_time_ms for k in klines] == [T0_MS + i * MIN_MS for i in (5, 6, 7)]


def test_download_fills_gaps_without_duplicating(tmp_path):
    store = DatasetStore(tmp_path)
    end = T0 + timedelta(minutes=120)
    # First run: the venue misses minutes 30-39 and 100.
    first = FakeKlineServer(minutes(T0_MS, 120, skip={*range(30, 40), 100}))
    r1 = download_klines(client(first), store, "test", "ADXUSDT", T0, end)
    assert (r1.added, r1.still_missing) == (109, 11)

    # Second run: venue now has everything; only the missing ranges are asked for.
    second = FakeKlineServer(minutes(T0_MS, 120))
    r2 = download_klines(client(second), store, "test", "ADXUSDT", T0, end)
    assert (r2.requested_ranges, r2.fetched, r2.added, r2.still_missing) == (
        2,
        11,
        11,
        0,
    )
    asked = sorted((int(q["startTime"]), int(q["endTime"])) for q in second.requests)
    assert asked == [
        (T0_MS + 30 * MIN_MS, T0_MS + 40 * MIN_MS),
        (T0_MS + 100 * MIN_MS, T0_MS + 101 * MIN_MS),
    ]

    # Third run: nothing missing, nothing fetched, no duplicates.
    third = FakeKlineServer(minutes(T0_MS, 120))
    r3 = download_klines(client(third), store, "test", "ADXUSDT", T0, end)
    assert (r3.requested_ranges, r3.added) == (0, 0)
    assert third.requests == []

    df = store.read("test", "mexc", "ADXUSDT", KLINES_1M)
    assert len(df) == 120
    assert df["open_time"].is_unique and df["open_time"].is_monotonic_increasing


def test_storage_partitions_by_venue_market_type_date(tmp_path):
    store = DatasetStore(tmp_path)
    end = T0 + timedelta(minutes=120)
    download_klines(
        client(FakeKlineServer(minutes(T0_MS, 120))), store, "test", "ADXUSDT", T0, end
    )
    parts = sorted(
        p.relative_to(tmp_path).as_posix() for p in tmp_path.rglob("*.parquet")
    )
    assert parts == [
        "test/venue=mexc/market=ADXUSDT/type=klines_1m/date=2026-10-27/data.parquet",
        "test/venue=mexc/market=ADXUSDT/type=klines_1m/date=2026-10-28/data.parquet",
    ]


def test_rewritten_rows_replace_stored_rows(tmp_path):
    store = DatasetStore(tmp_path)
    store.write(
        "test", "mexc", "X", KLINES_1M, klines_frame_of([row(T0_MS, close=1.0)])
    )
    store.write(
        "test", "mexc", "X", KLINES_1M, klines_frame_of([row(T0_MS, close=2.0)])
    )
    df = store.read("test", "mexc", "X", KLINES_1M)
    assert df["close"].tolist() == [2.0]


def klines_frame_of(rows):
    return klines_frame(parse_klines(rows))


def test_reader_returns_time_range_as_dataframe(tmp_path):
    store = DatasetStore(tmp_path)
    download_klines(
        client(FakeKlineServer(minutes(T0_MS, 120))),
        store,
        "test",
        "ADXUSDT",
        T0,
        T0 + timedelta(minutes=120),
    )
    df = store.read(
        "test",
        "mexc",
        "ADXUSDT",
        KLINES_1M,
        start=T0 + timedelta(minutes=50),
        end=T0 + timedelta(minutes=70),  # 2026-10-27 23:50 to 2026-10-28 00:10
    )
    assert isinstance(df, pd.DataFrame)
    assert list(df.columns) == list(KLINES_1M.columns)
    assert len(df) == 20
    assert df["open_time"].iloc[0] == pd.Timestamp("2026-10-27 23:50", tz="UTC")
    assert df["open_time"].iloc[-1] == pd.Timestamp("2026-10-28 00:09", tz="UTC")
    assert df["close"].iloc[0] == pytest.approx(1.05)


def test_reader_on_missing_series_returns_empty_frame(tmp_path):
    df = DatasetStore(tmp_path).read("nothing", "mexc", "ADXUSDT", KLINES_1M)
    assert df.empty
    assert list(df.columns) == list(KLINES_1M.columns)


def test_dataset_name_is_validated(tmp_path):
    with pytest.raises(ValueError):
        DatasetStore(tmp_path).dataset_dir("../escape")


def run_download(tmp_path, server, args):
    return CliRunner().invoke(
        main,
        ["download", "klines", *args],
        obj={
            "mexc": client(server),
            "data_root": tmp_path / "data",
            "cards_dir": tmp_path / "cards",
            "now": lambda: T0 + timedelta(minutes=120, seconds=30),
            "commit": "abc1234",
        },
        prog_name="ttp",
    )


def test_download_command_writes_dataset_and_card(tmp_path):
    # Two days requested, but the venue only has the last 120 minutes, minus 2.
    server = FakeKlineServer(minutes(T0_MS, 120, skip={60, 61}))
    result = run_download(
        tmp_path, server, ["adx/usdt", "--days", "2", "--dataset", "spikes-v1"]
    )
    assert result.exit_code == 0, result.output
    assert "118 new" in result.output
    assert "dataset 'spikes-v1'" in result.output

    card = (tmp_path / "cards" / "spikes-v1.md").read_text(encoding="utf-8")
    assert card.startswith("# spikes-v1\n")
    for field in (
        "- Source: MEXC spot public REST `GET /api/v3/klines`",
        "- Venue(s) & markets: MEXC ADXUSDT",
        "- Data type & resolution: OHLCV 1m",
        "- Date range: 2026-10-27 23:00 UTC to 2026-10-28 00:59 UTC",
        "- Location: ",
        "- Collected by: `ttp` at commit `abc1234`, last updated on 2026-10-28",
        "- Known gaps & quirks: see Gaps below.",
    ):
        assert field in card
    assert (
        "| mexc | ADXUSDT | klines_1m | 2026-10-27 23:00 UTC | 2026-10-28 00:59 UTC | 118 | 2 |"
        in card
    )
    assert "- ADXUSDT klines_1m: 2026-10-28 00:00 UTC to 2026-10-28 00:02 UTC" in card


def test_download_command_rejects_bad_dataset_name(tmp_path):
    result = run_download(
        tmp_path,
        FakeKlineServer([]),
        ["ADXUSDT", "--days", "1", "--dataset", "Bad Name"],
    )
    assert result.exit_code != 0
    assert "--dataset" in result.output


def test_download_command_reports_venue_errors(tmp_path):
    def handler(request):
        return httpx.Response(400, json={"code": -1121, "msg": "Invalid symbol."})

    result = run_download(tmp_path, handler, ["NOPEUSDT", "--days", "1"])
    assert result.exit_code == 1
    assert "Invalid symbol." in result.output
    assert "Traceback" not in result.output


@pytest.mark.live
def test_live_klines_last_hour():
    now = int(datetime.now(UTC).timestamp() * 1000) // MIN_MS * MIN_MS
    with MexcClient() as c:
        klines = c.klines("BTCUSDT", now - 600 * MIN_MS, now)
    assert len(klines) == 600  # MEXC fills idle minutes, and pagination crosses 500
    assert klines[-1].open_time_ms == now - MIN_MS
