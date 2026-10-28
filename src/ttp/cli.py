"""Command-line entry point: `ttp`."""

import click

from ttp import __version__
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
