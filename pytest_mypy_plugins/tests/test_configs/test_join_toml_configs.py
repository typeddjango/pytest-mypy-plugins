from pathlib import Path
from textwrap import dedent
from typing import Callable, Final, Optional

import pytest

from pytest_mypy_plugins.configs import join_toml_configs

_ADDITIONAL_CONFIG: Final = """
[tool.mypy]
pretty = true
show_error_codes = false
show_traceback = true
"""

_ADDITIONAL_CONFIG_NO_TABLE: Final = """
pretty = true
show_error_codes = false
show_traceback = true
"""

_MYPY_PLUGINS_CONFIG: Final = {
    "pretty": False,
    "show_column_numbers": True,
    "warn_unused_ignores": False,
}

_PYPROJECT1: Final = str(Path(__file__).parent / "pyproject1.toml")
_PYPROJECT2: Final = str(Path(__file__).parent / "pyproject2.toml")


@pytest.fixture
def execution_path(tmpdir_factory: pytest.TempdirFactory) -> Path:
    return Path(tmpdir_factory.mktemp("testproject", numbered=True))


_AssertFileContents = Callable[[Optional[str], str], None]


@pytest.fixture
def assert_file_contents() -> _AssertFileContents:
    def factory(filename: Optional[str], expected: str) -> None:
        assert filename

        expected = dedent(expected).strip()
        with open(filename) as f:
            contents = f.read().strip()
        assert contents == expected

    return factory


@pytest.mark.parametrize(
    "additional_config",
    [
        _ADDITIONAL_CONFIG,
        _ADDITIONAL_CONFIG_NO_TABLE,
    ],
)
def test_join_existing_config(
    execution_path: Path, assert_file_contents: _AssertFileContents, additional_config: str
) -> None:
    filepath = join_toml_configs(_PYPROJECT1, additional_config, execution_path)

    assert_file_contents(
        filepath,
        """
        [tool.mypy]
        warn_unused_ignores = true
        pretty = true
        show_error_codes = false
        show_traceback = true
        """,
    )


def test_join_existing_config1(execution_path: Path, assert_file_contents: _AssertFileContents) -> None:
    filepath = join_toml_configs(_PYPROJECT1, "", execution_path, _MYPY_PLUGINS_CONFIG)

    assert_file_contents(
        filepath,
        """
        [tool.mypy]
        pretty = true
        show_column_numbers = true
        warn_unused_ignores = true
        show_error_codes = true
        """,
    )


@pytest.mark.parametrize(
    "additional_config",
    [
        _ADDITIONAL_CONFIG,
        _ADDITIONAL_CONFIG_NO_TABLE,
    ],
)
def test_join_existing_config2(
    execution_path: Path, assert_file_contents: _AssertFileContents, additional_config: str
) -> None:
    filepath = join_toml_configs(_PYPROJECT1, additional_config, execution_path, _MYPY_PLUGINS_CONFIG)

    assert_file_contents(
        filepath,
        """
        [tool.mypy]
        pretty = true
        show_column_numbers = true
        warn_unused_ignores = true
        show_error_codes = false
        show_traceback = true
        """,
    )


@pytest.mark.parametrize(
    "additional_config",
    [
        _ADDITIONAL_CONFIG,
        _ADDITIONAL_CONFIG_NO_TABLE,
    ],
)
def test_join_missing_config(
    execution_path: Path, assert_file_contents: _AssertFileContents, additional_config: str
) -> None:
    filepath = join_toml_configs(_PYPROJECT2, additional_config, execution_path)

    assert_file_contents(
        filepath,
        """
        [tool.mypy]
        pretty = true
        show_error_codes = false
        show_traceback = true
        """,
    )


def test_join_missing_config1(execution_path: Path, assert_file_contents: _AssertFileContents) -> None:
    filepath = join_toml_configs(_PYPROJECT1, "", execution_path)

    assert_file_contents(
        filepath,
        """
        [tool.mypy]
        warn_unused_ignores = true
        pretty = true
        show_error_codes = true
        """,
    )


def test_join_missing_config2(execution_path: Path, assert_file_contents: _AssertFileContents) -> None:
    filepath = join_toml_configs(_PYPROJECT2, "", execution_path)

    assert_file_contents(
        filepath,
        "[tool.mypy]",
    )


def test_join_missing_config3(execution_path: Path, assert_file_contents: _AssertFileContents) -> None:
    filepath = join_toml_configs(_PYPROJECT2, "", execution_path, _MYPY_PLUGINS_CONFIG)

    assert_file_contents(
        filepath,
        """
        [tool.mypy]
        pretty = false
        show_column_numbers = true
        warn_unused_ignores = false
        """,
    )


@pytest.mark.parametrize(
    "additional_config",
    [
        _ADDITIONAL_CONFIG,
        _ADDITIONAL_CONFIG_NO_TABLE,
    ],
)
def test_join_missing_config4(
    execution_path: Path, assert_file_contents: _AssertFileContents, additional_config: str
) -> None:
    filepath = join_toml_configs(_PYPROJECT2, additional_config, execution_path, _MYPY_PLUGINS_CONFIG)

    assert_file_contents(
        filepath,
        """
        [tool.mypy]
        pretty = true
        show_column_numbers = true
        warn_unused_ignores = false
        show_error_codes = false
        show_traceback = true
        """,
    )
