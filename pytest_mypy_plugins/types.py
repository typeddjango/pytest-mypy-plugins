from dataclasses import dataclass
from enum import IntEnum, unique
from typing import NamedTuple, final

import regex


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


@dataclass
class File:
    path: str
    content: str


@final
@unique
class ReturnCodes(IntEnum):
    SUCCESS = 0
    FAIL = 1
    FATAL_ERROR = 2


class DiffMessageLines(NamedTuple):
    expected: list[str]
    actual: list[str]
    last_expected_line: OutputMatcher | None
