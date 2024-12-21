import importlib
import io
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path
from typing import (
    TYPE_CHECKING,
    Any,
    Dict,
    List,
    Literal,
    Optional,
    TextIO,
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

from pytest_mypy_plugins import configs, utils
from pytest_mypy_plugins.collect import File, YamlTestFile
from pytest_mypy_plugins.utils import (
    OutputMatcher,
    TypecheckAssertionError,
    assert_expected_matched_actual,
    fname_to_module,
)

if TYPE_CHECKING:
    # pytest 8.3.0 renamed _TracebackStyle to TracebackStyle, but there is no syntax
    # to assert what version you have using static conditions, so it has to be
    # manually re-defined here. Once minimum supported pytest version is >= 8.3.0,
    # the following can be replaced with `from _pytest._code.code import TracebackStyle`
    TracebackStyle = Literal["long", "short", "line", "no", "native", "value", "auto"]


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


def run_mypy_typechecking(cmd_options: List[str], stdout: TextIO, stderr: TextIO) -> int:
    fscache = FileSystemCache()
    sources, options = process_options(cmd_options, fscache=fscache)

    error_messages = []

    # Different mypy versions have different arity of `flush_errors`: 2 and 3 params
    def flush_errors(*args: Any) -> None:
        new_messages: List[str]
        serious: bool
        *_, new_messages, serious = args
        error_messages.extend(new_messages)
        f = stderr if serious else stdout
        try:
            for msg in new_messages:
                f.write(msg + "\n")
            f.flush()
        except BrokenPipeError:
            sys.exit(ReturnCodes.FATAL_ERROR)

    try:
        build.build(sources, options, flush_errors=flush_errors, fscache=fscache, stdout=stdout, stderr=stderr)

    except SystemExit as sysexit:
        # The code to a SystemExit is optional
        # From python docs, if the code is None then the exit code is 0
        # Otherwise if the code is not an integer the exit code is 1
        code = sysexit.code
        if code is None:
            code = 0
        elif not isinstance(code, int):
            code = 1

        return code
    finally:
        fscache.flush()

    if error_messages:
        return ReturnCodes.FAIL

    return ReturnCodes.SUCCESS


class MypyExecutor:
    def __init__(
        self,
        same_process: bool,
        rootdir: Union[Path, None],
        execution_path: Path,
        environment_variables: Dict[str, Any],
        mypy_executable: str,
    ) -> None:
        self.rootdir = rootdir
        self.same_process = same_process
        self.execution_path = execution_path
        self.mypy_executable = mypy_executable
        self.environment_variables = environment_variables

    def execute(self, mypy_cmd_options: List[str]) -> Tuple[int, Tuple[str, str]]:
        # Returns (returncode, (stdout, stderr))
        if self.same_process:
            return self._typecheck_in_same_process(mypy_cmd_options)
        else:
            return self._typecheck_in_new_subprocess(mypy_cmd_options)

    def _typecheck_in_new_subprocess(self, mypy_cmd_options: List[Any]) -> Tuple[int, Tuple[str, str]]:
        # add current directory to path
        self._collect_python_path(self.rootdir)
        # adding proper MYPYPATH variable
        self._collect_mypy_path(self.rootdir)

        # Windows requires this to be set, otherwise the interpreter crashes
        if "SYSTEMROOT" in os.environ:
            self.environment_variables["SYSTEMROOT"] = os.environ["SYSTEMROOT"]

        completed = subprocess.run(
            [self.mypy_executable, *mypy_cmd_options],
            capture_output=True,
            cwd=os.getcwd(),
            env=self.environment_variables,
        )
        captured_stdout = completed.stdout.decode()
        captured_stderr = completed.stderr.decode()
        return completed.returncode, (captured_stdout, captured_stderr)

    def _typecheck_in_same_process(self, mypy_cmd_options: List[Any]) -> Tuple[int, Tuple[str, str]]:
        return_code = -1
        with utils.temp_environ(), utils.temp_path(), utils.temp_sys_modules():
            # add custom environment variables
            for key, val in self.environment_variables.items():
                os.environ[key] = val

            # add current directory to path
            sys.path.insert(0, str(self.execution_path))

            stdout = io.StringIO()
            stderr = io.StringIO()

            with stdout, stderr:
                return_code = run_mypy_typechecking(mypy_cmd_options, stdout=stdout, stderr=stderr)
                stdout_value = stdout.getvalue()
                stderr_value = stderr.getvalue()

            return return_code, (stdout_value, stderr_value)

    def _collect_python_path(self, rootdir: Optional[Path]) -> None:
        python_path_parts = []

        existing_python_path = os.environ.get("PYTHONPATH")
        if existing_python_path:
            python_path_parts.append(existing_python_path)
        python_path_parts.append(str(self.execution_path))
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
        if rootdir:
            mypy_path_parts.append(str(rootdir))

        self.environment_variables["MYPYPATH"] = ":".join(mypy_path_parts)


class OutputChecker:
    def __init__(self, expect_fail: bool, execution_path: Path, expected_output: List[OutputMatcher]) -> None:
        self.expect_fail = expect_fail
        self.execution_path = execution_path
        self.expected_output = expected_output

    def check(self, ret_code: int, stdout: str, stderr: str) -> None:
        mypy_output = stdout + stderr
        if ret_code == ReturnCodes.FATAL_ERROR:
            print(mypy_output, file=sys.stderr)
            raise TypecheckAssertionError(error_message="Critical error occurred")

        output_lines = []
        for line in mypy_output.splitlines():
            output_line = replace_fpath_with_module_name(line, rootdir=self.execution_path)
            output_lines.append(output_line)
        try:
            assert_expected_matched_actual(expected=self.expected_output, actual=output_lines)
        except TypecheckAssertionError as e:
            if not self.expect_fail:
                raise e
        else:
            if self.expect_fail:
                raise TypecheckAssertionError("Expected failure, but test passed")


class Runner:
    def __init__(
        self,
        *,
        files: List[File],
        config: Config,
        main_file: Path,
        config_file: Optional[str],
        disable_cache: bool,
        mypy_executor: MypyExecutor,
        output_checker: OutputChecker,
        test_only_local_stub: bool,
        incremental_cache_dir: str,
    ) -> None:
        self.files = files
        self.config = config
        self.main_file = main_file
        self.config_file = config_file
        self.mypy_executor = mypy_executor
        self.disable_cache = disable_cache
        self.output_checker = output_checker
        self.test_only_local_stub = test_only_local_stub
        self.incremental_cache_dir = incremental_cache_dir

    def run(self) -> None:
        # start from main.py
        mypy_cmd_options = self._prepare_mypy_cmd_options()
        mypy_cmd_options.append(str(self.main_file))

        # make files
        for file in self.files:
            self._make_test_file(file)

        returncode, (stdout, stderr) = self.mypy_executor.execute(mypy_cmd_options)
        self.output_checker.check(returncode, stdout, stderr)

    def _make_test_file(self, file: File) -> None:
        current_directory = Path.cwd()
        fpath = current_directory / file.path
        fpath.parent.mkdir(parents=True, exist_ok=True)
        fpath.write_text(file.content)

    def _prepare_mypy_cmd_options(self) -> List[str]:
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

        if self.config_file:
            mypy_cmd_options.append(f"--config-file={self.config_file}")

        return mypy_cmd_options


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

        # You cannot use both `.ini` and `pyproject.toml` files at the same time:
        if self.config.option.mypy_ini_file and self.config.option.mypy_pyproject_toml_file:
            raise ValueError("Cannot specify both `--mypy-ini-file` and `--mypy-pyproject-toml-file`")

        if self.config.option.mypy_ini_file:
            self.base_ini_fpath = os.path.abspath(self.config.option.mypy_ini_file)
        else:
            self.base_ini_fpath = None
        if self.config.option.mypy_pyproject_toml_file:
            self.base_pyproject_toml_fpath = os.path.abspath(self.config.option.mypy_pyproject_toml_file)
        else:
            self.base_pyproject_toml_fpath = None
        self.incremental_cache_dir = os.path.join(self.root_directory, ".mypy_cache")

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
            mypy_executable = shutil.which("mypy")
            assert mypy_executable is not None, "mypy executable is not found"
            rootdir = getattr(getattr(self.parent, "config", None), "rootdir", None)

            # extension point for derived packages
            if (
                hasattr(self.config.option, "mypy_extension_hook")
                and self.config.option.mypy_extension_hook is not None
            ):
                self.execute_extension_hook()

            execution_path = Path(temp_dir.name)
            with utils.cd(execution_path):
                mypy_executor = MypyExecutor(
                    same_process=self.same_process,
                    execution_path=execution_path,
                    rootdir=rootdir,
                    environment_variables=self.environment_variables,
                    mypy_executable=mypy_executable,
                )

                output_checker = OutputChecker(
                    expect_fail=self.expect_fail, execution_path=execution_path, expected_output=self.expected_output
                )

                Runner(
                    files=self.files,
                    config=self.config,
                    main_file=execution_path / "main.py",
                    config_file=self.prepare_config_file(execution_path),
                    disable_cache=self.disable_cache,
                    mypy_executor=mypy_executor,
                    output_checker=output_checker,
                    test_only_local_stub=self.test_only_local_stub,
                    incremental_cache_dir=self.incremental_cache_dir,
                ).run()
        finally:
            temp_dir.cleanup()
            # remove created modules
            if not self.disable_cache:
                for file in self.files:
                    path = Path(file.path)
                    self.remove_cache_files(path.with_suffix(""))

        assert not os.path.exists(temp_dir.name)

    def prepare_config_file(self, execution_path: Path) -> Optional[str]:
        # Merge (`self.base_ini_fpath` or `base_pyproject_toml_fpath`)
        # and `self.additional_mypy_config`
        # into one file and copy to the typechecking folder:
        if self.base_pyproject_toml_fpath:
            return configs.join_toml_configs(
                self.base_pyproject_toml_fpath, self.additional_mypy_config, execution_path
            )
        elif self.base_ini_fpath or self.additional_mypy_config:
            # We might have `self.base_ini_fpath` set as well.
            # Or this might be a legacy case: only `mypy_config:` is set in the `yaml` test case.
            # This means that no real file is provided.
            return configs.join_ini_configs(self.base_ini_fpath, self.additional_mypy_config, execution_path)
        return None

    def repr_failure(
        self, excinfo: ExceptionInfo[BaseException], style: Optional["TracebackStyle"] = None
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
            repr_tb_entry = ReprEntry(
                exception_repr.reprtraceback.reprentries[-1].lines[1:], None, None, repr_file_location, "short"
            )
            exception_repr.reprtraceback.reprentries = [repr_tb_entry]
            return exception_repr
        else:
            return super().repr_failure(excinfo, style="native")

    def reportinfo(self) -> Tuple[Union[Path, str], Optional[int], str]:
        return self.path, None, self.name
