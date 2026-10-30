from dataclasses import dataclass
from enum import IntEnum, unique
from typing import final


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
