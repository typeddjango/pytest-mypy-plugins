from pathlib import Path
from typing import Final

from pytest_mypy_plugins.configs import load_mypy_plugins_config


def test_load_existing_config() -> None:
    root_pyproject1: Final = str(Path(__file__).parent / "pyproject3.toml")
    result = load_mypy_plugins_config(root_pyproject1)
    assert result == {
        "pretty": False,
        "show_column_numbers": True,
        "warn_unused_ignores": False,
    }


def test_load_missing_config() -> None:
    root_pyproject2: Final = str(Path(__file__).parent / "pyproject2.toml")
    result = load_mypy_plugins_config(root_pyproject2)
    assert result is None
