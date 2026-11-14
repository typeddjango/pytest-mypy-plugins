from typing import Any, Mapping

import pytest

from pytest_mypy_plugins.logic.parser import parse_parametrized


@pytest.mark.parametrize(
    "params",
    [
        [{"a": "2"}, {"a": "2"}],
        [{"key": False, "data": (1, 2, 3)}, {"key": False, "data": (1, 2, 3)}],
        [{"a": "2", "b": {"c": 1}}, {"b": {"c": 1}, "a": "2"}],
    ],
)
def test_parametrized_duplicates(params: list[Mapping[str, Any]]) -> None:
    """Checks that `parse_parametrized` raises `ValueError` with duplicates."""
    with pytest.raises(ValueError, match="Params in test must be unique."):
        parse_parametrized(params)


def test_parametrized_unique() -> None:
    """Checks that unique params with multiple keys are not rejected."""
    params: list[Mapping[str, Any]] = [{"a": 1, "b": 2}, {"a": 3, "b": 4}]

    assert parse_parametrized(params) == params
