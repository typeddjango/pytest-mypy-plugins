import os
import sys
import tempfile
from pathlib import Path
from typing import TYPE_CHECKING, List, Dict, Iterator

import pytest
from _pytest._code.code import ReprFileLocation, ReprEntry, ExceptionInfo
from _pytest.config import Config
from decorator import contextmanager
from mypy import api as mypy_api

from pytest_mypy import utils
from pytest_mypy.utils import fname_to_module, assert_string_arrays_equal, TypecheckAssertionError

if TYPE_CHECKING:
    from pytest_mypy.collect import DotTestFile


class TraceLastReprEntry(ReprEntry):
    def toterminal(self, tw):
        self.reprfileloc.toterminal(tw)
        for line in self.lines:
            red = line.startswith("E   ")
            tw.line(line, bold=True, red=red)
        return


class TestItem(pytest.Item):
    def __init__(self,
                 name: str,
                 collector: 'DotTestFile',
                 config: Config,
                 source_code: str,
                 starting_lineno: int,
                 output_lines: List[str],
                 files: Dict[str, str],
                 custom_environment: Dict[str, str]) -> None:
        super().__init__(name, collector, config)
        self.name = name
        self.source_code = source_code
        self.starting_lineno = starting_lineno
        self.expected_output_lines = output_lines
        self.root_directory = config.option.mypy_testing_base
        self.base_ini_fpath = config.option.mypy_ini_file
        self.files = files
        self.custom_environment = custom_environment

    @contextmanager
    def temp_directory(self) -> Iterator[Path]:
        with tempfile.TemporaryDirectory(prefix='mypy-pytest-',
                                         dir=self.root_directory) as tmpdir_name:
            yield Path(self.root_directory) / tmpdir_name

    def runtest(self):
        with self.temp_directory() as tmpdir_path:
            if not self.source_code:
                return

            # if self.ini_file_contents:
            #     mypy_ini_fpath = tmpdir_path / 'mypy.ini'
            #     mypy_ini_fpath.write_text(self.ini_file_contents)

            test_specific_modules = []
            for fname, contents in self.files.items():
                fpath = tmpdir_path / fname
                #
                # if create_file.make_parent_packages:
                #     fpath.parent.mkdir(parents=True, exist_ok=True)
                #     for parent in fpath.parents:
                #         try:
                #             parent.relative_to(tmpdir_path)
                #             if parent != tmpdir_path:
                #                 parent_init_file = parent / '__init__.py'
                #                 parent_init_file.write_text('')
                #                 test_specific_modules.append(fname_to_module(parent,
                #                                                              root_path=tmpdir_path))
                #         except ValueError:
                #             break

                fpath.write_text(contents)
                test_specific_modules.append(fname_to_module(fpath,
                                                             root_path=tmpdir_path))

            with utils.temp_environ(), utils.temp_path():
                for key, val in (self.custom_environment or {}).items():
                    os.environ[key] = val
                sys.path.insert(0, str(tmpdir_path))

                mypy_cmd_options = self.prepare_mypy_cmd_options()
                main_fpath = tmpdir_path / 'main.py'
                main_fpath.write_text(self.source_code)
                mypy_cmd_options.append(str(main_fpath))

                stdout, stderr, returncode = mypy_api.run(mypy_cmd_options)
                output_lines = []
                for line in (stdout + stderr).splitlines():
                    if ':' not in line:
                        continue
                    out_fpath, res_line = line.split(':', 1)
                    line = os.path.relpath(out_fpath, start=tmpdir_path) + ':' + res_line
                    output_lines.append(line.strip().replace('.py', ''))

                for module in test_specific_modules:
                    parts = module.split('.')
                    for i in range(len(parts)):
                        parent_module = '.'.join(parts[:i + 1])
                        if parent_module in sys.modules:
                            del sys.modules[parent_module]

                assert_string_arrays_equal(expected=self.expected_output_lines,
                                           actual=output_lines)

    def prepare_mypy_cmd_options(self) -> List[str]:
        mypy_cmd_options = [
            '--raise-exceptions',
            '--no-silence-site-packages'
        ]
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
