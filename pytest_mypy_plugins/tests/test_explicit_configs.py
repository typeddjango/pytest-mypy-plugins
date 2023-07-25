import subprocess
from pathlib import Path
from typing import Final

import pytest

_PYPROJECT1: Final = str(Path(__file__).parent / "test_configs" / "pyproject1.toml")
_PYPROJECT2: Final = str(Path(__file__).parent / "test_configs" / "pyproject2.toml")
_MYPYINI1: Final = str(Path(__file__).parent / "test_configs" / "mypy1.ini")
_MYPYINI2: Final = str(Path(__file__).parent / "test_configs" / "mypy2.ini")
_SETUPCFG1: Final = str(Path(__file__).parent / "test_configs" / "setup1.cfg")
_SETUPCFG2: Final = str(Path(__file__).parent / "test_configs" / "setup2.cfg")

_TEST_FILE: Final = str(Path(__file__).parent / "test-mypy-config.yml")


@pytest.mark.parametrize("config_file", [_PYPROJECT1, _PYPROJECT2])
def test_pyproject_toml(config_file: str) -> None:
    subprocess.check_output(
        [
            "pytest",
            "--mypy-pyproject-toml-file",
            config_file,
            _TEST_FILE,
        ]
    )


@pytest.mark.parametrize(
    "config_file",
    [
        _MYPYINI1,
        _MYPYINI2,
        _SETUPCFG1,
        _SETUPCFG2,
    ],
)
def test_ini_files(config_file: str) -> None:
    subprocess.check_output(
        [
            "pytest",
            "--mypy-ini-file",
            config_file,
            _TEST_FILE,
        ]
    )
