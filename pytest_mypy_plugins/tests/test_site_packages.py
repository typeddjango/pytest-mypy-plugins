import os.path
import site
import subprocess
from pathlib import Path

import pytest


def test_default(tmp_path: Path) -> None:
    make_yaml_test_file(
        tmp_path,
        """
- case: test_non_test_case_files_cache_files_remain
  mypy_config: |
    strict=true
  main: |
    import subpkg

    a: str
    a / 2
  files:
    - path: subpkg.py
      content: |
        a: str
        a / 2
  out: |
    main:4: error: Unsupported operand types for / ("str" and "int")  [operator]
    subpkg:2: error: Unsupported operand types for / ("str" and "int")  [operator]
        """,
    )
    res = subprocess.run(
        [
            "pytest",
            f"--mypy-testing-base={tmp_path}",
        ],
        cwd=tmp_path,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.STDOUT,
    )
    assert res.returncode == pytest.ExitCode.OK


def test_modify_pythonpath_only(tmp_path: Path) -> None:
    make_yaml_test_file(
        tmp_path,
        """
- case: test_non_test_case_files_cache_files_remain
  mypy_config: |
    strict=true
  main: |
    import subpkg

    a: str
    a / 2
  files:
    - path: subpkg.py
      content: |
        a: str
        a / 2  # Modifying `PYTHONPATH` causes this to not raise an error as expected.
  out: |
    main:4: error: Unsupported operand types for / ("str" and "int")  [operator]
        """,
    )
    res = subprocess.run(
        [
            "pytest",
            f"--mypy-testing-base={tmp_path}",
            "--mypy-modify-pythonpath",
        ],
        cwd=tmp_path,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.STDOUT,
    )
    assert res.returncode == pytest.ExitCode.OK


def test_no_silence_site_packages_only(tmp_path: Path) -> None:
    make_yaml_test_file(
        tmp_path,
        """
- case: test_non_test_case_files_cache_files_remain
  mypy_config: |
    strict=true
  main: |
    import subpkg

    a: str
    a / 2
  files:
    - path: subpkg.py
      content: |
        a: str
        a / 2
  out: |
    {site_packages_path}/mypy/typeshed/stdlib/types.pyi:716: error: Class cannot subclass "Any" (has type "Any")  [misc]
    main:4: error: Unsupported operand types for / ("str" and "int")  [operator]
    subpkg:2: error: Unsupported operand types for / ("str" and "int")  [operator]
        """,
    )
    res = subprocess.run(
        [
            "pytest",
            f"--mypy-testing-base={tmp_path}",
            "--mypy-no-silence-site-packages",
        ],
        cwd=tmp_path,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.STDOUT,
    )
    assert res.returncode == pytest.ExitCode.OK


def test_no_silence_site_packages_and_modify_pythonpath(tmp_path: Path) -> None:
    make_yaml_test_file(
        tmp_path,
        """
- case: test_non_test_case_files_cache_files_remain
  mypy_config: |
    strict=true
  main: |
    import subpkg

    a: str
    a / 2
  files:
    - path: subpkg.py
      content: |
        a: str
        a / 2
  out: |
    {site_packages_path}/mypy/typeshed/stdlib/types.pyi:716: error: Class cannot subclass "Any" (has type "Any")  [misc]
    main:4: error: Unsupported operand types for / ("str" and "int")  [operator]
    subpkg:2: error: Unsupported operand types for / ("str" and "int")  [operator]
        """,
    )
    res = subprocess.run(
        [
            "pytest",
            f"--mypy-testing-base={tmp_path}",
            "--mypy-no-silence-site-packages",
            "--mypy-modify-pythonpath",
        ],
        cwd=tmp_path,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.STDOUT,
    )
    assert res.returncode == pytest.ExitCode.OK


def make_yaml_test_file(
    root_dir: Path,
    contents: str,
    /,
    *,
    file_base_name: str = "test-case",
) -> None:
    output_path = root_dir.joinpath(file_base_name).with_suffix(".yml")
    site_packages_path: Path | str = Path(site.getsitepackages()[0])
    site_packages_path = os.path.relpath(site_packages_path, start=output_path)
    contents = contents.format(site_packages_path=site_packages_path)
    output_path.write_text(contents)
