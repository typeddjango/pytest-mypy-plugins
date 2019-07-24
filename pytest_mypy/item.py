import importlib
import os
import subprocess
import sys
import tempfile
from configparser import ConfigParser
from pathlib import Path
from typing import Any, Dict, List, Tuple, Callable, Optional

import capturer
import pytest
from _pytest._code import ExceptionInfo
from _pytest._code.code import ReprEntry, ReprFileLocation
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


def run_mypy_typechecking(cmd_options: List[str]) -> int:
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


class YamlTestItem(pytest.Item):
    def __init__(self,
                 name: str,
                 collector: YamlTestFile,
                 config: Config,
                 files: List[File],
                 starting_lineno: int,
                 expected_output_lines: List[str],
                 environment_variables: Dict[str, Any],
                 disable_cache: bool,
                 mypy_config: str,
                 parsed_test_data: Dict[str, Any]) -> None:
        super().__init__(name, collector, config)
        self.files = files
        self.environment_variables = environment_variables
        self.disable_cache = disable_cache
        self.expected_output_lines = expected_output_lines
        self.starting_lineno = starting_lineno
        self.additional_mypy_config = mypy_config
        self.parsed_test_data = parsed_test_data
        self.same_process = self.config.option.mypy_same_process

        # config parameters
        self.root_directory = config.option.mypy_testing_base
        if config.option.mypy_ini_file:
            self.base_ini_fpath = os.path.abspath(config.option.mypy_ini_file)
        else:
            self.base_ini_fpath = None
        self.incremental_cache_dir = os.path.join(self.root_directory, '.mypy_cache')

    def make_test_file(self, file: File) -> None:
        current_directory = Path.cwd()
        fpath = current_directory / file.path
        fpath.parent.mkdir(parents=True, exist_ok=True)
        fpath.write_text(file.content)

    def make_test_files_in_current_directory(self) -> None:
        for file in self.files:
            self.make_test_file(file)

    def remove_cache_files(self, fpath_no_suffix: Path) -> None:
        cache_file = Path(self.incremental_cache_dir)
        cache_file /= '.'.join([str(part) for part in sys.version_info[:2]])
        for part in fpath_no_suffix.parts:
            cache_file /= part

        data_json_file = cache_file.with_suffix('.data.json')
        if data_json_file.exists():
            data_json_file.unlink()
        meta_json_file = cache_file.with_suffix('.meta.json')
        if meta_json_file.exists():
            meta_json_file.unlink()

        for parent_dir in cache_file.parents:
            if parent_dir.exists() and \
                    len(list(parent_dir.iterdir())) == 0 and \
                    str(self.incremental_cache_dir) in str(parent_dir):
                parent_dir.rmdir()

    def find_dependent_paths(self, path: Path) -> List[Path]:
        py_module = '.'.join(path.with_suffix('').parts)
        dependants = []
        for dirpath, _, filenames in os.walk(self.incremental_cache_dir):
            for filename in filenames:
                path = Path(dirpath) / filename
                if f'"{py_module}"' in path.read_text():
                    dependants.append(path.with_suffix('').with_suffix(''))
        return dependants

    def typecheck_in_new_subprocess(self, execution_path: Path, mypy_cmd_options: List[Any]) -> Tuple[int, Tuple[str, str]]:
        import distutils.spawn
        mypy_executable = distutils.spawn.find_executable('mypy')
        assert mypy_executable is not None

        # add current directory to path
        self.environment_variables['PYTHONPATH'] = str(execution_path)
        completed = subprocess.run([mypy_executable, *mypy_cmd_options],
                                   stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                   cwd=os.getcwd(),
                                   env=self.environment_variables)
        captured_stdout = completed.stdout.decode()
        captured_stderr = completed.stderr.decode()
        return completed.returncode, (captured_stdout, captured_stderr)

    def typecheck_in_same_process(self, execution_path: Path, mypy_cmd_options: List[Any]) -> Tuple[int, Tuple[str, str]]:
            with utils.temp_environ(), utils.temp_path(), utils.temp_sys_modules():
                # add custom environment variables
                for key, val in self.environment_variables.items():
                    os.environ[key] = val

                # add current directory to path
                sys.path.insert(0, str(execution_path))

                with capturer.CaptureOutput(merged=False) as captured_std_streams:
                    return_code = run_mypy_typechecking(mypy_cmd_options)

                stdout = captured_std_streams.stdout.get_text()
                stderr = captured_std_streams.stderr.get_text()
                return return_code, (stdout, stderr)

    def execute_extension_hook(self) -> None:
        extension_hook_fqname = self.config.option.mypy_extension_hook
        module_name, func_name = extension_hook_fqname.rsplit('.', maxsplit=1)
        module = importlib.import_module(module_name)
        extension_hook = getattr(module, func_name)
        extension_hook(self)

    def runtest(self):
        try:
            temp_dir = tempfile.TemporaryDirectory(prefix='pytest-mypy-', dir=self.root_directory)

            execution_path = Path(temp_dir.name)
            assert execution_path.exists()

            with utils.cd(execution_path):
                # extension point for derived packages
                if (hasattr(self.config.option, 'mypy_extension_hook')
                        and self.config.option.mypy_extension_hook is not None):
                    self.execute_extension_hook()

                # start from main.py
                main_file = str(execution_path / 'main.py')
                mypy_cmd_options = self.prepare_mypy_cmd_options(execution_path)
                mypy_cmd_options.append(main_file)

                # make files
                self.make_test_files_in_current_directory()

                if self.same_process:
                    returncode, (stdout, stderr) = self.typecheck_in_same_process(execution_path, mypy_cmd_options)
                else:
                    returncode, (stdout, stderr) = self.typecheck_in_new_subprocess(execution_path, mypy_cmd_options)

                mypy_output = stdout + stderr
                if returncode == ReturnCodes.FATAL_ERROR:
                    print(mypy_output, file=sys.stderr)
                    raise TypecheckAssertionError(error_message='Critical error occurred')

                output_lines = []
                for line in mypy_output.splitlines():
                    output_line = replace_fpath_with_module_name(line, rootdir=execution_path)
                    output_lines.append(output_line)
                assert_string_arrays_equal(expected=self.expected_output_lines,
                                           actual=output_lines)
        finally:
            temp_dir.cleanup()
            # remove created modules and all their dependants from cache
            if not self.disable_cache:
                for file in self.files:
                    path = Path(file.path)
                    self.remove_cache_files(path.with_suffix(''))

                    dependants = self.find_dependent_paths(path)
                    for dependant in dependants:
                        self.remove_cache_files(dependant)

        assert not os.path.exists(temp_dir.name)

    def prepare_mypy_cmd_options(self, execution_path: Path) -> List[str]:
        mypy_cmd_options = [
            '--show-traceback',
            '--no-silence-site-packages',
        ]
        if not self.disable_cache:
            mypy_cmd_options.extend([
                '--cache-dir',
                self.incremental_cache_dir
            ])

        python_version = '.'.join([str(part) for part in sys.version_info[:2]])
        mypy_cmd_options.append(f'--python-version={python_version}')

        # merge self.base_ini_fpath and self.additional_mypy_config into one file and copy to the typechecking folder
        mypy_ini_config = ConfigParser()
        if self.base_ini_fpath:
            mypy_ini_config.read(self.base_ini_fpath)
        if self.additional_mypy_config:
            additional_config = self.additional_mypy_config
            if '[mypy]' not in additional_config:
                additional_config = '[mypy]\n' + additional_config
            mypy_ini_config.read_string(additional_config)

        if mypy_ini_config.sections():
            mypy_config_file_path = execution_path / 'mypy.ini'
            with mypy_config_file_path.open('w') as f:
                mypy_ini_config.write(f)
            mypy_cmd_options.append(f'--config-file={str(mypy_config_file_path)}')

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
