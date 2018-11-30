import pytest
from _pytest.config.argparsing import Parser

from pytest_mypy.item import TestItem
from pytest_mypy.parser import split_test_chunks, parse_test_chunk


class DotTestFile(pytest.File):
    def collect(self):
        file_contents = self.fspath.read_text('utf8')
        for raw_chunk in split_test_chunks(file_contents):
            chunk = parse_test_chunk(raw_chunk)
            yield TestItem(name=chunk.name,
                           collector=self,
                           config=self.config,
                           source_code=chunk.source_code,
                           starting_lineno=chunk.starting_lineno,
                           output_lines=chunk.output_lines,
                           files=chunk.files_to_create,
                           custom_environment=chunk.custom_environment)


def pytest_collect_file(path, parent):
    if path.ext == '.test':
        return DotTestFile(path, parent=parent, config=parent.config)


def pytest_addoption(parser: Parser) -> None:
    group = parser.getgroup('mypy-tests')
    group.addoption('--mypy-testing-base', type=str, default='/tmp',
                    help='Base directory for tests to use')
    group.addoption('--mypy-ini-file', type=str,
                    help='Which .ini file to use as a default config for tests')

