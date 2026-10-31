import os
import sys
from collections.abc import Iterator
from pathlib import Path

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
