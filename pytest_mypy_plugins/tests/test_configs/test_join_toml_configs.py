import os
from collections.abc import Callable
from pathlib import Path
from textwrap import dedent
from typing import Final, Optional

import pytest
import tomlkit

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

_PYPROJECT1: Final = str(Path(__file__).parent / "pyproject1.toml")
_PYPROJECT2: Final = str(Path(__file__).parent / "pyproject2.toml")
_PYPROJECT3: Final = str(Path(__file__).parent / "pyproject3.toml")


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
    execution_path: Path,
    assert_file_contents: _AssertFileContents,
    additional_config: str,
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


@pytest.mark.parametrize(
    "additional_config",
    [
        _ADDITIONAL_CONFIG,
        _ADDITIONAL_CONFIG_NO_TABLE,
    ],
)
def test_join_missing_config(
    execution_path: Path,
    assert_file_contents: _AssertFileContents,
    additional_config: str,
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


def test_join_missing_config1(
    execution_path: Path, assert_file_contents: _AssertFileContents
) -> None:
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


def test_join_missing_config2(
    execution_path: Path, assert_file_contents: _AssertFileContents
) -> None:
    filepath = join_toml_configs(_PYPROJECT2, "", execution_path)

    assert_file_contents(
        filepath,
        "[tool.mypy]",
    )


def test_join_missing_config3(
    execution_path: Path, assert_file_contents: _AssertFileContents
) -> None:
    filepath = join_toml_configs(_PYPROJECT3, "", execution_path)

    assert_file_contents(
        filepath,
        """
        [tool.mypy]
        warn_unused_ignores = true
        pretty = true
        show_error_codes = true

        [[tool.mypy.overrides]]
        # This section should be copied
        module = "mymodule"
        ignore_missing_imports = true
        """,
    )


def test_join_toml_expands_mypy_config_file_dir(tmp_path: Path) -> None:
    config_dir = tmp_path / "project"
    execution_path = tmp_path / "exec"
    config_dir.mkdir()
    execution_path.mkdir()

    pyproject = config_dir / "pyproject.toml"
    pyproject.write_text(
        "[tool.mypy]\n"
        'mypy_path = ["$MYPY_CONFIG_FILE_DIR/stubs_a", "${MYPY_CONFIG_FILE_DIR}/stubs_b"]\n'
        'custom_typeshed_dir = "$MYPY_CONFIG_FILE_DIR/typeshed"\n'
        'cache_dir = "${MYPY_CONFIG_FILE_DIR}/.mypy_cache"\n'
        'junit_xml = "$MYPY_CONFIG_FILE_DIR_EXTRA/report.xml"\n\n'
        "[[tool.mypy.overrides]]\n"
        'module = "pkg.*"\n'
        'custom_typing_module = "$MYPY_CONFIG_FILE_DIR/typing_mod"\n',
        encoding="utf-8",
    )

    joined = join_toml_configs(
        str(pyproject),
        'python_executable = "$MYPY_CONFIG_FILE_DIR/bin/python"\n',
        execution_path,
    )
    assert joined is not None

    with open(joined, encoding="utf-8") as f:
        parsed = tomlkit.parse(f.read())

    expected_dir = os.path.dirname(os.path.abspath(pyproject))
    mypy_cfg = parsed.unwrap()["tool"]["mypy"]
    assert mypy_cfg["mypy_path"] == [
        f"{expected_dir}/stubs_a",
        f"{expected_dir}/stubs_b",
    ]
    assert mypy_cfg["custom_typeshed_dir"] == f"{expected_dir}/typeshed"
    assert mypy_cfg["cache_dir"] == f"{expected_dir}/.mypy_cache"
    assert mypy_cfg["junit_xml"] == "$MYPY_CONFIG_FILE_DIR_EXTRA/report.xml"
    assert mypy_cfg["python_executable"] == "$MYPY_CONFIG_FILE_DIR/bin/python"
    assert (
        mypy_cfg["overrides"][0]["custom_typing_module"]
        == f"{expected_dir}/typing_mod"
    )


def test_join_toml_expands_string_mypy_path(tmp_path: Path) -> None:
    config_dir = tmp_path / "project"
    execution_path = tmp_path / "exec"
    config_dir.mkdir()
    execution_path.mkdir()

    pyproject = config_dir / "pyproject.toml"
    pyproject.write_text(
        "[tool.mypy]\n"
        'mypy_path = "$MYPY_CONFIG_FILE_DIR/stubs_a:${MYPY_CONFIG_FILE_DIR}/stubs_b"\n',
        encoding="utf-8",
    )

    joined = join_toml_configs(str(pyproject), "", execution_path)
    assert joined is not None

    with open(joined, encoding="utf-8") as f:
        parsed = tomlkit.parse(f.read()).unwrap()

    expected_dir = os.path.dirname(os.path.abspath(pyproject))
    if ":" in expected_dir:
        rel = Path(
            os.path.relpath(expected_dir, os.path.abspath(execution_path))
        ).as_posix()
        expected_prefix = f"$MYPY_CONFIG_FILE_DIR/{rel}"
    else:
        expected_prefix = expected_dir
    assert (
        parsed["tool"]["mypy"]["mypy_path"]
        == f"{expected_prefix}/stubs_a:{expected_prefix}/stubs_b"
    )
