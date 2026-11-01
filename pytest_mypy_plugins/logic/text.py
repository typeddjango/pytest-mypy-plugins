import re
from typing import Final

_ALIGNMENT_MARKER: Final = "^"
_TRUNCATION_MARKER: Final = "..."
_TRUNCATION_STEP: Final = 10
_TRUNCATION_WINDOW: Final = 30
_MIN_ALIGNMENT_STRING_LENGTH: Final = 4
_MAX_ALIGNMENT_WIDTH: Final = 72


def format_mismatched_line(line: str) -> str:
    return f"  {str(line):<45} (diff)"


def format_matched_line(line: str, width: int = 100) -> str:
    line = line[:width]
    return f" {line}..." if len(line) > width else f" {line}"


def format_error_lines(lines: list[str]) -> str:
    return "\n".join(lines) if lines else "  (empty)"


def remove_empty_lines(lines: list[str]) -> list[str]:
    return list(filter(None, lines))


def add_aligned_message(word1: str, word2: str, error_message: str) -> str:
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

    error_message += "Alignment of first line difference:\n"  # noqa: WPS336

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
    word1_format = word1[:_MAX_ALIGNMENT_WIDTH] + extra
    word2_format = word2[:_MAX_ALIGNMENT_WIDTH] + extra

    # Write a chunk of both lines, aligned.
    error_message += f"  E: {word1_format}\n"  # noqa: WPS336
    error_message += f"  A: {word2_format}\n"  # noqa: WPS336
    # Write an indicator character under the different columns.
    error_message += _format_alignment_pointer(word1, word2, max_len)
    return error_message


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


def _format_alignment_pointer(word1: str, word2: str, max_len: int) -> str:
    error_message = ["     "]
    for pos in range(min(_MAX_ALIGNMENT_WIDTH, max_len)):
        word1 = word1[pos : pos + 1]
        word2 = word2[pos : pos + 1]
        if word1 == word2:
            error_message.append(" ")
        else:
            error_message.append(_ALIGNMENT_MARKER)
            break
    error_message.append("\n")
    return "".join(error_message)
