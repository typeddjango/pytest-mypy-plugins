import importlib
import os
import subprocess
import sys
import tempfile
from configparser import ConfigParser
from pathlib import Path
from typing import (
    TYPE_CHECKING,
    Any,
    Callable,
    Dict,
    List,
    Optional,
    Tuple,
    Union,
)

import py
import pytest
from _pytest._code import ExceptionInfo
from _pytest._code.code import ReprEntry, ReprFileLocation, TerminalRepr
from _pytest._io import TerminalWriter
from _pytest.config import Config
from mypy import build
from mypy.fscache import FileSystemCache
from mypy.main import process_options

if TYPE_CHECKING:
    from _pytest._code.code import _TracebackStyle

from pytest_mypy_plugins import utils
from pytest_mypy_plugins.collect import File, YamlTestFile
from pytest_mypy_plugins.utils import (
    TypecheckAssertionError,
    assert_string_arrays_equal,
    capture_std_streams,
    fname_to_module,
)


class TraceLastReprEntry(ReprEntry):
    def toterminal(self, tw: TerminalWriter) -> None:
        if not self.reprfileloc:
            return

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
    if ":" not in line:
        return line
    out_fpath, res_line = line.split(":", 1)
    line = os.path.relpath(out_fpath, start=rootdir) + ":" + res_line
    return line.strip().replace(".py:", ":")


def maybe_to_abspath(rel_or_abs: str, rootdir: Optional[Path]) -> str:
    if rootdir is None or os.path.isabs(rel_or_abs):
        return rel_or_abs
    return str(rootdir / rel_or_abs)


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
                f.write(msg + "\n")
            f.flush()
        except BrokenPipeError:
            sys.exit(ReturnCodes.FATAL_ERROR)

    try:
        build.build(sources, options, flush_errors=flush_errors, fscache=fscache)

    except SystemExit as sysexit:
        return sysexit.code
    finally:
        fscache.flush()

    if error_messages:
        return ReturnCodes.FAIL

    return ReturnCodes.SUCCESS


class YamlTestItem(pytest.Item):
    def __init__(
        self,
        name: str,
        parent: Optional[YamlTestFile] = None,
        config: Optional[Config] = None,
        *,
        files: List[File],
        starting_lineno: int,
        expected_output_lines: List[str],
        environment_variables: Dict[str, Any],
        disable_cache: bool,
        mypy_config: str,
        parsed_test_data: Dict[str, Any],
    ) -> None:
        super().__init__(name, parent, config)
        self.files = files
        self.environment_variables = environment_variables
        self.disable_cache = disable_cache
        self.expected_output_lines = expected_output_lines
        self.starting_lineno = starting_lineno
        self.additional_mypy_config = mypy_config
        self.parsed_test_data = parsed_test_data
        self.same_process = self.config.option.mypy_same_process

        # config parameters
        self.root_directory = self.config.option.mypy_testing_base
        if self.config.option.mypy_ini_file:
            self.base_ini_fpath = os.path.abspath(self.config.option.mypy_ini_file)
        else:
            self.base_ini_fpath = None
        self.incremental_cache_dir = os.path.join(self.root_directory, ".mypy_cache")

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
        cache_file /= ".".join([str(part) for part in sys.version_info[:2]])
        for part in fpath_no_suffix.parts:
            cache_file /= part

        data_json_file = cache_file.with_suffix(".data.json")
        if data_json_file.exists():
            data_json_file.unlink()
        meta_json_file = cache_file.with_suffix(".meta.json")
        if meta_json_file.exists():
            meta_json_file.unlink()

        for parent_dir in cache_file.parents:
            if (
                parent_dir.exists()
                and len(list(parent_dir.iterdir())) == 0
                and str(self.incremental_cache_dir) in str(parent_dir)
            ):
                parent_dir.rmdir()

    def find_dependent_paths(self, path: Path) -> List[Path]:
        py_module = ".".join(path.with_suffix("").parts)
        dependants = []
        for dirpath, _, filenames in os.walk(self.incremental_cache_dir):
            for filename in filenames:
                path = Path(dirpath) / filename
                if f'"{py_module}"' in path.read_text():
                    dependants.append(path.with_suffix("").with_suffix(""))
        return dependants

    def typecheck_in_new_subprocess(
        self, execution_path: Path, mypy_cmd_options: List[Any]
    ) -> Tuple[int, Tuple[str, str]]:
        import distutils.spawn

        mypy_executable = distutils.spawn.find_executable("mypy")
        assert mypy_executable is not None, "mypy executable is not found"

        rootdir = getattr(getattr(self.parent, "config", None), "rootdir", None)
        # add current directory to path
        self._collect_python_path(rootdir, execution_path)
        # adding proper MYPYPATH variable
        self._collect_mypy_path(rootdir)

        # Windows requires this to be set, otherwise the interpreter crashes
        if "SYSTEMROOT" in os.environ:
            self.environment_variables["SYSTEMROOT"] = os.environ["SYSTEMROOT"]

        completed = subprocess.run(
            [mypy_executable, *mypy_cmd_options],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            cwd=os.getcwd(),
            env=self.environment_variables,
        )
        captured_stdout = completed.stdout.decode()
        captured_stderr = completed.stderr.decode()
        return completed.returncode, (captured_stdout, captured_stderr)

    def typecheck_in_same_process(
        self, execution_path: Path, mypy_cmd_options: List[Any]
    ) -> Tuple[int, Tuple[str, str]]:
        with utils.temp_environ(), utils.temp_path(), utils.temp_sys_modules():
            # add custom environment variables
            for key, val in self.environment_variables.items():
                os.environ[key] = val

            # add current directory to path
            sys.path.insert(0, str(execution_path))

            with capture_std_streams() as (stdout, stderr):
                return_code = run_mypy_typechecking(mypy_cmd_options)

            return return_code, (stdout.getvalue(), stderr.getvalue())

    def execute_extension_hook(self) -> None:
        extension_hook_fqname = self.config.option.mypy_extension_hook
        module_name, func_name = extension_hook_fqname.rsplit(".", maxsplit=1)
        module = importlib.import_module(module_name)
        extension_hook = getattr(module, func_name)
        extension_hook(self)

    def runtest(self) -> None:
        try:
            temp_dir = tempfile.TemporaryDirectory(prefix="pytest-mypy-", dir=self.root_directory)

            execution_path = Path(temp_dir.name)
            assert execution_path.exists()

            with utils.cd(execution_path):
                # extension point for derived packages
                if (
                    hasattr(self.config.option, "mypy_extension_hook")
                    and self.config.option.mypy_extension_hook is not None
                ):
                    self.execute_extension_hook()

                # start from main.py
                main_file = str(execution_path / "main.py")
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
                    raise TypecheckAssertionError(error_message="Critical error occurred")

                output_lines = []
                for line in mypy_output.splitlines():
                    output_line = replace_fpath_with_module_name(line, rootdir=execution_path)
                    output_lines.append(output_line)
                assert_string_arrays_equal(expected=self.expected_output_lines, actual=output_lines)
        finally:
            temp_dir.cleanup()
            # remove created modules and all their dependants from cache
            if not self.disable_cache:
                for file in self.files:
                    path = Path(file.path)
                    self.remove_cache_files(path.with_suffix(""))

                    dependants = self.find_dependent_paths(path)
                    for dependant in dependants:
                        self.remove_cache_files(dependant)

        assert not os.path.exists(temp_dir.name)

    def prepare_mypy_cmd_options(self, execution_path: Path) -> List[str]:
        mypy_cmd_options = [
            "--show-traceback",
            "--no-silence-site-packages",
            "--no-error-summary",
            "--no-pretty",
            "--hide-error-context",
        ]
        if not self.disable_cache:
            mypy_cmd_options.extend(["--cache-dir", self.incremental_cache_dir])

        python_version = ".".join([str(part) for part in sys.version_info[:2]])
        mypy_cmd_options.append(f"--python-version={python_version}")

        # merge self.base_ini_fpath and self.additional_mypy_config into one file and copy to the typechecking folder
        mypy_ini_config = ConfigParser()
        if self.base_ini_fpath:
            mypy_ini_config.read(self.base_ini_fpath)
        if self.additional_mypy_config:
            additional_config = self.additional_mypy_config
            if "[mypy]" not in additional_config:
                additional_config = "[mypy]\n" + additional_config
            mypy_ini_config.read_string(additional_config)

        if mypy_ini_config.sections():
            mypy_config_file_path = execution_path / "mypy.ini"
            with mypy_config_file_path.open("w") as f:
                mypy_ini_config.write(f)
            mypy_cmd_options.append(f"--config-file={str(mypy_config_file_path)}")

        return mypy_cmd_options

    def repr_failure(
        self, excinfo: ExceptionInfo[BaseException], style: Optional["_TracebackStyle"] = None
    ) -> Union[str, TerminalRepr]:
        if excinfo.errisinstance(SystemExit):
            # We assume that before doing exit() (which raises SystemExit) we've printed
            # enough context about what happened so that a stack trace is not useful.
            # In particular, uncaught exceptions during semantic analysis or type checking
            # call exit() and they already print out a stack trace.
            return excinfo.exconly(tryshort=True)
        elif excinfo.errisinstance(TypecheckAssertionError):
            # with traceback removed
            exception_repr = excinfo.getrepr(style="short")
            exception_repr.reprcrash.message = ""  # type: ignore
            repr_file_location = ReprFileLocation(
                path=self.fspath, lineno=self.starting_lineno + excinfo.value.lineno, message=""  # type: ignore
            )
            repr_tb_entry = TraceLastReprEntry(
                exception_repr.reprtraceback.reprentries[-1].lines[1:], None, None, repr_file_location, "short"
            )
            exception_repr.reprtraceback.reprentries = [repr_tb_entry]
            return exception_repr
        else:
            return super().repr_failure(excinfo, style="native")

    def reportinfo(self) -> Tuple[Union[py.path.local, str], Optional[int], str]:
        return self.fspath, None, self.name

    def _collect_python_path(
        self,
        rootdir: Optional[Path],
        execution_path: Path,
    ) -> None:
        python_path_parts = []

        existing_python_path = os.environ.get("PYTHONPATH")
        if existing_python_path:
            python_path_parts.append(existing_python_path)
        if execution_path:
            python_path_parts.append(str(execution_path))
        python_path_key = self.environment_variables.get("PYTHONPATH")
        if python_path_key:
            python_path_parts.append(
                maybe_to_abspath(python_path_key, rootdir),
            )

        self.environment_variables["PYTHONPATH"] = ":".join(python_path_parts)

    def _collect_mypy_path(self, rootdir: Optional[Path]) -> None:
        mypy_path_parts = []

        existing_mypy_path = os.environ.get("MYPYPATH")
        if existing_mypy_path:
            mypy_path_parts.append(existing_mypy_path)
        if self.base_ini_fpath:
            mypy_path_parts.append(os.path.dirname(self.base_ini_fpath))
        mypy_path_key = self.environment_variables.get("MYPYPATH")
        if mypy_path_key:
            mypy_path_parts.append(
                maybe_to_abspath(mypy_path_key, rootdir),
            )

        self.environment_variables["MYPYPATH"] = ":".join(mypy_path_parts)
