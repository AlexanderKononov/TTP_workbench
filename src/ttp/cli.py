"""Command-line entry point: `ttp`."""

import os
from datetime import UTC, datetime, timedelta
from pathlib import Path

import click
import pandas as pd

from ttp import __version__
from ttp.data.cards import current_commit, render_card, write_card
from ttp.data.downloader import download_klines
from ttp.data.store import DATASET_NAME, DatasetStore
from ttp.notify import (
    DEV_BOT,
    ENV_FILE,
    NotifyError,
    TelegramNotifier,
    env_names,
    load_bot_config,
)
from ttp.screener.report import REPORTS_ROOT, send_report, write_report
from ttp.screener.screen import Screen, ScreenParams, scan, universe
from ttp.screener.universe import thin_markets
from ttp.venues.mexc import MexcClient, MexcError


@click.group()
@click.version_option(__version__, prog_name="ttp")
@click.pass_context
def main(ctx: click.Context) -> None:
    """Human-confirmed crypto trading system."""
    ctx.ensure_object(dict)


@main.command()
@click.option(
    "--max-volume",
    type=click.FloatRange(min=0),
    required=True,
    help="Upper bound of 24h quote volume, USD.",
)
@click.option(
    "--min-volume",
    type=click.FloatRange(min=0),
    default=0.0,
    show_default=True,
    help="Lower bound of 24h quote volume, USD.",
)
@click.pass_context
def markets(ctx: click.Context, max_volume: float, min_volume: float) -> None:
    """List API-tradable MEXC USDT/USDC markets within a 24h volume band."""
    if min_volume > max_volume:
        raise click.BadParameter(
            "must not exceed --max-volume", param_hint="--min-volume"
        )
    client = ctx.obj.get("mexc") or MexcClient()
    try:
        with client:
            found = thin_markets(
                client.exchange_info(), client.tickers_24h(), max_volume, min_volume
            )
    except MexcError as exc:
        raise click.ClickException(str(exc)) from exc
    click.echo(f"{'MARKET':<20} {'QUOTE':<5} {'24H VOLUME (USD)':>18}")
    for m in found:
        click.echo(f"{m.symbol:<20} {m.quote_asset:<5} {m.quote_volume_24h:>18,.2f}")
    click.echo(
        f"{len(found)} markets between ${min_volume:,.0f} and ${max_volume:,.0f}"
    )


DATA_ROOT = Path("data/datasets")
CARDS_DIR = Path("docs/knowledge-base/datasets")


@main.group()
def download() -> None:
    """Download available venue history into a dataset."""


def _market(value: str) -> str:
    return value.upper().replace("/", "").replace("-", "").replace("_", "")


def _dataset(ctx: click.Context, param: click.Parameter, value: str) -> str:
    if not DATASET_NAME.fullmatch(value):
        raise click.BadParameter("use lowercase letters, digits, '.', '_', '-'")
    return value


@download.command("klines")
@click.argument("market")
@click.option(
    "--days",
    type=click.IntRange(min=1),
    required=True,
    help="How many days back from now (MEXC keeps about 30 days of 1m klines).",
)
@click.option(
    "--dataset",
    default="adhoc",
    show_default=True,
    callback=_dataset,
    help="Dataset name.",
)
@click.pass_context
def download_klines_cmd(
    ctx: click.Context, market: str, days: int, dataset: str
) -> None:
    """Download 1-minute klines of a MEXC MARKET (e.g. ADXUSDT) into a dataset.

    Only minutes the dataset lacks are fetched, so re-running fills gaps.
    Run from the repo root: data goes to data/datasets/, the dataset card to
    docs/knowledge-base/datasets/.
    """
    market = _market(market)
    obj = ctx.obj
    store = DatasetStore(obj.get("data_root", DATA_ROOT))
    now = obj.get("now", lambda: datetime.now(UTC))()
    client = obj.get("mexc") or MexcClient()
    try:
        with client:
            result = download_klines(
                client, store, dataset, market, now - timedelta(days=days), now
            )
    except MexcError as exc:
        raise click.ClickException(str(exc)) from exc
    card = write_card(
        Path(obj.get("cards_dir", CARDS_DIR)),
        dataset,
        render_card(
            store,
            dataset,
            location=store.dataset_dir(dataset).as_posix(),
            collected_by=obj.get("commit") or current_commit(),
            collected_on=now.date(),
        ),
    )
    fmt = "%Y-%m-%d %H:%M"
    click.echo(
        f"{market} klines_1m, {result.start:{fmt}} to {result.end:{fmt}} UTC "
        f"-> dataset '{dataset}'"
    )
    click.echo(
        f"fetched {result.fetched} rows in {result.requested_ranges} missing ranges, "
        f"{result.added} new"
    )
    if result.still_missing:
        click.echo(
            f"{result.still_missing} minutes still missing "
            "(MEXC returned no candles for them; see the dataset card)"
        )
    click.echo(f"dataset card: {card.as_posix()}")


@main.command()
@click.option(
    "--max-volume",
    type=click.FloatRange(min=0),
    default=100_000,
    show_default=True,
    help="Upper bound of 24h quote volume, USD.",
)
@click.option(
    "--min-volume",
    type=click.FloatRange(min=0),
    default=0.0,
    show_default=True,
    help="Lower bound of 24h quote volume, USD.",
)
@click.option(
    "--hours",
    type=click.IntRange(min=1, max=30 * 24),
    default=24,
    show_default=True,
    help="Hours of 1-minute klines to scan, back from now.",
)
@click.option(
    "--top",
    type=click.IntRange(min=1),
    default=10,
    show_default=True,
    help="How many candidates to chart and list.",
)
@click.option(
    "--min-wick",
    type=click.FloatRange(min=0, min_open=True),
    default=0.02,
    show_default=True,
    help="Smallest upper wick counted as a spike, as a fraction of the candle body top.",
)
@click.option(
    "--chart-hours",
    type=click.IntRange(min=1),
    default=6,
    show_default=True,
    help="Hours shown on each candidate's chart.",
)
@click.option(
    "--include-st",
    is_flag=True,
    help="Also scan markets MEXC flags 'st' (special treatment); excluded by default.",
)
@click.option(
    "--notify",
    is_flag=True,
    help=(
        "Also send the summary and the top candidates' charts to the dev Telegram "
        f"bot ({' / '.join(env_names(DEV_BOT))} from the environment or .env)."
    ),
)
@click.pass_context
def screen(
    ctx: click.Context,
    max_volume: float,
    min_volume: float,
    hours: int,
    top: int,
    min_wick: float,
    chart_hours: int,
    include_st: bool,
    notify: bool,
) -> None:
    """Rank thin MEXC markets by recurring upper wicks and write a chart report.

    Scans every API-tradable USDT/USDC market in the volume band. Klines are
    cached in the 'screener' dataset under data/datasets/, so re-running over
    the same window is free. The report goes to reports/screens/<screen-id>/.
    Run from the repo root.
    """
    if min_volume > max_volume:
        raise click.BadParameter(
            "must not exceed --max-volume", param_hint="--min-volume"
        )
    obj = ctx.obj
    params = ScreenParams(max_volume, min_volume, hours, min_wick, include_st)
    store = DatasetStore(obj.get("data_root", DATA_ROOT))
    now = obj.get("now", lambda: datetime.now(UTC))()
    client = obj.get("mexc") or MexcClient()
    try:
        with client:
            markets = universe(client, params)
            with click.progressbar(
                length=len(markets),
                label=f"scanning {len(markets)} markets",
                item_show_func=lambda m: m.symbol if m else "",
            ) as bar:
                result = scan(
                    client,
                    store,
                    markets,
                    now,
                    params,
                    len(markets),
                    progress=lambda m: bar.update(1, m),
                )
    except MexcError as exc:
        raise click.ClickException(str(exc)) from exc
    out = write_report(
        result,
        store,
        Path(obj.get("reports_root", REPORTS_ROOT)),
        top,
        min(chart_hours, hours),
    )
    click.echo(
        f"{'#':>3} {'MARKET':<14} {'SCORE':>7} {'EVENTS':>6} {'WICK':>7} "
        f"{'INTERVAL':>8} {'REGULAR':>7} {'24H VOLUME':>12}"
    )
    for r in result.table.head(top).itertuples(index=False):
        interval = (
            "-" if pd.isna(r.interval_median_min) else f"{r.interval_median_min:.0f}"
        )
        wick = "-" if pd.isna(r.wick_median) else f"{r.wick_median:.2%}"
        click.echo(
            f"{r.rank:>3} {r.market:<14} {r.score:>7.2f} {r.wick_count:>6} {wick:>7} "
            f"{interval:>8} {r.regularity:>7.2f} {r.volume_24h:>12,.0f}"
        )
    click.echo(
        f"scanned {len(result.table)} of {result.universe} markets, "
        f"{result.start:%Y-%m-%d %H:%M} to {result.end:%Y-%m-%d %H:%M} UTC"
    )
    if result.skipped:
        n = len(result.skipped)
        click.echo(f"skipped {n} market{'s' if n != 1 else ''} (see report)")
    click.echo(f"report: {out.as_posix()}")
    click.echo(f"screen id: {result.screen_id}")
    if notify:
        _notify_screen(ctx, result, out, top)


def _notify_screen(ctx: click.Context, result: Screen, out: Path, top: int) -> None:
    """Send the screen to the dev bot; a missing config warns, a failed send errors."""
    obj = ctx.obj
    notifier = obj.get("telegram")
    if notifier is None:
        config = load_bot_config(
            DEV_BOT, obj.get("env", os.environ), obj.get("env_file", ENV_FILE)
        )
        if config is None:
            token, chat = env_names(DEV_BOT)
            click.echo(
                f"warning: not sent to Telegram: set {token} and {chat} "
                "in the environment or .env",
                err=True,
            )
            return
        notifier = TelegramNotifier(config)
    try:
        with notifier:
            charts = send_report(notifier, result, out, top)
    except NotifyError as exc:
        raise click.ClickException(f"Telegram: {exc}") from exc
    click.echo(
        f"sent to Telegram: summary and {charts} chart{'s' if charts != 1 else ''}"
    )
