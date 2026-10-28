"""Dataset approval (gate 7): control selection, versioned definitions, `ttp dataset`."""

import json
from datetime import UTC, datetime

import httpx
import pandas as pd
import pytest
from click.testing import CliRunner

from ttp.cli import main
from ttp.data.datasets import (
    DatasetDefinition,
    approve,
    load_definition,
    select_controls,
)
from ttp.data.store import KLINES_1M, TRADES, DatasetStore
from ttp.screener.wicks import COLUMNS
from ttp.venues.mexc import MexcClient

NOW = datetime(2026, 10, 28, 12, 0, 30, tzinfo=UTC)
SCREEN = "20261028-083639"
MIN_MS = 60_000
S_MS = 1_000


def stats_table(markets: list[tuple[str, float, int, float]]) -> pd.DataFrame:
    """A screen's `stats.csv` content from (market, score, events, 24h volume)."""
    rows = []
    for rank, (market, score, events, volume) in enumerate(markets, 1):
        rows.append(
            {
                "rank": rank,
                "market": market,
                "score": score,
                "wick_count": events,
                "wick_median": 0.03 if events else float("nan"),
                "wick_max": 0.05 if events else float("nan"),
                "interval_median_min": 30.0 if events > 1 else float("nan"),
                "regularity": 0.5 if score else 0.0,
                "volume_24h": volume,
                "candles": 1440,
            }
        )
    return pd.DataFrame(rows, columns=COLUMNS)


# Two candidates in different volume bands; quiet markets around each; noise.
STATS = stats_table(
    [
        ("SPIKEUSDT", 0.9, 20, 60_000),
        ("WEAKUSDT", 0.4, 10, 5_000),
        ("FEWUSDT", 0.0, 2, 58_000),  # 2 events: not a pattern, not pattern-free
        ("ONEUSDT", 0.0, 1, 61_000),
        ("Q1USDT", 0.0, 0, 40_000),
        ("Q2USDT", 0.0, 0, 70_000),
        ("Q3USDT", 0.0, 0, 110_000),
        ("Q4USDT", 0.0, 0, 20_000),  # below SPIKE's band at x2
        ("L1USDT", 0.0, 0, 4_000),
        ("L2USDT", 0.0, 0, 9_000),
        ("FARUSDT", 0.0, 0, 500),
    ]
)


def test_controls_come_from_same_band_pattern_free_and_are_reproducible():
    picks = select_controls(STATS, ["SPIKEUSDT", "WEAKUSDT"], seed=0, band=2.0)
    assert [p.candidate for p in picks] == ["SPIKEUSDT", "WEAKUSDT"]
    assert picks[0].control in {"Q1USDT", "Q2USDT", "Q3USDT"}
    assert picks[1].control in {"L1USDT", "L2USDT"}
    assert all(p.band == 2.0 for p in picks)
    again = select_controls(STATS, ["SPIKEUSDT", "WEAKUSDT"], seed=0, band=2.0)
    assert again == picks
    shuffled = STATS.sample(frac=1, random_state=7)  # row order must not matter
    assert select_controls(shuffled, ["SPIKEUSDT", "WEAKUSDT"], seed=0) == picks


def test_seed_changes_the_draw_and_each_candidate_draws_independently():
    draws = {
        select_controls(STATS, ["SPIKEUSDT"], seed=s)[0].control for s in range(20)
    }
    assert draws == {"Q1USDT", "Q2USDT", "Q3USDT"}
    alone = select_controls(STATS, ["WEAKUSDT"], seed=3)[0].control
    with_other = select_controls(STATS, ["SPIKEUSDT", "WEAKUSDT"], seed=3)[1].control
    assert alone == with_other


def test_controls_are_distinct_and_exclude_candidates_and_taken_markets():
    stats = stats_table(
        [
            ("AUSDT", 0.9, 20, 10_000),
            ("BUSDT", 0.8, 15, 10_000),
            ("CUSDT", 0.0, 0, 10_000),
            ("DUSDT", 0.0, 0, 10_000),
            ("EUSDT", 0.0, 0, 10_000),
        ]
    )
    picks = select_controls(stats, ["AUSDT", "BUSDT"], seed=1, exclude={"EUSDT"})
    assert {p.control for p in picks} == {"CUSDT", "DUSDT"}


def test_max_control_events_admits_markets_with_a_few_isolated_wicks():
    picks = {
        select_controls(STATS, ["SPIKEUSDT"], seed=s, max_events=1)[0].control
        for s in range(30)
    }
    assert "ONEUSDT" in picks and "FEWUSDT" not in picks
    with pytest.raises(ValueError):
        select_controls(STATS, ["SPIKEUSDT"], seed=0, max_events=3)


def test_band_widens_when_empty_and_fails_when_nothing_is_near():
    stats = stats_table(
        [
            ("AUSDT", 0.9, 20, 10_000),
            ("QUSDT", 0.0, 0, 70_000),  # x7 away: found at band x8
            ("ZUSDT", 0.0, 0, 1_000_000),
        ]
    )
    [pick] = select_controls(stats, ["AUSDT"], seed=0, band=2.0)
    assert (pick.control, pick.band) == ("QUSDT", 8.0)
    with pytest.raises(ValueError, match="no pattern-free control for AUSDT"):
        select_controls(stats, ["AUSDT"], seed=0, band=1.5)


def test_half_listed_quiet_market_is_not_a_control():
    stats = stats_table([("AUSDT", 0.9, 20, 10_000), ("NEWUSDT", 0.0, 0, 10_000)])
    stats.loc[stats["market"] == "NEWUSDT", "candles"] = 300
    with pytest.raises(ValueError):
        select_controls(stats, ["AUSDT"], seed=0)


def test_unknown_candidate_is_an_error():
    with pytest.raises(ValueError, match="not in the screen: NOPEUSDT"):
        select_controls(STATS, ["NOPEUSDT"], seed=0)


def test_approve_versions_the_definition_and_skips_known_markets():
    d = DatasetDefinition("spikes")
    added = approve(d, STATS, SCREEN, ["SPIKEUSDT"], NOW, 0, 2.0, 0, "abc1234")
    assert [(m.market, m.role) for m in added] == [
        ("SPIKEUSDT", "candidate"),
        (added[1].market, "control"),
    ]
    assert added[0].paired_with == added[1].market
    assert added[1].paired_with == "SPIKEUSDT"
    assert (added[0].score, added[0].wick_count, added[0].volume_24h) == (
        0.9,
        20,
        60_000,
    )
    assert d.version == 1 and d.approvals[0].approved_on == "2026-10-28T12:00:30+00:00"

    assert approve(d, STATS, SCREEN, ["SPIKEUSDT"], NOW, 0, 2.0, 0, "abc1234") == []
    assert d.version == 1

    more = approve(
        d, STATS, SCREEN, ["WEAKUSDT", "SPIKEUSDT"], NOW, 0, 2.0, 0, "abc1234"
    )
    assert more[0].market == "WEAKUSDT"
    assert d.version == 2 and len(d.markets) == 4
    assert len(set(d.symbols)) == 4
    assert [m.version for m in d.markets] == [1, 1, 2, 2]

    restored = DatasetDefinition.from_json(d.to_json())
    assert restored == d
    assert json.loads(d.to_json())["approvals"][1]["version"] == 2


# --- `ttp dataset` -----------------------------------------------------------


class FakeMexc:
    """Klines (flat candles) and aggregate trades (one print per minute) for any symbol."""

    def __init__(self, fail: set[str] = frozenset()) -> None:
        self.fail = fail
        self.requests: list[tuple[str, str]] = []

    def __call__(self, request: httpx.Request) -> httpx.Response:
        q = dict(request.url.params)
        self.requests.append((request.url.path, q["symbol"]))
        if q["symbol"] in self.fail:
            return httpx.Response(400, json={"code": -1121, "msg": "Invalid symbol."})
        start, end = int(q["startTime"]), int(q["endTime"])
        if request.url.path == "/api/v3/klines":
            rows = [
                [t, "1", "1", "1", "1", "5", t + MIN_MS, "5"]
                for t in range(start, end, MIN_MS)
            ][:500]
            return httpx.Response(200, json=rows)
        assert request.url.path == "/api/v3/aggTrades"
        first = -(-start // MIN_MS) * MIN_MS
        rows = [
            {
                "a": None,
                "f": None,
                "l": None,
                "p": "1",
                "q": "2",
                "T": t,
                "m": True,
                "M": True,
            }
            for t in range(first, end + 1, MIN_MS)
        ]
        return httpx.Response(200, json=list(reversed(rows))[:1000])


def test_approving_a_control_as_candidate_is_an_error_and_writes_nothing():
    d = DatasetDefinition("spikes")
    approve(d, STATS, SCREEN, ["SPIKEUSDT"], NOW, 0, 2.0, 0, "abc1234")
    control = d.controls[0].market
    before = d.to_json()
    with pytest.raises(ValueError, match=f"{control}.*control.*SPIKEUSDT"):
        approve(d, STATS, SCREEN, ["WEAKUSDT", control], NOW, 0, 2.0, 0, "abc1234")
    assert d.to_json() == before


@pytest.fixture
def workdir(tmp_path):
    screen_dir = tmp_path / "reports" / SCREEN
    screen_dir.mkdir(parents=True)
    STATS.to_csv(screen_dir / "stats.csv", index=False)
    return tmp_path


def run(workdir, server, args):
    return CliRunner().invoke(
        main,
        ["dataset", *args],
        obj={
            "mexc": MexcClient(transport=httpx.MockTransport(server)),
            "data_root": workdir / "data",
            "reports_root": workdir / "reports",
            "cards_dir": workdir / "cards",
            "now": lambda: NOW,
            "commit": "abc1234",
        },
        prog_name="ttp",
    )


def test_approve_creates_definition_downloads_history_and_writes_card(workdir):
    server = FakeMexc()
    result = run(
        workdir,
        server,
        [
            "approve",
            SCREEN,
            "spike/usdt",
            "WEAKUSDT",
            "--name",
            "spikes-v1",
            "--days",
            "2",
        ],
    )
    assert result.exit_code == 0, result.output
    assert "dataset 'spikes-v1' version 1" in result.output

    store = DatasetStore(workdir / "data")
    d = load_definition(store, "spikes-v1")
    assert [m.market for m in d.candidates] == ["SPIKEUSDT", "WEAKUSDT"]
    controls = [m.market for m in d.controls]
    assert len(controls) == 2 and controls[0] in {"Q1USDT", "Q2USDT", "Q3USDT"}

    # Klines and trades were downloaded for all four markets.
    series = store.series("spikes-v1")
    assert {(s.market, s.data_type.name) for s in series} == {
        (m, t) for m in d.symbols for t in (KLINES_1M.name, TRADES.name)
    }
    klines = store.read("spikes-v1", "mexc", "SPIKEUSDT", KLINES_1M)
    assert len(klines) == 2 * 1440
    assert klines["open_time"].iloc[-1] == pd.Timestamp("2026-10-28 11:59", tz="UTC")
    trades = store.read("spikes-v1", "mexc", controls[0], TRADES)
    assert len(trades) == 26 * 60
    assert trades["time"].iloc[-1] == pd.Timestamp("2026-10-28 12:00", tz="UTC")

    card = (workdir / "cards" / "spikes-v1.md").read_text(encoding="utf-8")
    assert card.startswith("# spikes-v1\n")
    assert "## Definition" in card and "## Series" in card
    assert (
        f"| SPIKEUSDT | candidate | {controls[0]} | {SCREEN} | 0.90 | 20 | 60,000 |  | 1 |"
        in card
    )
    assert f"| {controls[0]} | control | SPIKEUSDT | {SCREEN} | 0.00 | 0 |" in card
    assert (
        f"- v1 on 2026-10-28T12:00:30+00:00: screen `{SCREEN}`, seed 0, band x2" in card
    )
    assert "`GET /api/v3/aggTrades`" in card and "`GET /api/v3/klines`" in card
    assert "| mexc | SPIKEUSDT | trades |" in card


def test_reapprove_adds_a_version_and_refreshes_without_duplicates(workdir):
    server = FakeMexc()
    assert (
        run(
            workdir,
            server,
            ["approve", SCREEN, "SPIKEUSDT", "--name", "d", "--days", "1"],
        ).exit_code
        == 0
    )
    first = len(server.requests)
    result = run(
        workdir, server, ["approve", SCREEN, "SPIKEUSDT", "--name", "d", "--days", "1"]
    )
    assert result.exit_code == 0, result.output
    assert "all markets already in it" in result.output
    # Klines were complete; only the trades were asked again (from the last print on).
    assert all(path == "/api/v3/aggTrades" for path, _ in server.requests[first:])
    store = DatasetStore(workdir / "data")
    assert len(store.read("d", "mexc", "SPIKEUSDT", TRADES)) == 26 * 60

    result = run(
        workdir, server, ["approve", SCREEN, "WEAKUSDT", "--name", "d", "--days", "1"]
    )
    assert result.exit_code == 0, result.output
    assert "version 2" in result.output
    d = load_definition(store, "d")
    assert d.version == 2 and len(d.markets) == 4
    assert len(store.series("d")) == 8


def test_no_download_writes_definition_and_card_only(workdir):
    server = FakeMexc()
    result = run(
        workdir,
        server,
        ["approve", SCREEN, "SPIKEUSDT", "--name", "d", "--no-download"],
    )
    assert result.exit_code == 0, result.output
    assert server.requests == []
    assert load_definition(DatasetStore(workdir / "data"), "d").version == 1
    card = (workdir / "cards" / "d.md").read_text(encoding="utf-8")
    assert "## Definition" in card and "- Date range: no data stored" in card


def test_approve_reports_bad_screen_markets_and_venue_errors(workdir):
    result = run(workdir, FakeMexc(), ["approve", "nope", "SPIKEUSDT", "--name", "d"])
    assert result.exit_code == 1 and "no screen 'nope'" in result.output

    result = run(workdir, FakeMexc(), ["approve", SCREEN, "NOPEUSDT", "--name", "d"])
    assert result.exit_code == 1 and "not in the screen: NOPEUSDT" in result.output

    result = run(
        workdir,
        FakeMexc(fail={"SPIKEUSDT"}),
        ["approve", SCREEN, "SPIKEUSDT", "--name", "d", "--days", "1"],
    )
    assert result.exit_code == 1, result.output
    assert "SPIKEUSDT: FAILED: MEXC /api/v3/klines returned HTTP 400" in result.output
    assert "re-run to retry" in result.output
    assert "Traceback" not in result.output
    # The definition and card are kept so the re-run only needs the download.
    assert load_definition(DatasetStore(workdir / "data"), "d").version == 1
    assert (workdir / "cards" / "d.md").is_file()


def test_cli_refuses_to_approve_a_control(workdir):
    args = ["--name", "d", "--no-download"]
    assert (
        run(workdir, FakeMexc(), ["approve", SCREEN, "SPIKEUSDT", *args]).exit_code == 0
    )
    store = DatasetStore(workdir / "data")
    control = load_definition(store, "d").controls[0].market
    result = run(workdir, FakeMexc(), ["approve", SCREEN, control, *args])
    assert result.exit_code == 1, result.output
    assert control in result.output and "control" in result.output
    assert "all markets already in it" not in result.output
    assert load_definition(store, "d").version == 1


def test_list_and_show(workdir):
    assert "no approved datasets" in run(workdir, FakeMexc(), ["list"]).output
    result = run(workdir, FakeMexc(), ["show", "d"])
    assert result.exit_code == 1 and "no approved dataset 'd'" in result.output

    server = FakeMexc()
    run(workdir, server, ["approve", SCREEN, "SPIKEUSDT", "--name", "d", "--days", "1"])
    run(
        workdir,
        server,
        ["approve", SCREEN, "WEAKUSDT", "--name", "other", "--no-download"],
    )

    result = run(workdir, server, ["list"])
    assert result.exit_code == 0, result.output
    lines = result.output.splitlines()
    assert lines[0].startswith("DATASET")
    assert lines[1].split()[:4] == ["d", "1", "1", "1"]
    assert lines[2].split()[:4] == ["other", "1", "1", "1"]

    result = run(workdir, server, ["show", "d"])
    assert result.exit_code == 0, result.output
    d = load_definition(DatasetStore(workdir / "data"), "d")
    control = d.controls[0].market
    assert "dataset 'd' version 1 on mexc" in result.output
    assert f"SPIKEUSDT      candidate {control:<14} {SCREEN}" in result.output
    assert f"{control:<14} control   SPIKEUSDT" in result.output
    assert (
        f"v1 2026-10-28T12:00:30+00:00 screen {SCREEN} seed 0 band x2 commit abc1234"
        in result.output
    )
    assert (
        "SPIKEUSDT      klines_1m  2026-10-27 12:00 to 2026-10-28 11:59 UTC, 1,440 rows"
        in result.output
    )
    assert (
        f"{control:<14} trades     2026-10-27 10:01 to 2026-10-28 12:00 UTC, 1,560 rows"
        in result.output
    )

    result = run(workdir, server, ["show", "other"])
    assert result.exit_code == 0 and "stored series: none" in result.output
