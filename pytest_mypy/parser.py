import itertools
import re
import tempfile
from typing import Any, Dict, Iterator, List, Optional

import dataclasses
from _pytest.config import Config

from pytest_mypy.utils import extract_errors_from_comments


@dataclasses.dataclass
class RawTestChunk:
    name: str
    starting_lineno: int
    contents: str


@dataclasses.dataclass
class ParsedTestChunk:
    name: str
    starting_lineno: int
    source_code: str
    output_lines: List[str]
    custom_environment: Dict[str, Any]
    files_to_create: Dict[str, str]
    temp_dir: tempfile.TemporaryDirectory
    custom_mypy_options: List[str]
    disable_cache: bool


TEST_CASES_SEPARATOR = re.compile(r'^\[(?:case|CASE) ([a-zA-Z0-9_]+)\][ \t]*$\n',
                                  flags=re.MULTILINE)
END_CASE_SEPARATOR = re.compile(r'^\[/(?:case|CASE)\][ \t]*$', flags=re.MULTILINE)
ONE_LINE_SECTIONS = ('env', 'disable_cache', 'mypy_options')


def split_test_chunks(testfile_text: str) -> Iterator[RawTestChunk]:
    matches = re.split(TEST_CASES_SEPARATOR, testfile_text)

    current_lineno = matches[0].count('\n') + 1
    for i in range(1, len(matches), 2):
        name, contents = matches[i:i + 2]
        contents = re.sub(END_CASE_SEPARATOR, '', contents)

        yield RawTestChunk(name=name,
                           starting_lineno=current_lineno,
                           contents=contents)
        current_lineno += contents.count('\n') + 1


TEMP_DIR_PREFIX = 'mypy-pytest-'


def interpolate_environment_variables(environment: Dict[str, str],
                                      temp_directory: str) -> Dict[str, str]:
    interpolated: Dict[str, str] = {}
    for varname in environment:
        interpolated[varname] = environment[varname].replace('${MYPY_CWD}', str(temp_directory))
    return interpolated


def parse_test_chunk(raw_chunk: RawTestChunk, pytest_config: Optional[Config] = None) -> ParsedTestChunk:
    sections: Dict[str, List[str]] = {'main': []}
    current_section = 'main'
    for i, line in enumerate(raw_chunk.contents.split('\n')):
        if not sections[current_section] and not line:
            # skip first line, if section is empty
            continue
        if line.startswith('[') and line.endswith(']') and not line.startswith('[['):
            section = line[1:-1]
            sections[section] = []
            if not section.startswith(ONE_LINE_SECTIONS):
                current_section = section
            continue
        if line.startswith('[['):
            sections[current_section].append(line[1:])
            continue
        sections[current_section].append(line)

    custom_environment: Dict[str, str] = {}
    files_to_create: Dict[str, List[str]] = {}
    mypy_options: List[str] = []
    disable_cache = False
    for section in sections:
        if section in {'main', 'out'}:
            continue

        if section.startswith('env'):
            if sections[section]:
                raise ValueError('[env] section cannot have any value')

            _, _, variables = section.partition(' ')
            if variables:
                # replace template variables
                for defn in variables.split(';'):
                    name, value = defn.split('=', 1)
                    custom_environment[name] = value
            continue

        if section.startswith('file'):
            content_lines = sections[section]
            _, _, filename = section.partition(' ')
            if not filename:
                raise ValueError('[file] directive has to be in form of [file FILEPATH]')

            files_to_create[filename] = content_lines
            continue

        if section.startswith('mypy_options'):
            _, _, options_line = section.partition(' ')
            mypy_options = options_line.split(' ')
            continue

        if section == 'disable_cache':
            disable_cache = True

    # parse comments output from source code
    source_lines: List[str] = sections.get('main', [])
    output_from_comments: List[str] = []
    for filename, input_lines in itertools.chain([('main.py', source_lines)],
                                                 files_to_create.items()):
        file_output = extract_errors_from_comments(filename, input_lines)
        output_from_comments.extend(file_output)

    output = output_from_comments + [out_line for out_line in sections.get('out', [])
                                     if out_line != '']

    temp_base_dir = None
    if pytest_config is not None and hasattr(pytest_config, 'root_directory'):
        temp_base_dir = pytest_config.root_directory

    temp_dir = tempfile.TemporaryDirectory(prefix=TEMP_DIR_PREFIX, dir=temp_base_dir)
    interpolated_environment = interpolate_environment_variables(custom_environment,
                                                                 temp_directory=temp_dir.name)
    chunk = ParsedTestChunk(name=raw_chunk.name,
                            starting_lineno=raw_chunk.starting_lineno,
                            source_code='\n'.join(source_lines),
                            output_lines=output,
                            custom_environment=interpolated_environment,
                            files_to_create={fname: '\n'.join(lines) for fname, lines in files_to_create.items()},
                            temp_dir=temp_dir,
                            custom_mypy_options=mypy_options,
                            disable_cache=disable_cache)
    return chunk
