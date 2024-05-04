import dataclasses
import json
import os
import pathlib
import platform
import sys
from dataclasses import dataclass
from typing import Any, Callable, Dict, Iterator, List, Mapping, Optional, Set

import jsonschema
import pytest

from . import utils


@dataclass
class File:
    path: str
    content: str


def validate_schema(data: List[Mapping[str, Any]], *, is_closed: bool = False) -> None:
    """Validate the schema of the file-under-test."""
    schema = json.loads((pathlib.Path(__file__).parent / "schema.json").read_text("utf8"))
    schema["items"]["properties"]["__line__"] = {
        "type": "integer",
        "description": "Line number where the test starts (`pytest-mypy-plugins` internal)",
    }
    schema["items"]["additionalProperties"] = not is_closed

    jsonschema.validate(instance=data, schema=schema)


def parse_test_files(test_files: List[Dict[str, Any]]) -> List[File]:
    files: List[File] = []
    for test_file in test_files:
        path = test_file.get("path", "main.py")
        file = File(path=path, content=test_file.get("content", ""))
        files.append(file)
    return files


def parse_environment_variables(env_vars: List[str]) -> Dict[str, str]:
    parsed_vars: Dict[str, str] = {}
    for env_var in env_vars:
        name, _, value = env_var.partition("=")
        parsed_vars[name] = value
    return parsed_vars


def parse_parametrized(params: List[Mapping[str, Any]]) -> List[Mapping[str, Any]]:
    if not params:
        return [{}]

    parsed_params: List[Mapping[str, Any]] = []
    known_params: Optional[Set[str]] = None
    for idx, param in enumerate(params):
        param_keys = set(sorted(param.keys()))
        if not known_params:
            known_params = param_keys
        elif known_params.intersection(param_keys) != known_params:
            raise ValueError(
                "All parametrized entries must have same keys."
                f'First entry is {", ".join(known_params)} but {", ".join(param_keys)} '
                "was spotted at {idx} position",
            )
        parsed_params.append({k: v for k, v in param.items() if not k.startswith("__")})

    return parsed_params


@dataclasses.dataclass
class ItemDefinition:
    """
    A dataclass representing a single test in the yaml file
    """

    make_pytest_item: Callable[[pytest.Collector], pytest.Item]

    @classmethod
    def from_yaml(cls, data: List[Mapping[str, Any]], *, is_closed: bool = False) -> Iterator["ItemDefinition"]:
        from pytest_mypy_plugins.item import YamlTestItem

        validate_schema(data, is_closed=is_closed)

        for raw_test in data:
            test_name_prefix = raw_test["case"]
            if " " in test_name_prefix:
                raise ValueError(f"Invalid test name {test_name_prefix!r}, only '[a-zA-Z0-9_]' is allowed.")
            else:
                parametrized = parse_parametrized(raw_test.get("parametrized", []))

            for params in parametrized:
                if params:
                    test_name_suffix = ",".join(f"{k}={v}" for k, v in params.items())
                    test_name_suffix = f"[{test_name_suffix}]"
                else:
                    test_name_suffix = ""

                test_name = f"{test_name_prefix}{test_name_suffix}"
                main_content = utils.render_template(template=raw_test["main"], data=params)
                main_file = File(path="main.py", content=main_content)
                test_files = [main_file] + parse_test_files(raw_test.get("files", []))
                expect_fail = raw_test.get("expect_fail", False)
                regex = raw_test.get("regex", False)

                expected_output = []
                for test_file in test_files:
                    output_lines = utils.extract_output_matchers_from_comments(
                        test_file.path, test_file.content.split("\n"), regex=regex
                    )
                    expected_output.extend(output_lines)

                starting_lineno = raw_test["__line__"]
                extra_environment_variables = parse_environment_variables(raw_test.get("env", []))
                disable_cache = raw_test.get("disable_cache", False)
                expected_output.extend(
                    utils.extract_output_matchers_from_out(raw_test.get("out", ""), params, regex=regex)
                )
                additional_mypy_config = utils.render_template(template=raw_test.get("mypy_config", ""), data=params)

                skip = cls._eval_skip(str(raw_test.get("skip", "False")))
                if not skip:
                    yield cls(
                        make_pytest_item=lambda parent: YamlTestItem.from_parent(
                            parent,
                            name=test_name,
                            files=test_files,
                            starting_lineno=starting_lineno,
                            environment_variables=extra_environment_variables,
                            disable_cache=disable_cache,
                            expected_output=expected_output,
                            parsed_test_data=raw_test,
                            mypy_config=additional_mypy_config,
                            expect_fail=expect_fail,
                        )
                    )

    @classmethod
    def _eval_skip(cls, skip_if: str) -> bool:
        return eval(skip_if, {"sys": sys, "os": os, "pytest": pytest, "platform": platform})

    def pytest_item(self, parent: pytest.Collector) -> pytest.Item:
        return self.make_pytest_item(parent)
