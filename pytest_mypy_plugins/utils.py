# Borrowed from Pew.
# See https://github.com/berdario/pew/blob/master/pew/_utils.py#L82
import inspect
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from itertools import zip_longest
from typing import (
    Any,
    Final,
)

import jinja2
import regex

from pytest_mypy_plugins.logic import files, text

_rendering_env = jinja2.Environment()

_SEVERITY_MAP: Final = {
    "E": "error",
    "N": "note",
    "W": "warning",
}

# AssertStringArraysEqual displays special line alignment helper messages if
# the first different line has at least this many characters,
_MIN_LINE_LENGTH_FOR_ALIGNMENT: Final = 5


_MYPY_OUTPUT_LINE_RE: Final = re.compile(
    r"^(?P<fname>.+):(?P<lnum>\d+): (?P<severity>[A-Za-z]+):((?P<col>\d+):)? (?P<message>.*)$"
)


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


def assert_expected_matched_actual(
    expected: list[OutputMatcher], actual: list[str]
) -> None:
    """Assert that two string arrays are equal.

    Display any differences in a human-readable form.
    """

    expected = sorted(expected, key=lambda om: (om.file_name, om.lnum))
    actual = text.remove_common_prefix(
        files.sorted_by_file_and_line(text.remove_empty_lines(actual))
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
                        text.format_mismatched_line(str(expected_line))
                    )
                if actual_line:
                    actual_message_lines.append(
                        text.format_mismatched_line(actual_line)
                    )

            else:
                expected_line, actual_line = expected[i], actual[i]
                actual_message_lines.append(
                    text.format_matched_line(actual_line)
                )
                expected_message_lines.append(
                    text.format_matched_line(str(expected_line))
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
            text.format_error_lines(actual_message_lines),
            text.format_error_lines(expected_message_lines),
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
            error_message = text.add_aligned_message(
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
