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


@pytest.mark.parametrize(
    "params",
    [
        [{"a": 2}, {"a": 3, "b": 4}],
        [{"a": 2, "b": 0}, {"a": 3, "b": 4, "c": 5}],
    ],
)
def test_parametrized_with_wrong_keys(params: list[Mapping[str, Any]]) -> None:
    with pytest.raises(
        ValueError, match="All parametrized entries must have same keys."
    ):
        parse_parametrized(params)
