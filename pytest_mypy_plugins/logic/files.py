import os
from pathlib import Path

from pytest_mypy_plugins.constants import COLON


def replace_fpath_with_module_name(line: str, rootdir: Path) -> str:
    if COLON not in line:
        return line
    out_fpath, res_line = line.split(COLON, 1)
    line = os.path.relpath(out_fpath, start=rootdir) + COLON + res_line
    return line.strip().replace(".py:", COLON)


def maybe_to_abspath(rel_or_abs: str, rootdir: Path | None) -> str:
    rel_or_abs = os.path.expandvars(rel_or_abs)
    if rootdir is None or os.path.isabs(rel_or_abs):
        return rel_or_abs
    return str(rootdir / rel_or_abs)


def parse_environment_variables(env_vars: list[str]) -> dict[str, str]:
    parsed_vars: dict[str, str] = {}
    for env_var in env_vars:
        name, _, value = env_var.partition("=")
        parsed_vars[name] = value
    return parsed_vars


def fname_to_module(fpath: Path, root_path: Path) -> str | None:
    try:
        relpath = fpath.relative_to(root_path).with_suffix("")
        return str(relpath).replace(os.sep, ".")
    except ValueError:
        return None
