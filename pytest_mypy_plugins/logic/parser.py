from collections.abc import Mapping
from typing import Any

from pytest_mypy_plugins.types import File


def parse_parametrized(
    params: list[Mapping[str, Any]],
) -> list[Mapping[str, Any]]:
    if not params:
        return [{}]

    unique_reprs = {
        repr(sorted(param.items(), key=lambda item: item[0]))
        for param in params
    }
    if len(unique_reprs) != len(params):
        raise ValueError("Params in test must be unique.")

    parsed_params: list[Mapping[str, Any]] = []
    expected_keys: set[str] = set(sorted(params[0].keys()))
    for idx, param in enumerate(params):
        param_keys = set(sorted(param.keys()))
        if expected_keys.intersection(param_keys) != expected_keys:
            raise ValueError(
                "All parametrized entries must have same keys."
                f'First entry is {", ".join(expected_keys)} but {", ".join(param_keys)} '
                f"was spotted at {idx} position",
            )
        parsed_params.append(
            {k: v for k, v in param.items() if not k.startswith("__")}
        )

    return parsed_params


def parse_test_files(test_files: list[dict[str, Any]]) -> list[File]:
    files: list[File] = []
    for test_file in test_files:
        path = test_file.get("path", "main.py")
        file = File(path=path, content=test_file.get("content", ""))
        files.append(file)
    return files
