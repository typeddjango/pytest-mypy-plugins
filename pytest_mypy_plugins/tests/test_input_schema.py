import pathlib
from typing import Sequence

import jsonschema
import pytest
import yaml

from pytest_mypy_plugins.collect import validate_schema


def get_all_yaml_files(dir_path: pathlib.Path) -> Sequence[pathlib.Path]:
    yaml_files = []
    for file in dir_path.rglob("*"):
        if file.suffix in (".yml", ".yaml"):
            yaml_files.append(file)

    return yaml_files


files = get_all_yaml_files(pathlib.Path(__file__).parent)


@pytest.mark.parametrize("yaml_file", files, ids=lambda x: x.stem)
def test_yaml_files(yaml_file: pathlib.Path) -> None:
    validate_schema(yaml.safe_load(yaml_file.read_text()))


def test_mypy_config_is_not_an_object() -> None:
    with pytest.raises(jsonschema.exceptions.ValidationError) as ex:
        validate_schema(
            [
                {
                    "case": "mypy_config_is_not_an_object",
                    "main": "False",
                    "mypy_config": [{"force_uppercase_builtins": True}, {"force_union_syntax": True}],
                }
            ]
        )

    assert (
        ex.value.message == "[{'force_uppercase_builtins': True}, {'force_union_syntax': True}] is not of type 'string'"
    )


def test_closed_schema() -> None:
    with pytest.raises(jsonschema.exceptions.ValidationError) as ex:
        validate_schema(
            [
                {
                    "case": "mypy_config_is_not_an_object",
                    "main": "False",
                    "extra_field": 1,
                }
            ],
            is_closed=True,
        )

    assert ex.value.message == "Additional properties are not allowed ('extra_field' was unexpected)"
