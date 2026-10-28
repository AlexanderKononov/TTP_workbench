"""Command-line entry point: `ttp`. Subcommands are added by later tickets."""

import click

from ttp import __version__


@click.group()
@click.version_option(__version__, prog_name="ttp")
def main() -> None:
    """Human-confirmed crypto trading system."""
