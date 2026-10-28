import importlib

import pytest
from click.testing import CliRunner

from ttp import __version__
from ttp.cli import main

SUBPACKAGES = [
    "core",
    "strategies",
    "data",
    "feeds",
    "venues",
    "venues.mexc",
    "execution",
    "engine",
    "screener",
    "notify",
]


@pytest.mark.parametrize("name", SUBPACKAGES)
def test_architecture_subpackages_import(name):
    importlib.import_module(f"ttp.{name}")


def test_cli_help_lists_usage():
    result = CliRunner().invoke(main, ["--help"], prog_name="ttp")
    assert result.exit_code == 0
    assert "Usage: ttp" in result.output


def test_cli_version():
    result = CliRunner().invoke(main, ["--version"])
    assert result.exit_code == 0
    assert __version__ in result.output
