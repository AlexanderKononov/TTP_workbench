"""Command-line entry point: `ttp`."""

import sys
import time
from datetime import UTC, datetime, timedelta
from pathlib import Path

import click

from ttp import __version__
from ttp.data.cards import current_commit, render_card, write_card
from ttp.data.downloader import download_klines
from ttp.data.store import DATASET_NAME, DatasetStore
from ttp.screener.universe import thin_markets
from ttp.venues.mexc import MexcClient, MexcError
from ttp.venues.mexc.book import BookEvent, DepthDiff, OrderBook, Trade
from ttp.venues.mexc.stream import LiveBooks, MexcMarketStream, StreamStatus


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
@click.argument("market")
@click.option(
    "--seconds",
    type=click.FloatRange(min=0),
    default=None,
    help="Stop after this many seconds (default: run until Ctrl-C).",
)
@click.pass_context
def watch(ctx: click.Context, market: str, seconds: float | None) -> None:
    """Show the live top of book and trades of a MEXC MARKET (e.g. ADXUSDT).

    The book is built from a REST snapshot and kept in sync from the WebSocket
    depth diffs; gaps and disconnects are shown and trigger a resync.
    """
    market = _market(market)
    obj = ctx.obj
    client = obj.get("mexc") or MexcClient()
    stream = obj.get("stream", MexcMarketStream)([market])
    books = LiveBooks([market], client, stream)
    clock = obj.get("clock", time.monotonic)
    deadline = None if seconds is None else clock() + seconds
    last_top = None
    try:
        with client:
            for event in books.events():
                line = _watch_line(event, books, last_top)
                if line:
                    _echo(line)
                if isinstance(event, DepthDiff | BookEvent):
                    book = books.book(market)
                    top = (book.best_bid, book.best_ask) if book else None
                    if book and top != last_top and isinstance(event, BookEvent):
                        _echo(_top_line(event.time_ms, market, book))  # after a sync
                    last_top = top
                if isinstance(event, StreamStatus) and event.kind == "error":
                    raise click.ClickException(f"MEXC stream error: {event.detail}")
                if deadline is not None and clock() >= deadline:
                    break
    except MexcError as exc:
        raise click.ClickException(str(exc)) from exc
    except KeyboardInterrupt:
        click.echo("stopped")


def _watch_line(event: object, books: LiveBooks, last_top: object) -> str | None:
    if isinstance(event, Trade):
        return (
            f"{_hms(event.time_ms)} {event.market} TRADE {event.side:<4} "
            f"{event.price:g} x {event.quantity:g}"
        )
    if isinstance(event, DepthDiff):
        book = books.book(event.market)
        if book is None or (book.best_bid, book.best_ask) == last_top:
            return None
        return _top_line(event.time_ms, event.market, book)
    if isinstance(event, BookEvent):
        return (
            f"{_hms(event.time_ms)} {event.market} {event.kind.upper()} {event.detail}"
        )
    if isinstance(event, StreamStatus):
        return f"{_hms(event.time_ms)} stream {event.kind} {event.detail}".rstrip()
    return None


def _echo(line: str) -> None:
    """Print a line even on a console that cannot encode the venue's text (cp1252)."""
    encoding = getattr(sys.stdout, "encoding", None) or "utf-8"
    click.echo(line.encode(encoding, "replace").decode(encoding))


def _top_line(time_ms: int | None, market: str, book: OrderBook) -> str:
    bid, ask = book.best_bid, book.best_ask
    spread = f"{(ask.price / bid.price - 1) * 100:.2f}%" if bid and ask else "n/a"
    bid_s = f"{bid.price:g} x {bid.quantity:g}" if bid else "-"
    ask_s = f"{ask.price:g} x {ask.quantity:g}" if ask else "-"
    return f"{_hms(time_ms)} {market} bid {bid_s} | ask {ask_s} | spread {spread}"


def _hms(time_ms: int | None) -> str:
    if not time_ms:
        return "--:--:--.---"
    return datetime.fromtimestamp(time_ms / 1000, UTC).strftime("%H:%M:%S.%f")[:-3]
