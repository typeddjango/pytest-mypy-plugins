import dataclasses
import re
from typing import List, Dict, Any, Iterator

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


TEST_CASES_SEPARATOR = re.compile(r'^\[(?:case|CASE) ([a-zA-Z0-9_]+)\][ \t]*$\n',
                                  flags=re.MULTILINE)


def split_test_chunks(testfile_text: str) -> Iterator[RawTestChunk]:
    matches = re.split(TEST_CASES_SEPARATOR, testfile_text)

    current_lineno = matches[0].count('\n') + 1
    for i in range(1, len(matches), 2):
        name, contents = matches[i:i + 2]
        yield RawTestChunk(name=name,
                           starting_lineno=current_lineno,
                           contents=contents)
        current_lineno += contents.count('\n') + 1


def parse_test_chunk(raw_chunk: RawTestChunk) -> ParsedTestChunk:
    sections: Dict[str, List[str]] = {'main': []}
    current_section = 'main'
    for i, line in enumerate(raw_chunk.contents.split('\n')):
        if not sections[current_section] and not line:
            # skip first line, if section is empty
            continue

        if line.startswith('[') and line.endswith(']') and not line.startswith('[['):
            current_section = line[1:-1]
            sections[current_section] = []
            continue
        if line.startswith('[['):
            sections[current_section].append(line[1:])
            continue

        sections[current_section].append(line)

    custom_environment = {}
    files_to_create = {}
    for section in sections:
        if section in {'main', 'out'}:
            continue

        if section.startswith('env'):
            if sections[section]:
                raise ValueError('[env] section cannot have any value')

            _, _, variables = section.partition(' ')
            if variables:
                for defn in variables.split(';'):
                    name, value = defn.split('=', 1)
                    custom_environment[name] = value
            continue

        if section.startswith('file'):
            content_lines = sections[section]
            _, _, filename = section.partition(' ')
            if not filename:
                raise ValueError('[file] directive has to be in form of [file FILEPATH]')

            files_to_create[filename] = '\n'.join(content_lines)
            continue

    # parse comments output from source code
    source_lines = sections.get('main', [])
    output_from_comments = extract_errors_from_comments(source_lines, 'main')
    output = output_from_comments + sections.get('out', [])

    chunk = ParsedTestChunk(name=raw_chunk.name,
                            starting_lineno=raw_chunk.starting_lineno,
                            source_code='\n'.join(source_lines),
                            output_lines=output,
                            custom_environment=custom_environment,
                            files_to_create=files_to_create)
    return chunk
