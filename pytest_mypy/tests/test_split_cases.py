from pathlib import Path

from pytest_mypy.parser import split_test_chunks

TEST_FILES_ROOT = Path(__file__).parent / 'files' / 'split'


def test_parse_hello_world_test():
    text = (TEST_FILES_ROOT / 'hello-world.txt').read_text()
    cases = list(split_test_chunks(text))

    assert len(cases) == 1
    assert cases[0].name == 'testHelloWorld'
    assert cases[0].contents == 'print("hello, world")'


def test_split_two_test_cases():
    text = (TEST_FILES_ROOT / 'two-tests.txt').read_text()
    cases = list(split_test_chunks(text))

    assert len(cases) == 2
    assert cases[0].name == 'testOne'
    assert cases[0].starting_lineno == 1
    assert cases[1].name == 'testTwo'
    assert cases[1].starting_lineno == 4


def test_case_with_indented_code():
    text = (TEST_FILES_ROOT / 'python.txt').read_text()
    cases = list(split_test_chunks(text))

    code = """
class MyClass:
    class Meta:
        pass

def func(arg: str): pass
""".lstrip()
    assert cases[0].contents == code
