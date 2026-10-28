# Borrowed from Pew.
# See https://github.com/berdario/pew/blob/master/pew/_utils.py#L82
import inspect
import os
import re
import sys
from collections.abc import Callable, Iterator, Mapping
from dataclasses import dataclass
from itertools import zip_longest
from pathlib import Path
from typing import (
    Any,
    Final,
)

import jinja2
import regex
from decorator import contextmanager

_rendering_env = jinja2.Environment()

_SEVERITY_MAP: Final = {
    "E": "error",
    "N": "note",
    "W": "warning",
}

# AssertStringArraysEqual displays special line alignment helper messages if
# the first different line has at least this many characters,
_MIN_LINE_LENGTH_FOR_ALIGNMENT: Final = 5

_MIN_ALIGNMENT_STRING_LENGTH: Final = 4
_MAX_ALIGNMENT_WIDTH: Final = 72
_MAX_LINE_SPLIT_PARTS: Final = 3
_ALIGNMENT_MARKER: Final = "^"
_TRUNCATION_MARKER: Final = "..."
_TRUNCATION_STEP: Final = 10
_TRUNCATION_WINDOW: Final = 30

_MYPY_OUTPUT_LINE_RE: Final = re.compile(
    r"^(?P<fname>.+):(?P<lnum>\d+): (?P<severity>[A-Za-z]+):((?P<col>\d+):)? (?P<message>.*)$"
)


@contextmanager
def temp_environ() -> Iterator[None]:
    """Allow the ability to set os.environ temporarily"""
    environ = dict(os.environ)
    try:
        yield
    finally:
        os.environ.clear()
        os.environ.update(environ)


@contextmanager
def temp_path() -> Iterator[None]:
    """A context manager which allows the ability to set sys.path temporarily"""
    path = sys.path[:]
    try:
        yield
    finally:
        sys.path = path[:]


@contextmanager
def temp_sys_modules() -> Iterator[None]:
    sys_modules = sys.modules.copy()
    try:
        yield
    finally:
        sys.modules = sys_modules.copy()


def fname_to_module(fpath: Path, root_path: Path) -> str | None:
    try:
        relpath = fpath.relative_to(root_path).with_suffix("")
        return str(relpath).replace(os.sep, ".")
    except ValueError:
        return None


@dataclass
class OutputMatcher:
    file_name: str
    lnum: int
    severity: str
    message: str
    regex: bool
    col: str | None = None

    def matches(self, actual: str) -> bool:
        if self.regex:
            pattern = (
                regex.escape(
                    f"{self.file_name}:{self.lnum}: {self.severity}: "
                    if self.col is None
                    else f"{self.file_name}:{self.lnum}:{self.col}: {self.severity}: "
                )
                + self.message
            )
            return bool(regex.match(pattern, actual))
        return str(self) == actual

    def __str__(self) -> str:
        if self.col is None:
            return (
                f"{self.file_name}:{self.lnum}: {self.severity}: {self.message}"
            )
        return f"{self.file_name}:{self.lnum}:{self.col}: {self.severity}: {self.message}"

    def __format__(self, format_spec: str) -> str:
        return format_spec.format(str(self))

    def __len__(self) -> int:
        return len(str(self))


class TypecheckAssertionError(AssertionError):
    def __init__(
        self, error_message: str | None = None, lineno: int = 0
    ) -> None:
        self.error_message = error_message or ""
        self.lineno = lineno

    def first_line(self) -> str:
        return self.__class__.__name__ + '(message="Invalid output")'

    def __str__(self) -> str:
        return self.error_message


def remove_common_prefix(lines: list[str]) -> list[str]:
    """Remove common directory prefix from all strings in a.

    This uses a naive string replace; it seems to work well enough. Also
    remove trailing carriage returns.
    """
    cleaned_lines = []
    for line in lines:
        # Ignore spaces at end of line.
        line = re.sub(" +$", "", line)
        cleaned_lines.append(re.sub("\\r$", "", line))
    return cleaned_lines


def _add_aligned_message(word1: str, word2: str, error_message: str) -> str:
    """Align word1 and word2 so that the their first difference is highlighted.

    For example, if word1 is 'foobar' and word2 is 'fobar', display the
    following lines:

      E: foobar
      A: fobar
           ^

    If word1 and word2 are long, only display a fragment of the strings around the
    first difference. If word1 is very short, do nothing.
    """

    # Seeing what went wrong is trivial even without alignment if the expected
    # string is very short. In this case do nothing to simplify output.
    if len(word1) < _MIN_ALIGNMENT_STRING_LENGTH:
        return error_message

    error_message += "Alignment of first line difference:\n"

    assert word1 != word2

    trunc = False
    while word1[:_TRUNCATION_WINDOW] == word2[:_TRUNCATION_WINDOW]:
        word1 = word1[_TRUNCATION_STEP:]
        word2 = word2[_TRUNCATION_STEP:]
        trunc = True

    if trunc:
        word1 = _TRUNCATION_MARKER + word1
        word2 = _TRUNCATION_MARKER + word2

    max_len = max(len(word1), len(word2))
    extra = _TRUNCATION_MARKER if max_len > _MAX_ALIGNMENT_WIDTH else ""

    # Write a chunk of both lines, aligned.
    error_message += f"  E: {word1[:_MAX_ALIGNMENT_WIDTH]}{extra}\n"
    error_message += f"  A: {word2[:_MAX_ALIGNMENT_WIDTH]}{extra}\n"
    # Write an indicator character under the different columns.
    error_message += "     "
    # sys.stderr.write('     ')
    for pos in range(min(_MAX_ALIGNMENT_WIDTH, max_len)):
        if word1[pos : pos + 1] != word2[pos : pos + 1]:
            error_message += _ALIGNMENT_MARKER
            break
        else:
            error_message += " "
    error_message += "\n"
    return error_message


def remove_empty_lines(lines: list[str]) -> list[str]:
    return list(filter(None, lines))


def sorted_by_file_and_line(lines: list[str]) -> list[str]:
    def extract_parts_as_tuple(line: str) -> tuple[str, int]:
        if len(line.split(":", maxsplit=2)) < _MAX_LINE_SPLIT_PARTS:
            return "", 0

        file_name, line_number, _ = line.split(":", maxsplit=2)
        try:
            return file_name, int(line_number)
        except ValueError:
            return "", 0

    return sorted(lines, key=extract_parts_as_tuple)


def assert_expected_matched_actual(
    expected: list[OutputMatcher], actual: list[str]
) -> None:
    """Assert that two string arrays are equal.

    Display any differences in a human-readable form.
    """

    def format_mismatched_line(line: str) -> str:
        return f"  {str(line):<45} (diff)"

    def format_matched_line(line: str, width: int = 100) -> str:
        return f" {line[:width]}..." if len(line) > width else f" {line}"

    def format_error_lines(lines: list[str]) -> str:
        return "\n".join(lines) if lines else "  (empty)"

    expected = sorted(expected, key=lambda om: (om.file_name, om.lnum))
    actual = remove_common_prefix(
        sorted_by_file_and_line(remove_empty_lines(actual))
    )

    diff_lines: dict[int, tuple[OutputMatcher, str]] = {
        i: (e, a)
        for i, (e, a) in enumerate(zip_longest(expected, actual))
        if e is None or a is None or not e.matches(a)
    }

    if diff_lines:
        first_diff_line = min(diff_lines.keys())
        last_diff_line = max(diff_lines.keys())

        expected_message_lines = []
        actual_message_lines = []

        for i in range(first_diff_line, last_diff_line + 1):
            if i in diff_lines:
                expected_line, actual_line = diff_lines[i]
                if expected_line:
                    expected_message_lines.append(
                        format_mismatched_line(str(expected_line))
                    )
                if actual_line:
                    actual_message_lines.append(
                        format_mismatched_line(actual_line)
                    )

            else:
                expected_line, actual_line = expected[i], actual[i]
                actual_message_lines.append(format_matched_line(actual_line))
                expected_message_lines.append(
                    format_matched_line(str(expected_line))
                )

        first_diff_expected, first_diff_actual = diff_lines[first_diff_line]

        failure_reason = (
            "Output is not expected"
            if actual and not expected
            else "Invalid output"
        )

        if actual_message_lines and expected_message_lines:
            if first_diff_line > 0:
                expected_message_lines.insert(0, "  ...")
                actual_message_lines.insert(0, "  ...")

            if (
                last_diff_line < len(actual) - 1
                and last_diff_line < len(expected) - 1
            ):
                expected_message_lines.append("  ...")
                actual_message_lines.append("  ...")

        error_message = "Actual:\n{}\nExpected:\n{}\n".format(
            format_error_lines(actual_message_lines),
            format_error_lines(expected_message_lines),
        )

        if expected_line and expected_line.regex:
            error_message += (
                "The actual output does not match the expected regex."
            )
        elif (
            first_diff_actual is not None
            and first_diff_expected is not None
            and (
                len(first_diff_actual) >= _MIN_LINE_LENGTH_FOR_ALIGNMENT
                or len(str(first_diff_expected))
                >= _MIN_LINE_LENGTH_FOR_ALIGNMENT
            )
        ):
            error_message = _add_aligned_message(
                str(first_diff_expected), first_diff_actual, error_message
            )

        raise TypecheckAssertionError(
            error_message=f"{failure_reason}: \n{error_message}",
            lineno=first_diff_expected.lnum if first_diff_expected else 0,
        )


def extract_output_matchers_from_comments(
    file_name: str, input_lines: list[str], regex: bool
) -> list[OutputMatcher]:
    """Transform comments such as '# E: message' or
    '# E:3: message' in input.

    The result is a list pf output matchers
    """
    file_name = file_name.removesuffix(".py")
    matchers = []
    for index, line in enumerate(input_lines):
        # The first in the split things isn't a comment
        for possible_err_comment in line.split(" # ")[1:]:
            match = re.search(
                r"^([ENW])(?P<regex>[R])?:((?P<col>\d+):)? (?P<message>.*)$",
                possible_err_comment.strip(),
            )
            if match:
                raw_severity = match.group(1)
                severity = _SEVERITY_MAP.get(match.group(1), raw_severity)
                col = match.group("col")
                matchers.append(
                    OutputMatcher(
                        file_name,
                        index + 1,
                        severity,
                        message=match.group("message"),
                        regex=regex or bool(match.group("regex")),
                        col=col,
                    )
                )
    return matchers


def extract_output_matchers_from_out(
    out: str, params: Mapping[str, Any], regex: bool
) -> list[OutputMatcher]:
    """Transform output lines such as 'function:9: E: message'

    The result is a list of output matchers
    """
    matchers = []
    lines = render_template(out, params).split("\n")
    for line in lines:
        match = re.search(
            _MYPY_OUTPUT_LINE_RE,
            line.strip(),
        )
        if match:
            raw_severity = match.group("severity")
            severity = _SEVERITY_MAP.get(match.group("severity"), raw_severity)
            col = match.group("col")
            matchers.append(
                OutputMatcher(
                    match.group("fname"),
                    int(match.group("lnum")),
                    severity,
                    message=match.group("message"),
                    regex=regex,
                    col=col,
                )
            )
    return matchers


def render_template(template: str, parametrized_data: Mapping[str, Any]) -> str:
    if _rendering_env.variable_start_string not in template:
        return template

    jinja_template: jinja2.environment.Template = _rendering_env.from_string(
        template
    )
    return jinja_template.render(
        {
            key: value_param if value_param is not None else "None"
            for key, value_param in parametrized_data.items()
        }
    )


def get_func_first_lnum(
    attr: Callable[..., None],
) -> tuple[int, list[str]] | None:
    lines, _ = inspect.getsourcelines(attr)
    for lnum, line in enumerate(lines):
        no_space_line = line.strip()
        if f"def {attr.__name__}" in no_space_line:
            return lnum, lines[lnum + 1 :]
    raise ValueError(f'No line "def {attr.__name__}" found')


@contextmanager
def cd(path: str | Path) -> Iterator[None]:
    """Context manager to temporarily change working directories"""
    if not path:
        return
    prev_cwd = Path.cwd().as_posix()
    if isinstance(path, Path):
        path = path.as_posix()
    os.chdir(str(path))
    try:
        yield
    finally:
        os.chdir(prev_cwd)
