import subprocess
from pathlib import Path
from typing import Final

import pytest

_PYPROJECT1: Final = str(
    Path(__file__).parent / "test_configs" / "pyproject1.toml"
)
_PYPROJECT2: Final = str(
    Path(__file__).parent / "test_configs" / "pyproject2.toml"
)
_MYPYINI1: Final = str(Path(__file__).parent / "test_configs" / "mypy1.ini")
_MYPYINI2: Final = str(Path(__file__).parent / "test_configs" / "mypy2.ini")
_SETUPCFG1: Final = str(Path(__file__).parent / "test_configs" / "setup1.cfg")
_SETUPCFG2: Final = str(Path(__file__).parent / "test_configs" / "setup2.cfg")

_TEST_FILE: Final = str(Path(__file__).parent / "test-mypy-config.yml")


@pytest.mark.parametrize("config_file", [_PYPROJECT1, _PYPROJECT2])
def test_pyproject_toml(config_file: str) -> None:
    subprocess.check_output(
        [
            "pytest",
            "--mypy-pyproject-toml-file",
            config_file,
            _TEST_FILE,
        ]
    )


@pytest.mark.parametrize(
    "config_file",
    [
        _MYPYINI1,
        _MYPYINI2,
        _SETUPCFG1,
        _SETUPCFG2,
    ],
)
def test_ini_files(config_file: str) -> None:
    subprocess.check_output(
        [
            "pytest",
            "--mypy-ini-file",
            config_file,
            _TEST_FILE,
        ]
    )


@pytest.fixture(scope="module")
def shared_testing_base(tmp_path_factory: pytest.TempPathFactory) -> Path:
    return tmp_path_factory.mktemp("mypy_cfg_dir_base")


@pytest.mark.parametrize("same_process", [False, True])
@pytest.mark.parametrize("config_kind", ["ini", "toml_str", "toml_list"])
def test_mypy_config_file_dir_resolution(
    tmp_path: Path,
    shared_testing_base: Path,
    same_process: bool,
    config_kind: str,
) -> None:
    cfg_dir = tmp_path / "project"
    stubs_a = cfg_dir / "stubs_a"
    stubs_b = cfg_dir / "stubs_b"
    stubs_a.mkdir(parents=True)
    stubs_b.mkdir(parents=True)

    mod_a = f"stub_{config_kind}_{int(same_process)}_a"
    mod_b = f"stub_{config_kind}_{int(same_process)}_b"
    (stubs_a / f"{mod_a}.pyi").write_text(
        "def greet() -> str: ...\n", encoding="utf-8"
    )
    (stubs_b / f"{mod_b}.pyi").write_text("VALUE: int\n", encoding="utf-8")

    yaml_test = cfg_dir / "test_config_dir.yml"
    yaml_test.write_text(
        "- case: resolves_mypy_config_file_dir\n"
        "  main: |\n"
        f"    import {mod_a}\n"
        f"    import {mod_b}\n"
        f"    x: str = {mod_a}.greet()\n"
        f"    y: int = {mod_b}.VALUE\n"
        f"    bad: int = {mod_a}.greet()  # E: Incompatible types in assignment "
        '(expression has type "str", variable has type "int")  [assignment]\n',
        encoding="utf-8",
    )

    cmd = [
        "pytest",
        "-o",
        "addopts=",
        f"--mypy-testing-base={shared_testing_base}",
        f"--rootdir={cfg_dir}",
    ]
    if same_process:
        cmd.append("--mypy-same-process")

    if config_kind == "ini":
        ini_path = cfg_dir / "mypy.ini"
        ini_path.write_text(
            "[mypy]\n"
            "mypy_path = $MYPY_CONFIG_FILE_DIR/stubs_a:${MYPY_CONFIG_FILE_DIR}/stubs_b\n",
            encoding="utf-8",
        )
        cmd.extend(["--mypy-ini-file", str(ini_path)])
    elif config_kind == "toml_str":
        toml_path = cfg_dir / "pyproject.toml"
        toml_path.write_text(
            "[tool.mypy]\n"
            'mypy_path = "$MYPY_CONFIG_FILE_DIR/stubs_a:${MYPY_CONFIG_FILE_DIR}/stubs_b"\n',
            encoding="utf-8",
        )
        cmd.extend(["--mypy-pyproject-toml-file", str(toml_path)])
    else:
        toml_path = cfg_dir / "pyproject.toml"
        toml_path.write_text(
            "[tool.mypy]\n"
            'mypy_path = ["$MYPY_CONFIG_FILE_DIR/stubs_a", "${MYPY_CONFIG_FILE_DIR}/stubs_b"]\n',
            encoding="utf-8",
        )
        cmd.extend(["--mypy-pyproject-toml-file", str(toml_path)])

    cmd.append(str(yaml_test))
    subprocess.check_output(cmd, cwd=cfg_dir)
