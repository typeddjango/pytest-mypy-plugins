from configparser import ConfigParser
from pathlib import Path
from textwrap import dedent
from typing import Any, Dict, Final, Optional

import tomlkit

_TOML_TABLE_NAME: Final = "[tool.mypy]"


def load_mypy_plugins_config(config_pyproject_toml_path: str) -> Optional[Dict[str, Any]]:
    with open(config_pyproject_toml_path) as f:
        toml_config = tomlkit.parse(f.read())
    return toml_config.get("tool", {}).get("pytest-mypy-plugins", {}).get("mypy-config")


def join_ini_configs(
    base_ini_fpath: Optional[str],
    additional_mypy_config: str,
    execution_path: Path,
    mypy_plugins_config: Optional[Dict[str, Any]] = None,
) -> Optional[str]:
    mypy_ini_config = ConfigParser()
    if mypy_plugins_config:
        mypy_ini_config.read_dict({"mypy": mypy_plugins_config})
    if base_ini_fpath:
        mypy_ini_config.read(base_ini_fpath)
    if additional_mypy_config:
        if "[mypy]" not in additional_mypy_config:
            additional_mypy_config = f"[mypy]\n{additional_mypy_config}"
        mypy_ini_config.read_string(additional_mypy_config)

    if mypy_ini_config.sections():
        mypy_config_file_path = execution_path / "mypy.ini"
        with mypy_config_file_path.open("w") as f:
            mypy_ini_config.write(f)
        return str(mypy_config_file_path)
    return None


def join_toml_configs(
    base_pyproject_toml_fpath: str,
    additional_mypy_config: str,
    execution_path: Path,
    mypy_plugins_config: Optional[Dict[str, Any]] = None,
) -> Optional[str]:
    # Empty document with `[tool.mypy]` empty table, useful for overrides further.
    toml_document = tomlkit.document()
    tool = tomlkit.table(is_super_table=True)
    tool.append("mypy", tomlkit.table())
    toml_document.append("tool", tool)

    if mypy_plugins_config:
        toml_document["tool"]["mypy"].update(mypy_plugins_config.items())  # type: ignore[index, union-attr]

    if base_pyproject_toml_fpath:
        with open(base_pyproject_toml_fpath) as f:
            toml_config = tomlkit.parse(f.read())
        # We don't want the whole config file, because it can contain
        # other sections like `[tool.isort]`, we only need `[tool.mypy]` part.
        if "tool" in toml_config and "mypy" in toml_config["tool"]:  # type: ignore[operator]
            toml_document["tool"]["mypy"].update(toml_config["tool"]["mypy"].value.items())  # type: ignore[index, union-attr]

    if additional_mypy_config:
        if _TOML_TABLE_NAME not in additional_mypy_config:
            additional_mypy_config = f"{_TOML_TABLE_NAME}\n{dedent(additional_mypy_config)}"

        additional_data = tomlkit.parse(additional_mypy_config)
        toml_document["tool"]["mypy"].update(  # type: ignore[index, union-attr]
            additional_data["tool"]["mypy"].value.items(),  # type: ignore[index]
        )

    mypy_config_file_path = execution_path / "pyproject.toml"
    with mypy_config_file_path.open("w") as f:
        f.write(toml_document.as_string())
    return str(mypy_config_file_path)
