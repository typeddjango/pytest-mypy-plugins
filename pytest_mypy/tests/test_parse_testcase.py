from pathlib import Path

from pytest_mypy.parser import ParsedTestChunk, RawTestChunk, parse_test_chunk

TEST_FILES_ROOT = Path(__file__).parent / 'files' / 'parse'


def _parse_file_content(fpath: Path) -> ParsedTestChunk:
    contents = fpath.read_text()
    raw_chunk = RawTestChunk(name='myTest', starting_lineno=1, contents=contents)
    return parse_test_chunk(raw_chunk)


def test_raw_chunk_with_no_parameters():
    raw_chunk = RawTestChunk(name='myTest', starting_lineno=1, contents='hello, world')
    chunk = parse_test_chunk(raw_chunk)

    assert chunk.name == 'myTest'
    assert chunk.source_code == 'hello, world'
    assert chunk.output_lines == []


def test_output_lines():
    chunk = _parse_file_content(TEST_FILES_ROOT / 'output.txt')
    assert chunk.output_lines == ['hello, world']


def test_source_code_has_square_brackets():
    chunk = _parse_file_content(TEST_FILES_ROOT / 'double_brackets.txt')
    assert chunk.source_code == "[mypy]\nprint('hello, world')"


def test_source_code_has_env():
    chunk = _parse_file_content(TEST_FILES_ROOT / 'env.txt')
    assert chunk.custom_environment == {'DJANGO_SETTINGS_MODULE': 'mysettings',
                                        'PATH': '/root/path'}


def test_interpolate_cwd_variable():
    contents = (TEST_FILES_ROOT / 'variables.txt').read_text()
    raw_chunk = RawTestChunk(name='myTest', starting_lineno=1, contents=contents)
    chunk = parse_test_chunk(raw_chunk)
    assert chunk.custom_environment['CONFIG_FILE'] == chunk.temp_dir.name + '/mypy.ini'


def test_add_files():
    chunk = _parse_file_content(TEST_FILES_ROOT / 'add_files.txt')
    assert chunk.files_to_create == {'mysettings.py': 'mysetting',
                                     'mysettings2.py': 'mysetting2\n'}


def test_parse_python_code():
    chunk = _parse_file_content(TEST_FILES_ROOT / 'python.txt')
    code = """
class MyClass:
    class Meta:
        pass

def func(arg: str): pass
""".lstrip()
    assert chunk.source_code == code


def test_revealed_type_comments():
    chunk = _parse_file_content(TEST_FILES_ROOT / 'revealed_type_comments.txt')
    assert chunk.output_lines == [
        "main:5: error: Revealed type is 'builtins.int'",
        "main:6: error: Revealed type is 'builtins.str'"
    ]
