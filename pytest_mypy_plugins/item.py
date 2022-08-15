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
    no_type_check,
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
    OutputMatcher,
    TypecheckAssertionError,
    assert_expected_matched_actual,
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
    rel_or_abs = os.path.expandvars(rel_or_abs)
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
        expected_output: List[OutputMatcher],
        environment_variables: Dict[str, Any],
        disable_cache: bool,
        mypy_config: str,
        parsed_test_data: Dict[str, Any],
        expect_fail: bool,
    ) -> None:
        super().__init__(name, parent, config)
        self.files = files
        self.environment_variables = environment_variables
        self.disable_cache = disable_cache
        self.expect_fail = expect_fail
        self.expected_output = expected_output
        self.starting_lineno = starting_lineno
        self.additional_mypy_config = mypy_config
        self.parsed_test_data = parsed_test_data
        self.same_process = self.config.option.mypy_same_process
        self.test_only_local_stub = self.config.option.mypy_only_local_stub

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

    def typecheck_in_new_subprocess(
        self, execution_path: Path, mypy_cmd_options: List[Any]
    ) -> Tuple[int, Tuple[str, str]]:
        import shutil

        mypy_executable = shutil.which("mypy")
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

        except (FileNotFoundError, PermissionError, NotADirectoryError) as e:

            raise TypecheckAssertionError(
                error_message=f"Testing base directory {self.root_directory} must exist and be writable"
            ) from e

        try:
            execution_path = Path(temp_dir.name)

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
                try:
                    assert_expected_matched_actual(expected=self.expected_output, actual=output_lines)
                except TypecheckAssertionError as e:
                    if not self.expect_fail:
                        raise e
                else:
                    if self.expect_fail:
                        raise TypecheckAssertionError("Expected failure, but test passed")

        finally:
            temp_dir.cleanup()
            # remove created modules
            if not self.disable_cache:
                for file in self.files:
                    path = Path(file.path)
                    self.remove_cache_files(path.with_suffix(""))

        assert not os.path.exists(temp_dir.name)

    def prepare_mypy_cmd_options(self, execution_path: Path) -> List[str]:
        mypy_cmd_options = [
            "--show-traceback",
            "--no-error-summary",
            "--no-pretty",
            "--hide-error-context",
        ]
        if not self.test_only_local_stub:
            mypy_cmd_options.append("--no-silence-site-packages")
        if not self.disable_cache:
            mypy_cmd_options.extend(["--cache-dir", self.incremental_cache_dir])

        # Merge `self.base_ini_fpath` and `self.additional_mypy_config`
        # into one file and copy to the typechecking folder:
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

    @no_type_check
    def reportinfo(self) -> Tuple[Union[py.path.local, Path, str], Optional[int], str]:
        # To support both Pytest 6.x and 7.x
        path = getattr(self, "path", None) or getattr(self, "fspath")
        return path, None, self.name

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
            python_path_parts.append(maybe_to_abspath(python_path_key, rootdir))
            python_path_parts.append(python_path_key)

        self.environment_variables["PYTHONPATH"] = ":".join(python_path_parts)

    def _collect_mypy_path(self, rootdir: Optional[Path]) -> None:
        mypy_path_parts = []

        existing_mypy_path = os.environ.get("MYPYPATH")
        if existing_mypy_path:
            mypy_path_parts.append(existing_mypy_path)
        mypy_path_key = self.environment_variables.get("MYPYPATH")
        if mypy_path_key:
            mypy_path_parts.append(maybe_to_abspath(mypy_path_key, rootdir))
            mypy_path_parts.append(mypy_path_key)

        self.environment_variables["MYPYPATH"] = ":".join(mypy_path_parts)
