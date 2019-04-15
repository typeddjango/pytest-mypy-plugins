import os
import sys
import tempfile
from pathlib import Path
from typing import List, Dict, Any

import capturer
import pytest
from _pytest._code import ExceptionInfo
from _pytest._code.code import ReprFileLocation, ReprEntry
from _pytest.config import Config
from mypy import build
from mypy.fscache import FileSystemCache
from mypy.main import process_options

from pytest_mypy import utils
from pytest_mypy.collect import File, YamlTestFile
from pytest_mypy.utils import TypecheckAssertionError, assert_string_arrays_equal, fname_to_module


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


def typecheck_with_mypy(cmd_options: List[str]) -> int:
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

    if error_messages:
        return ReturnCodes.FAIL

    return ReturnCodes.SUCCESS


class TestItem(pytest.Item):
    def __init__(self,
                 name: str,
                 collector: YamlTestFile,
                 config: Config,
                 files: List[File],
                 starting_lineno: int,
                 expected_output_lines: List[str],
                 extra_environment_variables: Dict[str, Any],
                 disable_cache: bool) -> None:
        super().__init__(name, collector, config)
        self.files = files
        self.extra_environment_variables = extra_environment_variables
        self.disable_cache = disable_cache
        self.expected_output_lines = expected_output_lines
        self.starting_lineno = starting_lineno

        # config parameters
        self.root_directory = config.option.mypy_testing_base
        if config.option.mypy_ini_file:
            self.base_ini_fpath = os.path.abspath(config.option.mypy_ini_file)
        else:
            self.base_ini_fpath = None

    def make_test_files_in_current_directory(self) -> None:
        """ Returns path to the main file of the test"""
        current_directory = Path.cwd()
        for file in self.files:
            fpath = current_directory / file.path
            fpath.parent.mkdir(parents=True, exist_ok=True)
            fpath.write_text(file.content)

    def runtest(self):
        # test_execution_dirpath = Path(self.temp_dir.name)
        # assert test_execution_dirpath.exists()

        try:
            # if not self.source_code:
            #     return
            # test_specific_modules = make_files(test_execution_dirpath, self.files)
            temp_dir = tempfile.TemporaryDirectory(prefix='pytest-mypy-', dir=self.root_directory)
            execution_path = Path(temp_dir.name)
            assert execution_path.exists()

            with utils.temp_environ(), utils.temp_path(), utils.cd(execution_path), utils.temp_sys_modules():
                # add custom environment variables
                for key, val in self.extra_environment_variables.items():
                    os.environ[key] = val

                # add current directory to path
                sys.path.insert(0, str(execution_path))

                # start from main.py
                mypy_cmd_options = self.prepare_mypy_cmd_options()
                mypy_cmd_options.append(str(execution_path / 'main.py'))

                # make files
                self.make_test_files_in_current_directory()

                # main_fpath = test_execution_dirpath / 'main.py'
                # main_fpath.write_text(self.source_code)
                # mypy_cmd_options.append(str(main_fpath))

                with capturer.CaptureOutput() as captured_std_streams:
                    return_code = typecheck_with_mypy(mypy_cmd_options)

                if return_code == ReturnCodes.FATAL_ERROR:
                    raise TypecheckAssertionError(error_message='Critical error occurred')

                output_lines = []
                for line in captured_std_streams.get_lines():
                    output_line = replace_fpath_with_module_name(line, rootdir=execution_path)
                    output_lines.append(output_line)

                # for module in test_specific_modules:
                #     # remove created modules from sys.modules, so name could be reused
                #     parts = module.split('.')
                #     for i in range(len(parts)):
                #         parent_module = '.'.join(parts[:i + 1])
                #         if parent_module in sys.modules:
                #             del sys.modules[parent_module]

                assert_string_arrays_equal(expected=self.expected_output_lines,
                                           actual=output_lines)
        finally:
            temp_dir.cleanup()

    def prepare_mypy_cmd_options(self) -> List[str]:
        incremental_cache_dir = os.path.join(self.root_directory, '.mypy_cache')

        mypy_cmd_options = [
            '--show-traceback',
            '--no-silence-site-packages',
        ]
        if not self.disable_cache:
            mypy_cmd_options.extend([
                '--cache-dir',
                incremental_cache_dir
            ])

        python_version = '.'.join([str(part) for part in sys.version_info[:2]])
        mypy_cmd_options.append(f'--python-version={python_version}')
        if self.base_ini_fpath:
            mypy_cmd_options.append(f'--config-file={self.base_ini_fpath}')

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
