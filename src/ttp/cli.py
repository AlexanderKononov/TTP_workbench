"""Command-line entry point: `ttp`."""

from datetime import UTC, datetime, timedelta
from pathlib import Path

import click

from ttp import __version__
from ttp.data.cards import current_commit, render_card, write_card
from ttp.data.downloader import download_klines
from ttp.data.store import DATASET_NAME, DatasetStore
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
