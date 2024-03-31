from configparser import ConfigParser
from pathlib import Path
from textwrap import dedent
from typing import Final, Optional

import tomlkit

_TOML_TABLE_NAME: Final = "[tool.mypy]"


def join_ini_configs(base_ini_fpath: Optional[str], additional_mypy_config: str, execution_path: Path) -> Optional[str]:
    mypy_ini_config = ConfigParser()
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
    base_pyproject_toml_fpath: str, additional_mypy_config: str, execution_path: Path
) -> Optional[str]:
    if base_pyproject_toml_fpath:
        with open(base_pyproject_toml_fpath) as f:
            toml_config = tomlkit.parse(f.read())
    else:
        # Emtpy document with `[tool.mypy` empty table,
        # useful for overrides further.
        toml_config = tomlkit.document()

    if "tool" not in toml_config or "mypy" not in toml_config["tool"]:  # type: ignore[operator]
        tool = tomlkit.table(is_super_table=True)
        tool.append("mypy", tomlkit.table())
        toml_config.append("tool", tool)

    if additional_mypy_config:
        if _TOML_TABLE_NAME not in additional_mypy_config:
            additional_mypy_config = f"{_TOML_TABLE_NAME}\n{dedent(additional_mypy_config)}"

        additional_data = tomlkit.parse(additional_mypy_config)
        toml_config["tool"]["mypy"].update(  # type: ignore[index, union-attr]
            additional_data["tool"]["mypy"].value.items(),  # type: ignore[index]
        )

    mypy_config_file_path = execution_path / "pyproject.toml"
    with mypy_config_file_path.open("w") as f:
        # We don't want the whole config file, because it can contain
        # other sections like `[tool.isort]`, we only need `[tool.mypy]` part.
        tool_mypy = toml_config["tool"]["mypy"]  # type: ignore[index]

        # construct toml output
        min_toml = tomlkit.document()
        min_tool = tomlkit.table(is_super_table=True)
        min_toml.append("tool", min_tool)
        min_tool.append("mypy", tool_mypy)

        f.write(min_toml.as_string())
    return str(mypy_config_file_path)
