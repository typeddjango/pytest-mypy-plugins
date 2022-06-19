# Borrowed from Pew.
# See https://github.com/berdario/pew/blob/master/pew/_utils.py#L82
import contextlib
import inspect
import io
import os
import re
import sys
from dataclasses import dataclass
from itertools import zip_longest
from pathlib import Path
from typing import Any, Callable, Dict, Iterator, List, Mapping, Optional, Tuple, Union

import chevron
import regex
from decorator import contextmanager


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


def fname_to_module(fpath: Path, root_path: Path) -> Optional[str]:
    try:
        relpath = fpath.relative_to(root_path).with_suffix("")
        return str(relpath).replace(os.sep, ".")
    except ValueError:
        return None


# AssertStringArraysEqual displays special line alignment helper messages if
# the first different line has at least this many characters,
MIN_LINE_LENGTH_FOR_ALIGNMENT = 5


@dataclass
class OutputMatcher:
    fname: str
    lnum: int
    severity: str
    message: str
    regex: bool
    col: Optional[str] = None

    def matches(self, actual: str) -> bool:
        if self.regex:
            pattern = (
                regex.escape(
                    f"{self.fname}:{self.lnum}: {self.severity}: "
                    if self.col is None
                    else f"{self.fname}:{self.lnum}:{self.col}: {self.severity}: "
                )
                + self.message
            )
            return regex.match(pattern, actual)
        else:
            return str(self) == actual

    def __str__(self) -> str:
        if self.col is None:
            return f"{self.fname}:{self.lnum}: {self.severity}: {self.message}"
        else:
            return f"{self.fname}:{self.lnum}:{self.col}: {self.severity}: {self.message}"

    def __format__(self, format_spec: str) -> str:
        return format_spec.format(str(self))

    def __len__(self) -> int:
        return len(str(self))


class TypecheckAssertionError(AssertionError):
    def __init__(self, error_message: Optional[str] = None, lineno: int = 0) -> None:
        self.error_message = error_message or ""
        self.lineno = lineno

    def first_line(self) -> str:
        return self.__class__.__name__ + '(message="Invalid output")'

    def __str__(self) -> str:
        return self.error_message


def remove_common_prefix(lines: List[str]) -> List[str]:
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


def _add_aligned_message(s1: str, s2: str, error_message: str) -> str:
    """Align s1 and s2 so that the their first difference is highlighted.

    For example, if s1 is 'foobar' and s2 is 'fobar', display the
    following lines:

      E: foobar
      A: fobar
           ^

    If s1 and s2 are long, only display a fragment of the strings around the
    first difference. If s1 is very short, do nothing.
    """

    # Seeing what went wrong is trivial even without alignment if the expected
    # string is very short. In this case do nothing to simplify output.
    if len(s1) < 4:
        return error_message

    maxw = 72  # Maximum number of characters shown

    error_message += "Alignment of first line difference:\n"

    assert s1 != s2

    trunc = False
    while s1[:30] == s2[:30]:
        s1 = s1[10:]
        s2 = s2[10:]
        trunc = True

    if trunc:
        s1 = "..." + s1
        s2 = "..." + s2

    max_len = max(len(s1), len(s2))
    extra = ""
    if max_len > maxw:
        extra = "..."

    # Write a chunk of both lines, aligned.
    error_message += "  E: {}{}\n".format(s1[:maxw], extra)
    error_message += "  A: {}{}\n".format(s2[:maxw], extra)
    # Write an indicator character under the different columns.
    error_message += "     "
    # sys.stderr.write('     ')
    for j in range(min(maxw, max(len(s1), len(s2)))):
        if s1[j : j + 1] != s2[j : j + 1]:
            error_message += "^"
            break
        else:
            error_message += " "
    error_message += "\n"
    return error_message


def remove_empty_lines(lines: List[str]) -> List[str]:
    filtered_lines = []
    for line in lines:
        if line:
            filtered_lines.append(line)
    return filtered_lines


def sorted_by_file_and_line(lines: List[str]) -> List[str]:
    def extract_parts_as_tuple(line: str) -> Tuple[str, int]:
        if len(line.split(":", maxsplit=2)) < 3:
            return "", 0

        fname, line_number, _ = line.split(":", maxsplit=2)
        try:
            return fname, int(line_number)
        except ValueError:
            return "", 0

    return sorted(lines, key=extract_parts_as_tuple)


def assert_expected_matched_actual(expected: List[OutputMatcher], actual: List[str]) -> None:
    """Assert that two string arrays are equal.

    Display any differences in a human-readable form.
    """

    def format_mismatched_line(line: str) -> str:
        return "  {:<45} (diff)".format(str(line))

    def format_matched_line(line: str, width: int = 100) -> str:
        return " {}...".format(line[:width]) if len(line) > width else " {}".format(line)

    def format_error_lines(lines: List[str]) -> str:
        return "\n".join(lines) if lines else "  (empty)"

    expected = sorted(expected, key=lambda om: (om.fname, om.lnum))
    actual = sorted_by_file_and_line(remove_empty_lines(actual))

    actual = remove_common_prefix(actual)

    diff_lines: Dict[int, Tuple[OutputMatcher, str]] = {
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
                    expected_message_lines.append(format_mismatched_line(str(expected_line)))
                if actual_line:
                    actual_message_lines.append(format_mismatched_line(actual_line))

            else:
                expected_line, actual_line = expected[i], actual[i]
                actual_message_lines.append(format_matched_line(actual_line))
                expected_message_lines.append(format_matched_line(str(expected_line)))

        first_diff_expected, first_diff_actual = diff_lines[first_diff_line]

        failure_reason = "Output is not expected" if actual and not expected else "Invalid output"

        if actual_message_lines and expected_message_lines:
            if first_diff_line > 0:
                expected_message_lines.insert(0, "  ...")
                actual_message_lines.insert(0, "  ...")

            if last_diff_line < len(actual) - 1 and last_diff_line < len(expected) - 1:
                expected_message_lines.append("  ...")
                actual_message_lines.append("  ...")

        error_message = "Actual:\n{}\nExpected:\n{}\n".format(
            format_error_lines(actual_message_lines), format_error_lines(expected_message_lines)
        )

        if expected_line and expected_line.regex:
            error_message += "The actual output does not match the expected regex."
        elif (
            first_diff_actual is not None
            and first_diff_expected is not None
            and (
                len(first_diff_actual) >= MIN_LINE_LENGTH_FOR_ALIGNMENT
                or len(str(first_diff_expected)) >= MIN_LINE_LENGTH_FOR_ALIGNMENT
            )
        ):
            error_message = _add_aligned_message(str(first_diff_expected), first_diff_actual, error_message)

        raise TypecheckAssertionError(
            error_message=f"{failure_reason}: \n{error_message}",
            lineno=first_diff_expected.lnum if first_diff_expected else 0,
        )


def extract_output_matchers_from_comments(fname: str, input_lines: List[str], regex: bool) -> List[OutputMatcher]:
    """Transform comments such as '# E: message' or
    '# E:3: message' in input.

    The result is a list pf output matchers
    """
    fname = fname.replace(".py", "")
    matchers = []
    for index, line in enumerate(input_lines):
        # The first in the split things isn't a comment
        for possible_err_comment in line.split(" # ")[1:]:
            match = re.search(
                r"^([ENW])(?P<regex>[R])?:((?P<col>\d+):)? (?P<message>.*)$", possible_err_comment.strip()
            )
            if match:
                if match.group(1) == "E":
                    severity = "error"
                elif match.group(1) == "N":
                    severity = "note"
                elif match.group(1) == "W":
                    severity = "warning"
                else:
                    severity = match.group(1)
                col = match.group("col")
                matchers.append(
                    OutputMatcher(
                        fname,
                        index + 1,
                        severity,
                        message=match.group("message"),
                        regex=regex or bool(match.group("regex")),
                        col=col,
                    )
                )
    return matchers


def extract_output_matchers_from_out(out: str, params: Mapping[str, Any], regex: bool) -> List[OutputMatcher]:
    """Transform output lines such as 'function:9: E: message'

    The result is a list of output matchers
    """
    matchers = []
    lines = render_template(out, params).split("\n")
    for line in lines:
        match = re.search(
            r"^(?P<fname>.*):(?P<lnum>\d*): (?P<severity>.*):((?P<col>\d+):)? (?P<message>.*)$", line.strip()
        )
        if match:
            if match.group("severity") == "E":
                severity = "error"
            elif match.group("severity") == "N":
                severity = "note"
            elif match.group("severity") == "W":
                severity = "warning"
            else:
                severity = match.group("severity")
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


def render_template(template: str, data: Mapping[str, Any]) -> str:
    return chevron.render(template=template, data={k: v if v is not None else "None" for k, v in data.items()})


def get_func_first_lnum(attr: Callable[..., None]) -> Optional[Tuple[int, List[str]]]:
    lines, _ = inspect.getsourcelines(attr)
    for lnum, line in enumerate(lines):
        no_space_line = line.strip()
        if f"def {attr.__name__}" in no_space_line:
            return lnum, lines[lnum + 1 :]
    raise ValueError(f'No line "def {attr.__name__}" found')


@contextmanager
def cd(path: Union[str, Path]) -> Iterator[None]:
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


@contextmanager
def capture_std_streams() -> Iterator[Tuple[io.StringIO, io.StringIO]]:
    """Context manager to temporarily capture stdout and stderr.

    Returns ``(stdout, stderr)``.
    """
    out = io.StringIO()
    err = io.StringIO()
    with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
        yield out, err
