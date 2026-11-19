import os
from configparser import ConfigParser
from pathlib import Path

from pytest_mypy_plugins.configs import join_ini_configs


def test_join_ini_expands_mypy_config_file_dir(tmp_path: Path) -> None:
    config_dir = tmp_path / "project"
    execution_path = tmp_path / "exec"
    config_dir.mkdir()
    execution_path.mkdir()

    ini_file = config_dir / "setup.cfg"
    ini_file.write_text(
        "[flake8]\n"
        "format = %(path)s:%(row)d\n\n"
        "[mypy]\n"
        "mypy_path = $MYPY_CONFIG_FILE_DIR/stubs_a:${MYPY_CONFIG_FILE_DIR}/stubs_b\n"
        "custom_typeshed_dir = $MYPY_CONFIG_FILE_DIR/typeshed\n"
        "cache_dir = ${MYPY_CONFIG_FILE_DIR}/.mypy_cache\n"
        "junit_xml = $MYPY_CONFIG_FILE_DIR_EXTRA/report.xml\n\n"
        "[mypy-pkg.*]\n"
        "custom_typing_module = $OTHER_ENV/typing_mod\n",
        encoding="utf-8",
    )

    joined = join_ini_configs(
        str(ini_file),
        "warn_unused_ignores = True\n"
        "python_executable = $MYPY_CONFIG_FILE_DIR/bin/python\n",
        execution_path,
    )
    assert joined is not None

    parsed = ConfigParser(interpolation=None)
    parsed.read(joined, encoding="utf-8")

    expected_dir = os.path.dirname(os.path.abspath(ini_file))
    assert (
        parsed.get("mypy", "custom_typeshed_dir") == f"{expected_dir}/typeshed"
    )
    assert parsed.get("mypy", "cache_dir") == f"{expected_dir}/.mypy_cache"
    assert (
        parsed.get("mypy", "junit_xml")
        == "$MYPY_CONFIG_FILE_DIR_EXTRA/report.xml"
    )
    assert parsed.get("mypy", "warn_unused_ignores") == "True"
    assert (
        parsed.get("mypy", "python_executable")
        == "$MYPY_CONFIG_FILE_DIR/bin/python"
    )
    assert (
        parsed.get("mypy-pkg.*", "custom_typing_module")
        == "$OTHER_ENV/typing_mod"
    )

    mypy_path_val = parsed.get("mypy", "mypy_path")
    if ":" in expected_dir:
        rel = Path(
            os.path.relpath(expected_dir, os.path.abspath(execution_path))
        ).as_posix()
        expected_prefix = f"$MYPY_CONFIG_FILE_DIR/{rel}"
    else:
        expected_prefix = expected_dir
    assert (
        mypy_path_val == f"{expected_prefix}/stubs_a:{expected_prefix}/stubs_b"
    )
