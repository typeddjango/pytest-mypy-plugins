import os
import platform
import sys
import tempfile
from typing import TYPE_CHECKING, Any, Dict, Iterator, List, Mapping, Optional

import pystache
import pytest
import yaml
from _pytest.config.argparsing import Parser
from _pytest.nodes import Node
from py._path.local import LocalPath

from pytest_mypy_plugins import utils

if TYPE_CHECKING:
    from pytest_mypy_plugins.item import YamlTestItem


class File:
    def __init__(self, path: str, content: str) -> None:
        self.path = path
        self.content = content


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
    known_params = None
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


class SafeLineLoader(yaml.SafeLoader):
    def construct_mapping(self, node: yaml.Node, deep: bool = False) -> None:
        mapping = super().construct_mapping(node, deep=deep)
        # Add 1 so line numbering starts at 1
        starting_line = node.start_mark.line + 1
        for (title_node, contents_node) in node.value:
            if title_node.value == "main":
                starting_line = title_node.start_mark.line + 1
        mapping["__line__"] = starting_line
        return mapping


class YamlTestFile(pytest.File):
    def collect(self) -> Iterator["YamlTestItem"]:
        from pytest_mypy_plugins.item import YamlTestItem

        parsed_file = yaml.load(stream=self.fspath.read_text("utf8"), Loader=SafeLineLoader)
        if parsed_file is None:
            return

        if not isinstance(parsed_file, list):
            raise ValueError(f"Test file has to be YAML list, got {type(parsed_file)!r}.")

        for raw_test in parsed_file:
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
                main_file = File(path="main.py", content=pystache.render(raw_test["main"], params))
                test_files = [main_file] + parse_test_files(raw_test.get("files", []))

                output_from_comments = []
                for test_file in test_files:
                    output_lines = utils.extract_errors_from_comments(test_file.path, test_file.content.split("\n"))
                    output_from_comments.extend(output_lines)

                starting_lineno = raw_test["__line__"]
                extra_environment_variables = parse_environment_variables(raw_test.get("env", []))
                disable_cache = raw_test.get("disable_cache", False)
                expected_output_lines = pystache.render(raw_test.get("out", ""), params).split("\n")
                additional_mypy_config = raw_test.get("mypy_config", "")

                skip = self._eval_skip(str(raw_test.get("skip", "False")))
                if not skip:
                    yield YamlTestItem.from_parent(
                        self,
                        name=test_name,
                        files=test_files,
                        starting_lineno=starting_lineno,
                        environment_variables=extra_environment_variables,
                        disable_cache=disable_cache,
                        expected_output_lines=output_from_comments + expected_output_lines,
                        parsed_test_data=raw_test,
                        mypy_config=additional_mypy_config,
                    )

    def _eval_skip(self, skip_if: str) -> bool:
        return eval(skip_if, {"sys": sys, "os": os, "pytest": pytest, "platform": platform})


def pytest_collect_file(path: LocalPath, parent: Node) -> Optional[YamlTestFile]:
    if path.ext in {".yaml", ".yml"} and path.basename.startswith(("test-", "test_")):
        return YamlTestFile.from_parent(parent, fspath=path)
    return None


def pytest_addoption(parser: Parser) -> None:
    group = parser.getgroup("mypy-tests")
    group.addoption(
        "--mypy-testing-base", type=str, default=tempfile.gettempdir(), help="Base directory for tests to use"
    )
    group.addoption("--mypy-ini-file", type=str, help="Which .ini file to use as a default config for tests")
    group.addoption(
        "--mypy-same-process",
        action="store_true",
        help="Run in the same process. Useful for debugging, will create problems with import cache",
    )
    group.addoption(
        "--mypy-extension-hook",
        type=str,
        help="Fully qualifield path to the extension hook function, in case you need custom yaml keys. "
        "Has to be top-level.",
    )
