from dataclasses import dataclass


@dataclass
class File:
    path: str
    content: str
