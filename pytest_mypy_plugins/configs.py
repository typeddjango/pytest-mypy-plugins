from configparser import ConfigParser
from pathlib import Path
from textwrap import dedent
from typing import Final

import tomlkit

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
            toml_config = tomlkit.parse(file_config.read())
    else:
        # Empty document with `[tool.mypy]` empty table,
        # useful for overrides further.
        toml_config = tomlkit.document()

    if (
        _TOOL_TOML_SECTION not in toml_config
        or _MYPY_TOML_SECTION not in toml_config[_TOOL_TOML_SECTION]
    ):
        tool = tomlkit.table(is_super_table=True)
        tool.append(_MYPY_TOML_SECTION, tomlkit.table())
        toml_config.append(_TOOL_TOML_SECTION, tool)

    if additional_mypy_config:
        if _TOML_TABLE_NAME not in additional_mypy_config:
            additional_mypy_config = (
                f"{_TOML_TABLE_NAME}\n{dedent(additional_mypy_config)}"
            )

        additional_data = tomlkit.parse(additional_mypy_config)
        toml_config[_TOOL_TOML_SECTION][_MYPY_TOML_SECTION].update(
            additional_data[_TOOL_TOML_SECTION][
                _MYPY_TOML_SECTION
            ].value.items(),
        )

    mypy_config_file_path = execution_path / "pyproject.toml"
    with mypy_config_file_path.open("w") as file_config:
        # We don't want the whole config file, because it can contain
        # other sections like `[tool.isort]`, we only need `[tool.mypy]` part.
        tool_mypy = toml_config[_TOOL_TOML_SECTION][_MYPY_TOML_SECTION]

        # construct toml output
        min_toml = tomlkit.document()
        min_tool = tomlkit.table(is_super_table=True)
        min_toml.append(_TOOL_TOML_SECTION, min_tool)
        min_tool.append(_MYPY_TOML_SECTION, tool_mypy)

        file_config.write(min_toml.as_string())
    return str(mypy_config_file_path)
