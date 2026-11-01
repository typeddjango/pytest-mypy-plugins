from collections.abc import Mapping
from typing import Any

from pytest_mypy_plugins.types import File


def parse_parametrized(
    parameters_case: list[Mapping[str, Any]],
) -> list[Mapping[str, Any]]:
    if not parameters_case:
        return [{}]

    expected_keys: set[str] = set(sorted(parameters_case[0].keys()))
    return [
        _parse_param_case(param_case, idx, expected_keys)
        for idx, param_case in enumerate(parameters_case)
    ]


def _parse_param_case(
    param_case: Mapping[str, Any], idx: int, expected_keys: set[str]
) -> Mapping[str, Any]:
    param_keys = set(sorted(param_case.keys()))
    if expected_keys.intersection(param_keys) != expected_keys:
        raise ValueError(
            "All parametrized entries must have same keys."  # noqa: WPS237
            f'First entry is {", ".join(expected_keys)} but {", ".join(param_keys)} '
            f"was spotted at {idx} position",
        )
    return {
        param_key: param_value
        for param_key, param_value in param_case.items()
        if not param_key.startswith("__")
    }


def parse_test_files(file_specs: list[dict[str, Any]]) -> list[File]:
    """Convert raw YAML file entries into ``File`` objects."""
    return [
        File(
            path=file_info.get("path", "main.py"),
            content=file_info.get("content", ""),
        )
        for file_info in file_specs
    ]
