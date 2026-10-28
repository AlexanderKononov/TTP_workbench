"""Command-line entry point: `ttp`."""

import os
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import UTC, datetime, timedelta
from pathlib import Path

import click
import pandas as pd

from ttp import __version__
from ttp.data.cards import current_commit, render_card, write_card
from ttp.data.datasets import (
    DatasetDefinition,
    approve,
    list_definitions,
    load_definition,
    load_screen_stats,
    save_definition,
)
from ttp.data.downloader import download_klines, download_trades
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
from ttp.venues.mexc import (
    AGG_TRADES_HISTORY_HOURS,
    MexcClient,
    MexcError,
    MexcRateLimited,
)
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
    default=24,
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
        f"{'#':>3} {'MARKET':<14} {'SCORE':>7} {'RETURNED':>8} {'EVENTS':>6} "
        f"{'WICK':>7} {'RETRACE':>7} {'BASE':>7} {'ACTIVE':>7} {'INTERVAL':>8} "
        f"{'REGULAR':>7} {'24H VOLUME':>12}"
    )
    for r in result.table.head(top).itertuples(index=False):
        interval = (
            "-" if pd.isna(r.interval_median_min) else f"{r.interval_median_min:.0f}"
        )
        wick, retrace, base, active = (
            "-" if pd.isna(x) else f"{x:.2%}"
            for x in (r.wick_median, r.retrace_median, r.base_range, r.active_share)
        )
        click.echo(
            f"{r.rank:>3} {r.market:<14} {r.score:>7.2f} {r.returned_events:>8} "
            f"{r.wick_count:>6} {wick:>7} {retrace:>7} {base:>7} {active:>7} "
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


@main.group()
def dataset() -> None:
    """Approved datasets: candidates from a screen plus matched control markets."""


DOWNLOAD_WORKERS = 4


def _download_history(
    client: MexcClient, store: DatasetStore, name: str, markets: list[str], now, days
) -> dict[str, str]:
    """Download klines and trades for every market, a few at a time; returns failures."""
    kline_start = now - timedelta(days=days)
    trade_start = now - timedelta(hours=AGG_TRADES_HISTORY_HOURS + 2)

    def one(market: str) -> str:
        k = download_klines(client, store, name, market, kline_start, now)
        t = download_trades(client, store, name, market, trade_start, now)
        return (
            f"{market}: klines {k.fetched} fetched, {k.added} new, "
            f"{k.still_missing} min missing; trades {t.fetched} fetched, {t.added} new"
        )

    failed: dict[str, str] = {}
    with ThreadPoolExecutor(max_workers=DOWNLOAD_WORKERS) as pool:
        futures = {pool.submit(one, m): m for m in markets}
        try:
            for future in as_completed(futures):
                market = futures[future]
                try:
                    click.echo(future.result())
                except MexcRateLimited:
                    raise
                except MexcError as exc:
                    failed[market] = str(exc)
                    click.echo(f"{market}: FAILED: {exc}")
        except MexcRateLimited:
            pool.shutdown(cancel_futures=True)
            raise
    return failed


@dataset.command("approve")
@click.argument("screen_id")
@click.argument("markets", nargs=-1, required=True)
@click.option("--name", required=True, callback=_dataset, help="Dataset name.")
@click.option(
    "--seed",
    type=int,
    default=0,
    show_default=True,
    help="Seed of the control draw; same screen, markets and seed pick the same controls.",
)
@click.option(
    "--band",
    type=click.FloatRange(min=1, min_open=True),
    default=2.0,
    show_default=True,
    help="Volume band ratio: a control's 24h volume lies within candidate / band "
    "to candidate x band.",
)
@click.option(
    "--max-control-events",
    type=click.IntRange(min=0, max=2),
    default=0,
    show_default=True,
    help="Most spike events a control may show in the screen.",
)
@click.option(
    "--days",
    type=click.IntRange(min=1),
    default=30,
    show_default=True,
    help="Days of 1m klines to download (MEXC keeps about 30).",
)
@click.option(
    "--no-download",
    is_flag=True,
    help="Write the definition and card only; download history later by re-running.",
)
@click.pass_context
def dataset_approve(
    ctx: click.Context,
    screen_id: str,
    markets: tuple[str, ...],
    name: str,
    seed: int,
    band: float,
    max_control_events: int,
    days: int,
    no_download: bool,
) -> None:
    """Approve MARKETS from screen SCREEN_ID into dataset NAME (gate 7).

    Each approved market gets one control market, drawn at random (seeded) from
    the same 24h-volume band among markets the screen found pattern-free. Then
    the kline and trade history MEXC still serves is downloaded for every market
    of the dataset, and the dataset card is written. Re-running with more markets
    adds a version; re-running with the same markets just refreshes the history.
    Run from the repo root.
    """
    obj = ctx.obj
    store = DatasetStore(obj.get("data_root", DATA_ROOT))
    reports_root = Path(obj.get("reports_root", REPORTS_ROOT))
    now = obj.get("now", lambda: datetime.now(UTC))()
    commit = obj.get("commit") or current_commit()
    try:
        stats = load_screen_stats(reports_root, screen_id)
    except FileNotFoundError as exc:
        raise click.ClickException(str(exc)) from exc
    definition = load_definition(store, name) or DatasetDefinition(name)
    try:
        added = approve(
            definition,
            stats,
            screen_id,
            [_market(m) for m in markets],
            now,
            seed,
            band,
            max_control_events,
            commit,
        )
    except ValueError as exc:
        raise click.ClickException(str(exc)) from exc
    if added:
        save_definition(store, definition)
        click.echo(f"dataset '{name}' version {definition.version}: added")
        for m in added:
            if m.role == "candidate":
                click.echo(f"  {m.market:<14} candidate  control {m.paired_with}")
            else:
                click.echo(
                    f"  {m.market:<14} control    for {m.paired_with}, "
                    f"{m.wick_count} events, 24h vol {m.volume_24h:,.0f}, band x{m.band:g}"
                )
    else:
        click.echo(
            f"dataset '{name}' version {definition.version}: all markets already in it"
        )
    failed: dict[str, str] = {}
    if not no_download:
        client = obj.get("mexc") or MexcClient()
        try:
            with client:
                failed = _download_history(
                    client, store, name, definition.symbols, now, days
                )
        except MexcError as exc:
            raise click.ClickException(str(exc)) from exc
    card = write_card(
        Path(obj.get("cards_dir", CARDS_DIR)),
        name,
        render_card(
            store,
            name,
            location=store.dataset_dir(name).as_posix(),
            collected_by=commit,
            collected_on=now.date(),
        ),
    )
    click.echo(f"dataset card: {card.as_posix()}")
    if failed:
        raise click.ClickException(
            f"history download failed for {', '.join(sorted(failed))}; re-run to retry"
        )


@dataset.command("list")
@click.pass_context
def dataset_list(ctx: click.Context) -> None:
    """List approved datasets."""
    store = DatasetStore(ctx.obj.get("data_root", DATA_ROOT))
    definitions = list_definitions(store)
    if not definitions:
        click.echo("no approved datasets (see `ttp dataset approve`)")
        return
    click.echo(
        f"{'DATASET':<24} {'VERSION':>7} {'CANDIDATES':>10} {'CONTROLS':>8}  LAST APPROVED"
    )
    for d in definitions:
        click.echo(
            f"{d.name:<24} {d.version:>7} {len(d.candidates):>10} {len(d.controls):>8}  "
            f"{d.approvals[-1].approved_on}"
        )


@dataset.command("show")
@click.argument("name", callback=_dataset)
@click.pass_context
def dataset_show(ctx: click.Context, name: str) -> None:
    """Show an approved dataset: its markets, controls and stored series."""
    store = DatasetStore(ctx.obj.get("data_root", DATA_ROOT))
    d = load_definition(store, name)
    if d is None:
        raise click.ClickException(f"no approved dataset '{name}'")
    click.echo(f"dataset '{d.name}' version {d.version} on {d.venue}")
    click.echo(
        f"{'MARKET':<14} {'ROLE':<9} {'PAIRED WITH':<14} {'SCREEN':<16} {'SCORE':>6} "
        f"{'EVENTS':>6} {'24H VOLUME':>11} {'VER':>3}"
    )
    for m in d.markets:
        click.echo(
            f"{m.market:<14} {m.role:<9} {m.paired_with:<14} {m.screen_id:<16} "
            f"{m.score:>6.2f} {m.wick_count:>6} {m.volume_24h:>11,.0f} {m.version:>3}"
        )
    click.echo("approvals:")
    for a in d.approvals:
        click.echo(
            f"  v{a.version} {a.approved_on} screen {a.screen_id} seed {a.seed} "
            f"band x{a.band:g} commit {a.commit}"
        )
    series = store.series(name)
    click.echo("stored series:" if series else "stored series: none")
    fmt = "%Y-%m-%d %H:%M"
    for s in series:
        click.echo(
            f"  {s.market:<14} {s.data_type.name:<10} {s.first:{fmt}} to "
            f"{s.last:{fmt}} UTC, {s.rows:,} rows"
        )
