import os
from pathlib import Path
from typing import Final

from pytest_mypy_plugins.constants import COLON
from pytest_mypy_plugins.types import File

_MAX_LINE_SPLIT_PARTS: Final = 3


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
        name, _, value_env = env_var.partition("=")
        parsed_vars[name] = value_env
    return parsed_vars


def fname_to_module(fpath: Path, root_path: Path) -> str | None:
    try:
        relpath = fpath.relative_to(root_path).with_suffix("")
        return str(relpath).replace(os.sep, ".")
    except ValueError:
        return None


def make_test_file(test_file: File) -> None:
    current_directory = Path.cwd()
    fpath = current_directory / test_file.path
    fpath.parent.mkdir(parents=True, exist_ok=True)
    fpath.write_text(test_file.content)


def sorted_by_file_and_line(lines: list[str]) -> list[str]:
    def extract_parts_as_tuple(line: str) -> tuple[str, int]:  # noqa: WPS430
        if len(line.split(":", maxsplit=2)) < _MAX_LINE_SPLIT_PARTS:
            return "", 0

        file_name, line_number, _ = line.split(":", maxsplit=2)
        try:
            return file_name, int(line_number)
        except ValueError:
            return "", 0

    return sorted(lines, key=extract_parts_as_tuple)
