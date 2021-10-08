# encoding=utf-8
import re
from typing import List, NamedTuple

import pytest

from pytest_mypy_plugins import utils
from pytest_mypy_plugins.utils import (
    OutputMatcher,
    TypecheckAssertionError,
    assert_expected_matched_actual,
    extract_output_matchers_from_comments,
)


class ExpectMatchedActualTestData(NamedTuple):
    source_lines: List[str]
    actual_lines: List[str]
    expected_message_lines: List[str]


def test_render_template_with_None_value() -> None:
    # Given
    template = "{{ a }} {{ b }}"
    data = {"a": None, "b": 99}

    # When
    actual = utils.render_template(template=template, data=data)

    # Then
    assert actual == "None 99"


expect_matched_actual_data = [
    ExpectMatchedActualTestData(
        [
            '''reveal_type(42)  # N: Revealed type is "Literal['foo']?"''',
            '''reveal_type("foo")  # N: Revealed type is "Literal[42]?"''',
        ],
        ['''main:1: note: Revealed type is "Literal[42]?"''', '''main:2: note: Revealed type is "Literal['foo']?"'''],
        [
            """Invalid output: """,
            """Actual:""",
            """  main:1: note: Revealed type is "Literal[42]?" (diff)""",
            """  main:2: note: Revealed type is "Literal['foo']?" (diff)""",
            """Expected:""",
            """  main:1: note: Revealed type is "Literal['foo']?" (diff)""",
            """  main:2: note: Revealed type is "Literal[42]?" (diff)""",
            """Alignment of first line difference:""",
            '''  E: ...ed type is "Literal['foo']?"''',
            '''  A: ...ed type is "Literal[42]?"''',
            """                            ^""",
            "",
        ],
    ),
    ExpectMatchedActualTestData(
        [
            """reveal_type(42)""",
            '''reveal_type("foo")  # N: Revealed type is "Literal['foo']?"''',
        ],
        ['''main:1: note: Revealed type is "Literal[42]?"''', '''main:2: note: Revealed type is "Literal['foo']?"'''],
        [
            """Invalid output: """,
            """Actual:""",
            """  main:1: note: Revealed type is "Literal[42]?" (diff)""",
            """  main:2: note: Revealed type is "Literal['foo']?" (diff)""",
            """Expected:""",
            """  main:2: note: Revealed type is "Literal['foo']?" (diff)""",
            """Alignment of first line difference:""",
            '''  E: main:2: note: Revealed type is "Literal['foo']?"''',
            '''  A: main:1: note: Revealed type is "Literal[42]?"''',
            """          ^""",
        ],
    ),
    ExpectMatchedActualTestData(
        ['''reveal_type(42)  # N: Revealed type is "Literal[42]?"''', """reveal_type("foo")"""],
        ['''main:1: note: Revealed type is "Literal[42]?"''', '''main:2: note: Revealed type is "Literal['foo']?"'''],
        [
            """Invalid output: """,
            """Actual:""",
            """  main:2: note: Revealed type is "Literal['foo']?" (diff)""",
            """Expected:""",
            """  (empty)""",
        ],
    ),
    ExpectMatchedActualTestData(
        ['''42 + "foo"'''],
        ["""main:1: error: Unsupported operand types for + ("int" and "str")"""],
        [
            """Output is not expected: """,
            """Actual:""",
            """  main:1: error: Unsupported operand types for + ("int" and "str") (diff)""",
            """Expected:""",
            """  (empty)""",
        ],
    ),
    ExpectMatchedActualTestData(
        [""" 1 + 1  # E: Unsupported operand types for + ("int" and "int")"""],
        [],
        [
            """Invalid output: """,
            """Actual:""",
            """  (empty)""",
            """Expected:""",
            """  main:1: error: Unsupported operand types for + ("int" and "int") (diff)""",
        ],
    ),
    ExpectMatchedActualTestData(
        [
            '''reveal_type(42)  # N: Revealed type is "Literal[42]?"''',
            '''reveal_type("foo")  # N: Revealed type is "builtins.int"''',
        ],
        ['''main:1: note: Revealed type is "Literal[42]?"''', '''main:2: note: Revealed type is "Literal['foo']?"'''],
        [
            """Invalid output: """,
            """Actual:""",
            """  ...""",
            """  main:2: note: Revealed type is "Literal['foo']?" (diff)""",
            """Expected:""",
            """  ...""",
            """  main:2: note: Revealed type is "builtins.int" (diff)""",
            """Alignment of first line difference:""",
            '''  E: ...te: Revealed type is "builtins.int"''',
            '''  A: ...te: Revealed type is "Literal['foo']?"''',
            """                              ^""",
        ],
    ),
    ExpectMatchedActualTestData(
        [
            '''reveal_type(42)  # N: Revealed type is "Literal[42]?"''',
            '''reveal_type("foo")  # N: Revealed type is "builtins.int"''',
        ],
        ['''main:1: note: Revealed type is "Literal[42]?"''', '''main:2: note: Revealed type is "Literal['foo']?"'''],
        [
            """Invalid output: """,
            """Actual:""",
            """  ...""",
            """  main:2: note: Revealed type is "Literal['foo']?" (diff)""",
            """Expected:""",
            """  ...""",
            """  main:2: note: Revealed type is "builtins.int" (diff)""",
            """Alignment of first line difference:""",
            '''  E: ...te: Revealed type is "builtins.int"''',
            '''  A: ...te: Revealed type is "Literal['foo']?"''',
            """                              ^""",
        ],
    ),
    ExpectMatchedActualTestData(
        [
            '''reveal_type(42.0)  # N: Revealed type is "builtins.float"''',
            '''reveal_type("foo")  # N: Revealed type is "builtins.int"''',
            '''reveal_type(42)  # N: Revealed type is "Literal[42]?"''',
        ],
        [
            '''main:1: note: Revealed type is "builtins.float"''',
            '''main:2: note: Revealed type is "Literal['foo']?"''',
            '''main:3: note: Revealed type is "Literal[42]?"''',
        ],
        [
            """Invalid output: """,
            """Actual:""",
            """  ...""",
            """  main:2: note: Revealed type is "Literal['foo']?" (diff)""",
            """  ...""",
            """Expected:""",
            """  ...""",
            """  main:2: note: Revealed type is "builtins.int" (diff)""",
            """  ...""",
            """Alignment of first line difference:""",
            '''  E: ...te: Revealed type is "builtins.int"''',
            '''  A: ...te: Revealed type is "Literal['foo']?"''',
            """                              ^""",
        ],
    ),
]


@pytest.mark.parametrize("source_lines,actual_lines,expected_message_lines", expect_matched_actual_data)
def test_assert_expected_matched_actual_failures(
    source_lines: List[str], actual_lines: List[str], expected_message_lines: List[str]
):
    expected: List[OutputMatcher] = extract_output_matchers_from_comments("main", source_lines, False)
    expected_error_message = re.escape("\n".join(expected_message_lines))

    with pytest.raises(TypecheckAssertionError, match=expected_error_message):
        assert_expected_matched_actual(expected, actual_lines)
