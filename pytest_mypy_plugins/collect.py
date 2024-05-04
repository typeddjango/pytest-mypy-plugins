import pathlib
import tempfile
from typing import Any, Dict, Hashable, Iterator, List, Mapping, Optional

import pytest
import yaml
from _pytest.config.argparsing import Parser
from _pytest.nodes import Node

from .definition import File, ItemDefinition

# For backwards compatibility reasons this reference stays here
File = File


class SafeLineLoader(yaml.SafeLoader):
    def construct_mapping(self, node: yaml.MappingNode, deep: bool = False) -> Dict[Hashable, Any]:
        mapping = super().construct_mapping(node, deep=deep)
        # Add 1 so line numbering starts at 1
        starting_line = node.start_mark.line + 1
        for title_node, _contents_node in node.value:
            if title_node.value == "main":
                starting_line = title_node.start_mark.line + 1
        mapping["__line__"] = starting_line
        return mapping


class YamlTestFile(pytest.File):
    @classmethod
    def read_yaml_file(cls, path: pathlib.Path) -> List[Mapping[str, Any]]:
        parsed_file = yaml.load(stream=path.read_text("utf8"), Loader=SafeLineLoader)
        if parsed_file is None:
            return []

        # Unfortunately, yaml.safe_load() returns Any,
        # so we make our intention explicit here.
        if not isinstance(parsed_file, list):
            raise ValueError(f"Test file has to be YAML list, got {type(parsed_file)!r}.")

        return parsed_file

    def collect(self) -> Iterator[pytest.Item]:
        is_closed = self.config.option.mypy_closed_schema
        parsed_file = self.read_yaml_file(self.path)

        for test in ItemDefinition.from_yaml(parsed_file, is_closed=is_closed):
            yield test.pytest_item(self)


def pytest_collect_file(file_path: pathlib.Path, parent: Node) -> Optional[pytest.Collector]:
    if file_path.suffix in {".yaml", ".yml"} and file_path.name.startswith(("test-", "test_")):
        return YamlTestFile.from_parent(parent, path=file_path)
    return None


def pytest_addoption(parser: Parser) -> None:
    group = parser.getgroup("mypy-tests")
    group.addoption(
        "--mypy-testing-base", type=str, default=tempfile.gettempdir(), help="Base directory for tests to use"
    )
    group.addoption(
        "--mypy-pyproject-toml-file",
        type=str,
        help="Which `pyproject.toml` file to use as a default config for tests. Incompatible with `--mypy-ini-file`",
    )
    group.addoption(
        "--mypy-ini-file",
        type=str,
        help="Which `.ini` file to use as a default config for tests. Incompatible with `--mypy-pyproject-toml-file`",
    )
    group.addoption(
        "--mypy-same-process",
        action="store_true",
        help="Run in the same process. Useful for debugging, will create problems with import cache",
    )
    group.addoption(
        "--mypy-extension-hook",
        type=str,
        help="Fully qualified path to the extension hook function, in case you need custom yaml keys. "
        "Has to be top-level.",
    )
    group.addoption(
        "--mypy-only-local-stub",
        action="store_true",
        help="mypy will ignore errors from site-packages",
    )
    group.addoption(
        "--mypy-closed-schema",
        action="store_true",
        help="Use closed schema to validate YAML test cases, which won't allow any extra keys (does not work well with `--mypy-extension-hook`)",
    )
