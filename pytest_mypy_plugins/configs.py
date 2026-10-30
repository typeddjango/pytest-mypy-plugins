from configparser import ConfigParser
from pathlib import Path
from textwrap import dedent
from typing import Any, Final

import tomli
import tomli_w

_TOML_TABLE_NAME: Final = "[tool.mypy]"
_MYPY_TOML_SECTION: Final = "mypy"
_TOOL_TOML_SECTION: Final = "tool"


def join_ini_configs(
    base_ini_fpath: str | None,
    additional_mypy_config: str,
    execution_path: Path,
) -> str | None:
    mypy_ini_config = ConfigParser()
    if base_ini_fpath:
        mypy_ini_config.read(base_ini_fpath)
    if additional_mypy_config:
        if "[mypy]" not in additional_mypy_config:
            additional_mypy_config = f"[mypy]\n{additional_mypy_config}"
        mypy_ini_config.read_string(additional_mypy_config)

    if mypy_ini_config.sections():
        mypy_config_file_path = execution_path / "mypy.ini"
        with mypy_config_file_path.open("w") as mypy_file_config:
            mypy_ini_config.write(mypy_file_config)
        return str(mypy_config_file_path)
    return None


def join_toml_configs(
    base_pyproject_toml_fpath: str,
    additional_mypy_config: str,
    execution_path: Path,
) -> str | None:
    if base_pyproject_toml_fpath:
        with open(base_pyproject_toml_fpath) as file_config:
            toml_config = tomli.loads(file_config.read())
    else:
        # Empty document with `[tool.mypy]` empty table,
        # useful for overrides further.
        toml_config = {}

    if (
        _TOOL_TOML_SECTION not in toml_config
        or _MYPY_TOML_SECTION not in toml_config[_TOOL_TOML_SECTION]
    ):
        tool: dict[str, Any] = {}
        tool[_MYPY_TOML_SECTION] = {}
        toml_config[_TOOL_TOML_SECTION] = tool

    if additional_mypy_config:
        if _TOML_TABLE_NAME not in additional_mypy_config:
            additional_mypy_config = (
                f"{_TOML_TABLE_NAME}\n{dedent(additional_mypy_config)}"
            )

        additional_data = tomli.loads(additional_mypy_config)
        toml_config[_TOOL_TOML_SECTION][_MYPY_TOML_SECTION].update(
            additional_data[_TOOL_TOML_SECTION][_MYPY_TOML_SECTION].items(),
        )

    mypy_config_file_path = execution_path / "pyproject.toml"
    with mypy_config_file_path.open("w") as file_config:
        # We don't want the whole config file, because it can contain
        # other sections like `[tool.isort]`, we only need `[tool.mypy]` part.
        tool_mypy = toml_config[_TOOL_TOML_SECTION][_MYPY_TOML_SECTION]

        # construct toml output
        min_toml = {}
        min_tool: dict[str, Any] = {}
        min_toml[_TOOL_TOML_SECTION] = min_tool
        min_tool[_MYPY_TOML_SECTION] = tool_mypy

        file_config.write(tomli_w.dumps(min_toml))
    return str(mypy_config_file_path)
