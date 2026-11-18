import os
import re
from collections.abc import MutableMapping
from configparser import ConfigParser
from pathlib import Path
from textwrap import dedent
from typing import Any, Final

import tomlkit

_TOML_TABLE_NAME: Final = "[tool.mypy]"
_MYPY_TOML_SECTION: Final = "mypy"
_TOOL_TOML_SECTION: Final = "tool"
_MYPY_CONFIG_FILE_DIR_RE: Final = re.compile(
    r"\$(?:MYPY_CONFIG_FILE_DIR(?![A-Za-z0-9_])|\{MYPY_CONFIG_FILE_DIR\})"
)


def _expand_config_dir_str(value: str, config_dir: str) -> str:
    if not _MYPY_CONFIG_FILE_DIR_RE.search(value):
        return value
    return _MYPY_CONFIG_FILE_DIR_RE.sub(lambda _: config_dir, value)


def _mypy_path_config_dir(config_dir: str, execution_path: Path) -> str:
    if ":" not in config_dir:
        return config_dir
    try:
        rel = os.path.relpath(config_dir, os.path.abspath(execution_path))
    except ValueError:
        return config_dir
    rel_posix = Path(rel).as_posix()
    if rel_posix == ".":
        return "$MYPY_CONFIG_FILE_DIR"
    return f"$MYPY_CONFIG_FILE_DIR/{rel_posix}"


def _expand_ini_config_dir(
    mypy_ini_config: ConfigParser,
    config_dir: str,
    execution_path: Path,
) -> None:
    mypy_path_dir = _mypy_path_config_dir(config_dir, execution_path)
    for section in mypy_ini_config.sections():
        if section != "mypy" and not section.startswith("mypy-"):
            continue
        for option, value in mypy_ini_config.items(section):
            target_dir = mypy_path_dir if option == "mypy_path" else config_dir
            expanded = _expand_config_dir_str(value, target_dir)
            if expanded != value:
                mypy_ini_config.set(section, option, expanded)


def _expand_toml_mapping(
    mapping: MutableMapping[str, Any],
    config_dir: str,
    mypy_path_dir: str,
) -> None:
    for key, value in list(mapping.items()):
        if isinstance(value, str):
            if (
                key == "mypy_path"
                and ":" in mypy_path_dir
                and _MYPY_CONFIG_FILE_DIR_RE.search(value)
            ):
                mapping[key] = [
                    _expand_config_dir_str(part.strip(), config_dir)
                    for part in re.split("[,:]", value)
                    if part.strip()
                ]
                continue
            target_dir = mypy_path_dir if key == "mypy_path" else config_dir
            expanded = _expand_config_dir_str(value, target_dir)
            if expanded != value:
                mapping[key] = expanded
        elif isinstance(value, MutableMapping):
            _expand_toml_mapping(value, config_dir, mypy_path_dir)
        elif isinstance(value, list):
            _expand_toml_list(value, config_dir, mypy_path_dir)


def _expand_toml_list(
    items: list[Any],
    config_dir: str,
    mypy_path_dir: str,
) -> None:
    for idx, item in enumerate(items):
        if isinstance(item, str):
            expanded = _expand_config_dir_str(item, config_dir)
            if expanded != item:
                items[idx] = expanded
        elif isinstance(item, MutableMapping):
            _expand_toml_mapping(item, config_dir, mypy_path_dir)
        elif isinstance(item, list):
            _expand_toml_list(item, config_dir, mypy_path_dir)


def join_ini_configs(
    base_ini_fpath: str | None,
    additional_mypy_config: str,
    execution_path: Path,
) -> str | None:
    mypy_ini_config = ConfigParser(interpolation=None)
    if base_ini_fpath:
        mypy_ini_config.read(base_ini_fpath)
        _expand_ini_config_dir(
            mypy_ini_config,
            os.path.dirname(os.path.abspath(base_ini_fpath)),
            execution_path,
        )
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
    elif base_pyproject_toml_fpath:
        config_dir = os.path.dirname(os.path.abspath(base_pyproject_toml_fpath))
        tool_mypy_section = toml_config[_TOOL_TOML_SECTION][_MYPY_TOML_SECTION]
        if isinstance(tool_mypy_section, MutableMapping):
            _expand_toml_mapping(
                tool_mypy_section,
                config_dir,
                _mypy_path_config_dir(config_dir, execution_path),
            )

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
