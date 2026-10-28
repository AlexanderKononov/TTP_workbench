"""Screen report: stats table (CSV + markdown) and a candle chart per top candidate.

Written under `reports/screens/<screen-id>/` (gitignored):

    report.md            top candidates, parameters, skipped markets
    stats.csv            every scanned market, ranked
    charts/NN-MARKET.png recent hours of 1m candles, spike candles marked

`send_report` delivers the summary and the top candidates' charts to Telegram.
"""

from pathlib import Path

import matplotlib
import numpy as np
import pandas as pd

from ttp.data.downloader import VENUE
from ttp.data.store import KLINES_1M, DatasetStore
from ttp.notify import TelegramNotifier
from ttp.screener.screen import SCREEN_DATASET, Screen
from ttp.screener.wicks import upper_wicks

matplotlib.use("Agg")
import matplotlib.pyplot as plt

REPORTS_ROOT = Path("reports/screens")
UP, DOWN, SPIKE, VOLUME = "#2e8b57", "#c0392b", "#8e44ad", "#95a5a6"
TIME_FMT = "%Y-%m-%d %H:%M"


def candle_chart(klines: pd.DataFrame, min_wick: float, title: str, path: Path) -> None:
    """Save a PNG of 1m candles (gaps closed up) with spike candles marked."""
    fig, (ax, axv) = plt.subplots(
        2, 1, figsize=(14, 6), sharex=True, gridspec_kw={"height_ratios": [4, 1]}
    )
    if not klines.empty:
        x = np.arange(len(klines))
        o, h, lo, c = (klines[k].to_numpy() for k in ("open", "high", "low", "close"))
        colors = np.where(c >= o, UP, DOWN)
        ax.vlines(x, lo, h, color=colors, linewidth=0.8)
        ax.bar(
            x,
            np.abs(c - o),
            bottom=np.minimum(o, c),
            width=0.7,
            color=colors,
            edgecolor=colors,
            linewidth=0.5,
        )
        spikes = (upper_wicks(klines) >= min_wick).to_numpy()
        ax.plot(x[spikes], h[spikes] * 1.003, "v", color=SPIKE, markersize=5)
        axv.bar(x, klines["volume"].to_numpy(), width=0.7, color=VOLUME)
        ticks = x[:: max(1, len(x) // 12)]
        axv.set_xticks(ticks)
        axv.set_xticklabels(
            klines["open_time"].dt.strftime("%H:%M").iloc[ticks], rotation=0
        )
        axv.set_xlabel(f"UTC, {klines['open_time'].iloc[0]:%Y-%m-%d}")
    ax.set_title(title)
    ax.set_ylabel("price")
    axv.set_ylabel("volume")
    for a in (ax, axv):
        a.grid(True, linewidth=0.3)
    fig.tight_layout()
    path.parent.mkdir(parents=True, exist_ok=True)
    fig.savefig(path, dpi=110)
    plt.close(fig)


def _pct(x: float) -> str:
    return "-" if pd.isna(x) else f"{x:.2%}"


def _num(x: float, fmt: str = ".0f") -> str:
    return "-" if pd.isna(x) else f"{x:{fmt}}"


def _short_usd(x: float) -> str:
    return f"${x / 1000:.0f}k" if x >= 10_000 else f"${x:,.0f}"


def chart_path(rank: int, market: str) -> Path:
    """A candidate's chart, relative to the report directory."""
    return Path("charts") / f"{rank:02d}-{market}.png"


def summary(screen: Screen, top: int) -> str:
    """Phone-sized plain-text summary: window, universe and the top candidates."""
    p = screen.params
    lines = [
        f"Screen {screen.screen_id}",
        f"{screen.start:{TIME_FMT}} to {screen.end:{TIME_FMT}} UTC, {p.hours} h",
        f"{len(screen.table)} of {screen.universe} markets scanned",
        (
            f"24h vol ${p.min_volume:,.0f}-${p.max_volume:,.0f}"
            f"{', incl. st' if p.include_st else ''}, wick >= {p.min_wick:.1%}"
        ),
        "",
        f" # {'market':<12} {'score':>5} ev {'wick':>5} {'int':>4} reg  24h vol",
    ]
    for r in screen.table.head(top).itertuples(index=False):
        interval = (
            "-" if pd.isna(r.interval_median_min) else f"{r.interval_median_min:.0f}m"
        )
        wick = "-" if pd.isna(r.wick_median) else f"{r.wick_median:.1%}"
        lines.append(
            f"{r.rank:>2} {r.market:<12} {r.score:>5.2f} {r.wick_count:>2} "
            f"{wick:>5} {interval:>4} {r.regularity:.2f} {_short_usd(r.volume_24h)}"
        )
    if screen.skipped:
        n = len(screen.skipped)
        lines.append(f"skipped {n} market{'s' if n != 1 else ''}")
    return "\n".join(lines)


def send_report(notifier: TelegramNotifier, screen: Screen, out: Path, top: int) -> int:
    """Send the summary, then each top candidate's chart. Returns charts sent."""
    notifier.send_text(summary(screen, top), monospace=True)
    sent = 0
    for r in screen.table.head(top).itertuples(index=False):
        notifier.send_photo(
            out / chart_path(r.rank, r.market),
            f"#{r.rank} {r.market}: score {r.score:.2f}, {r.wick_count} events, "
            f"typical wick {_pct(r.wick_median)}, interval "
            f"{_num(r.interval_median_min)} min, regularity {r.regularity:.2f}, "
            f"24h vol ${r.volume_24h:,.0f}",
        )
        sent += 1
    return sent


def write_report(
    screen: Screen,
    store: DatasetStore,
    reports_root: Path,
    top: int,
    chart_hours: int,
) -> Path:
    """Write the screen's report directory; returns its path."""
    out = reports_root / screen.screen_id
    out.mkdir(parents=True, exist_ok=True)
    screen.table.to_csv(out / "stats.csv", index=False)

    p = screen.params
    chart_start = screen.end - pd.Timedelta(hours=chart_hours)
    st_note = " (incl. `st`)" if p.include_st else " (`st` markets excluded)"
    lines = [
        f"# Screen {screen.screen_id}",
        "",
        (
            f"- Window: {screen.start:{TIME_FMT}} to {screen.end:{TIME_FMT}} UTC "
            f"({p.hours} h of MEXC 1m klines)"
        ),
        (
            f"- Universe: {screen.universe} API-tradable USDT/USDC markets with 24h "
            f"volume ${p.min_volume:,.0f} to ${p.max_volume:,.0f}{st_note}"
        ),
        (
            f"- Spike candle: upper wick >= {p.min_wick:.2%} of the body top; "
            "adjacent spike minutes are one event"
        ),
        (
            "- Returned event: retrace (high - last close) / (high - first open) "
            ">= 50%. Base range: median (high - low) / close of non-spike candles"
        ),
        (
            "- Score: returned events x typical wick x (1 + regularity), or 0 unless "
            ">= 3 returned events, median interval >= 10 min, regularity > 0 and "
            "typical wick >= 2 x base range. Regularity is 1 - cv(intervals between "
            "returned events), 1 = perfectly periodic"
        ),
        (
            f"- Scanned {len(screen.table)} markets, skipped {len(screen.skipped)}; "
            f"charts show the last {chart_hours} h"
        ),
        "",
        (
            "| # | Market | Score | Returned | Events | Typical wick | Retrace "
            "| Base range | Max wick | Interval (min) | Regularity | 24h volume | Chart |"
        ),
        "|--:|---|--:|--:|--:|--:|--:|--:|--:|--:|--:|--:|---|",
    ]
    for r in screen.table.head(top).itertuples(index=False):
        chart = chart_path(r.rank, r.market)
        klines = store.read(
            SCREEN_DATASET, VENUE, r.market, KLINES_1M, chart_start, screen.end
        )
        candle_chart(
            klines,
            p.min_wick,
            f"{r.market}  score {r.score:.2f}  returned {r.returned_events}/"
            f"{r.wick_count}  typical wick {_pct(r.wick_median)}  retrace "
            f"{_pct(r.retrace_median)}  base {_pct(r.base_range)}  interval "
            f"{_num(r.interval_median_min)} min  regularity {r.regularity:.2f}  "
            f"24h vol ${r.volume_24h:,.0f}",
            out / chart,
        )
        lines.append(
            f"| {r.rank} | {r.market} | {r.score:.2f} | {r.returned_events} "
            f"| {r.wick_count} | {_pct(r.wick_median)} | {_pct(r.retrace_median)} "
            f"| {_pct(r.base_range)} | {_pct(r.wick_max)} "
            f"| {_num(r.interval_median_min)} | {r.regularity:.2f} "
            f"| {r.volume_24h:,.0f} | [{chart.name}]({chart.as_posix()}) |"
        )
    if screen.skipped:
        lines += ["", "## Skipped", ""]
        lines += [f"- {m}: {why}" for m, why in sorted(screen.skipped.items())]
    lines += ["", "Full ranking: [stats.csv](stats.csv)", ""]
    (out / "report.md").write_text("\n".join(lines), encoding="utf-8")
    return out
