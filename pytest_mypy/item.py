import os
import shutil
import sys
import tempfile
import time
from pathlib import Path
from typing import Dict, List, Optional, Set, TYPE_CHECKING

import capturer
import pytest
from _pytest._code.code import ExceptionInfo, ReprEntry, ReprFileLocation
from _pytest.config import Config
from mypy import build
from mypy.fscache import FileSystemCache
from mypy.main import process_options
from mypy.options import Options

from pytest_mypy import utils
from pytest_mypy.utils import TypecheckAssertionError, assert_string_arrays_equal, fname_to_module

if TYPE_CHECKING:
    from pytest_mypy.collect import DotTestFile


class TraceLastReprEntry(ReprEntry):
    def toterminal(self, tw):
        self.reprfileloc.toterminal(tw)
        for line in self.lines:
            red = line.startswith("E   ")
            tw.line(line, bold=True, red=red)
        return


def make_files(rootdir: Path, files_to_create: Dict[str, str]) -> List[str]:
    created_modules = []
    for rel_fpath, file_contents in files_to_create.items():
        fpath = rootdir / rel_fpath
        fpath.parent.mkdir(parents=True, exist_ok=True)
        fpath.write_text(file_contents)

        created_module = fname_to_module(fpath, root_path=rootdir)
        if created_module:
            created_modules.append(created_module)
    return created_modules


def replace_fpath_with_module_name(line: str, rootdir: Path) -> str:
    if ':' not in line:
        return line
    out_fpath, res_line = line.split(':', 1)
    line = os.path.relpath(out_fpath, start=rootdir) + ':' + res_line
    return line.strip().replace('.py', '')


class ReturnCodes:
    SUCCESS = 0
    FAIL = 1
    FATAL_ERROR = 2


def get_module_files_in_cache(cache_dir: Path, module_qualname: str) -> List[Path]:
    base_path = cache_dir.joinpath(*module_qualname.split('.'))
    return [base_path.with_suffix('.data.json'), base_path.with_suffix('.meta.json')]


def get_cache_dir(options: Options) -> Path:
    python_version_dir = '.'.join([str(part) for part in options.python_version])
    return Path(os.getcwd()) / options.cache_dir / python_version_dir


def typecheck_with_mypy(cmd_options: List[str],
                        *,
                        disable_cache_for: Optional[Set[str]] = None) -> int:
    fscache = FileSystemCache()
    sources, options = process_options(cmd_options, fscache=fscache)

    error_messages = []

    def flush_errors(new_messages: List[str], serious: bool) -> None:
        error_messages.extend(new_messages)
        f = sys.stderr if serious else sys.stdout
        try:
            for msg in new_messages:
                f.write(msg + '\n')
            f.flush()
        except BrokenPipeError:
            sys.exit(ReturnCodes.FATAL_ERROR)

    try:
        build.build(sources, options,
                    flush_errors=flush_errors, fscache=fscache)

    except SystemExit as sysexit:
        return sysexit.code
    finally:
        fscache.flush()
        if disable_cache_for:
            cache_dir = get_cache_dir(options)
            for module_qualname in disable_cache_for:
                for cache_file in get_module_files_in_cache(cache_dir, module_qualname):
                    if cache_file.exists():
                        cache_file.unlink()

    if error_messages:
        return ReturnCodes.FAIL
    return ReturnCodes.SUCCESS


class TestItem(pytest.Item):
    def __init__(self,
                 name: str,
                 collector: 'DotTestFile',
                 config: Config,
                 source_code: str,
                 starting_lineno: int,
                 output_lines: List[str],
                 files: Dict[str, str],
                 custom_environment: Dict[str, str],
                 temp_dir: tempfile.TemporaryDirectory,
                 mypy_options: List[str]) -> None:
        super().__init__(name, collector, config)
        self.name = name
        self.source_code = source_code
        self.starting_lineno = starting_lineno
        self.expected_output_lines = output_lines
        self.root_directory = config.option.mypy_testing_base
        if config.option.mypy_ini_file:
            mypy_ini_file_abspath = os.path.abspath(config.option.mypy_ini_file)
        else:
            mypy_ini_file_abspath = None
        self.base_ini_fpath = mypy_ini_file_abspath
        self.disable_cache_for_modules = config.option.mypy_no_cache
        self.files = files
        self.custom_environment = custom_environment
        self.temp_dir = temp_dir
        self.mypy_options = mypy_options

    def runtest(self):
        tmpdir_path = Path(self.temp_dir.name)
        assert tmpdir_path.exists()

        try:
            if not self.source_code:
                return
            test_specific_modules = make_files(tmpdir_path, self.files)
            # TODO: add check for python >= 3.6

            with utils.temp_environ(), utils.temp_path(), utils.cd(tmpdir_path):
                for key, val in (self.custom_environment or {}).items():
                    os.environ[key] = val
                sys.path.insert(0, str(tmpdir_path))

                mypy_cmd_options = self.prepare_mypy_cmd_options()
                main_fpath = tmpdir_path / 'main.py'
                main_fpath.write_text(self.source_code)
                mypy_cmd_options.append(str(main_fpath))

                with capturer.CaptureOutput() as captured_std_streams:
                    disable_cache_for = None
                    if self.disable_cache_for_modules:
                        disable_cache_for = set(test_specific_modules + ['main'])
                    return_code = typecheck_with_mypy(mypy_cmd_options,
                                                      disable_cache_for=disable_cache_for)

                if return_code == ReturnCodes.FATAL_ERROR:
                    raise TypecheckAssertionError(error_message='Critical error occurred')

                output_lines = []
                for line in captured_std_streams.get_lines():
                    output_lines.append(replace_fpath_with_module_name(line, rootdir=tmpdir_path))

                for module in test_specific_modules:
                    # remove created modules from sys.modules, so name could be reused
                    parts = module.split('.')
                    for i in range(len(parts)):
                        parent_module = '.'.join(parts[:i + 1])
                        if parent_module in sys.modules:
                            del sys.modules[parent_module]

                assert_string_arrays_equal(expected=self.expected_output_lines,
                                           actual=output_lines)
        finally:
            self.temp_dir.cleanup()

    def prepare_mypy_cmd_options(self) -> List[str]:
        incremental_cache_dir = os.path.join(self.root_directory, '.mypy_cache')

        mypy_cmd_options = [
            '--show-traceback',
            '--no-silence-site-packages',
            '--cache-dir',
            incremental_cache_dir
        ]

        python_version = '.'.join([str(part) for part in sys.version_info[:2]])
        mypy_cmd_options.append(f'--python-version={python_version}')
        if self.base_ini_fpath:
            mypy_cmd_options.append(f'--config-file={self.base_ini_fpath}')

        if self.mypy_options:
            mypy_cmd_options.extend(self.mypy_options)

        return mypy_cmd_options

    def repr_failure(self, excinfo: ExceptionInfo) -> str:
        if excinfo.errisinstance(SystemExit):
            # We assume that before doing exit() (which raises SystemExit) we've printed
            # enough context about what happened so that a stack trace is not useful.
            # In particular, uncaught exceptions during semantic analysis or type checking
            # call exit() and they already print out a stack trace.
            return excinfo.exconly(tryshort=True)
        elif excinfo.errisinstance(TypecheckAssertionError):
            # with traceback removed
            exception_repr = excinfo.getrepr(style='short')
            exception_repr.reprcrash.message = ''
            repr_file_location = ReprFileLocation(path=self.fspath,
                                                  lineno=self.starting_lineno + excinfo.value.lineno,
                                                  message='')
            repr_tb_entry = TraceLastReprEntry(filelocrepr=repr_file_location,
                                               lines=exception_repr.reprtraceback.reprentries[-1].lines[1:],
                                               style='short',
                                               reprlocals=None,
                                               reprfuncargs=None)
            exception_repr.reprtraceback.reprentries = [repr_tb_entry]
            return exception_repr
        else:
            return super().repr_failure(excinfo, style='native')

    def reportinfo(self):
        return self.fspath, None, self.name
