"""Dataset cards: the knowledge-base description of a dataset, generated from storage.

Follows the template in docs/knowledge-base/README.md. The card is rewritten from
what is stored each time data is added, so it always matches the dataset.
"""

import subprocess
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import pandas as pd

from ttp.data.datasets import DatasetDefinition, load_definition
from ttp.data.store import DatasetStore


@dataclass(frozen=True)
class SourceInfo:
    source: str
    resolution: str
    quirks: tuple[str, ...]


# How each (venue, data type) is obtained; later data types add entries here.
SOURCES = {
    ("mexc", "klines_1m"): SourceInfo(
        source="MEXC spot public REST `GET /api/v3/klines`, interval `1m`",
        resolution="OHLCV 1m (`klines_1m`); `open_time` is the candle open, UTC",
        quirks=(
            (
                "MEXC serves only about the last 30 days of 1m klines; older requests "
                "return nothing (checked 2026-10-28)."
            ),
            (
                "Minutes without trades come back as flat candles with zero volume, so "
                "they are stored, not gaps. A gap below means MEXC returned no candle."
            ),
            (
                "Only closed candles are stored (the download range ends at the current "
                "minute)."
            ),
        ),
    ),
    ("mexc", "trades"): SourceInfo(
        source="MEXC spot public REST `GET /api/v3/aggTrades`",
        resolution=(
            "trade prints (`trades`): time, price, quantity, aggressor side; MEXC "
            "aggregates prints of one price, side and second into one row"
        ),
        quirks=(
            (
                "MEXC serves only about the last 24 h of aggregate trades, timestamped "
                "to the second and without trade ids (checked 2026-10-28), so the "
                "order of prints within one second is not kept; a dataset's trade "
                "history starts where its first download reached."
            ),
            (
                "Trades have no grid, so missing hours cannot be told from quiet ones; "
                "gaps are not listed for them. Recorded trades (M1) come with a gap log."
            ),
        ),
    ),
}


def current_commit(repo: Path | str = ".") -> str:
    """Short HEAD hash, marked `-dirty` if tracked files changed; `unknown` without git."""

    def run(*args: str) -> str:
        return subprocess.run(
            ["git", *args], cwd=repo, capture_output=True, text=True, check=True
        ).stdout.strip()

    try:
        commit = run("rev-parse", "--short", "HEAD")
        return commit + ("-dirty" if run("status", "--porcelain", "-uno") else "")
    except (OSError, subprocess.CalledProcessError):
        return "unknown"


def _t(ts: pd.Timestamp) -> str:
    return ts.strftime("%Y-%m-%d %H:%M UTC")


def definition_lines(d: DatasetDefinition) -> list[str]:
    """The approved markets, their controls and the approvals behind them."""
    lines = [
        "## Definition",
        "",
        (
            f"Version {d.version}: {len(d.candidates)} candidate(s) approved from the "
            "screener, each paired with one control market drawn at random from "
            "the same 24h-volume band among markets the screen found pattern-free."
        ),
        "",
        "| Market | Role | Paired with | Screen | Score | Events | 24h volume | Band | Version |",
        "|---|---|---|---|--:|--:|--:|--:|--:|",
    ]
    for m in d.markets:
        band = "" if m.role == "candidate" else f"x{m.band:g}"
        lines.append(
            f"| {m.market} | {m.role} | {m.paired_with} | {m.screen_id} | {m.score:.2f} "
            f"| {m.wick_count} | {m.volume_24h:,.0f} | {band} | {m.version} |"
        )
    lines += ["", "Approvals:", ""]
    for a in d.approvals:
        lines.append(
            f"- v{a.version} on {a.approved_on}: screen `{a.screen_id}`, seed {a.seed}, "
            f"band x{a.band:g}, controls with at most {a.max_control_events} spike "
            f"event(s), `ttp` at commit `{a.commit}`"
        )
    return lines


def render_card(
    store: DatasetStore,
    dataset: str,
    location: str,
    collected_by: str,
    collected_on: date,
    max_gaps: int = 20,
) -> str:
    series = store.series(dataset)
    infos = [SOURCES.get((s.venue, s.data_type.name)) for s in series]
    unique = list(dict.fromkeys(i for i in infos if i is not None))
    markets = sorted({f"{s.venue.upper()} {s.market}" for s in series})
    if series:
        date_range = (
            f"{_t(min(s.first for s in series))} to {_t(max(s.last for s in series))}"
        )
    else:
        date_range = "no data stored"

    rows, gap_lines = [], []
    for s in series:
        gaps = store.gaps(dataset, s.venue, s.market, s.data_type)
        step = s.data_type.interval
        missing = sum((hi - lo) // step for lo, hi in gaps) if step else 0
        rows.append(
            f"| {s.venue} | {s.market} | {s.data_type.name} | {_t(s.first)} | "
            f"{_t(s.last)} | {s.rows} | {missing} |"
        )
        for lo, hi in gaps[:max_gaps]:
            gap_lines.append(
                f"- {s.market} {s.data_type.name}: {_t(lo)} to {_t(hi)} (exclusive)"
            )
        if len(gaps) > max_gaps:
            gap_lines.append(
                f"- {s.market} {s.data_type.name}: {len(gaps) - max_gaps} more gaps"
            )

    quirks = [q for i in unique for q in i.quirks]
    gap_summary = "none inside the stored range" if not gap_lines else "see Gaps below"
    lines = [
        f"# {dataset}",
        "",
        "<!-- Generated by `ttp` from the stored data; edits here are overwritten. -->",
        "",
        f"- Source: {'; '.join(i.source for i in unique) or 'n/a'}",
        f"- Venue(s) & markets: {', '.join(markets) or 'none'}",
        f"- Data type & resolution: {'; '.join(i.resolution for i in unique) or 'n/a'}",
        f"- Date range: {date_range}",
        (
            f"- Location: `{location}` (Parquet, `venue=/market=/type=/date=` partitions; "
            "gitignored, local only)"
        ),
        (
            f"- Collected by: `ttp` at commit `{collected_by}`, last updated on "
            f"{collected_on.isoformat()}"
        ),
        f"- Known gaps & quirks: {gap_summary}. " + " ".join(quirks),
        "",
    ]
    definition = load_definition(store, dataset)
    if definition is not None:
        lines += [*definition_lines(definition), ""]
    lines += [
        "## Series",
        "",
        "| Venue | Market | Data type | First | Last | Rows | Missing steps |",
        "|---|---|---|---|---|---|---|",
        *rows,
    ]
    if gap_lines:
        lines += ["", "## Gaps", "", *gap_lines]
    return "\n".join(lines) + "\n"


def write_card(cards_dir: Path, dataset: str, text: str) -> Path:
    cards_dir.mkdir(parents=True, exist_ok=True)
    path = cards_dir / f"{dataset}.md"
    path.write_text(text, encoding="utf-8", newline="\n")
    return path
