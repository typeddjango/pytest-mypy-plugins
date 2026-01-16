import subprocess
from collections.abc import Generator
from pathlib import Path
from sys import version_info
from tempfile import TemporaryDirectory

import pytest


def test_non_test_case_files_remain(temp_dir: Path) -> None:
    """
    Tests that cache files not associated with ``files`` in a test case do not get removed.

    Assumes that cache files will be generated for typeshed's ``builtins.pyi`` when running any test case.
    """

    cache_dir = temp_dir / ".mypy_cache" / f"{version_info[0]}.{version_info[1]}"
    # pytest and mypy hasn't been run yet, so no cache should exist
    assert not cache_dir.is_dir()

    make_yaml_test_file(
        temp_dir,
        """
- case: test_non_test_case_files_cache_files_remain
  main: |
        """,
    )
    res = subprocess.run(
        ["pytest", f"--mypy-testing-base={temp_dir}"], cwd=temp_dir, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT
    )

    # pytest was invoked correctly and there are no failures unrelated to tests
    assert res.returncode in (pytest.ExitCode.OK, pytest.ExitCode.TESTS_FAILED)
    # Cache files should not be deleted
    assert get_created_cache_files(cache_dir, ("builtins",))


CACHE_FILES_REMOVED_TEST_DATA = {
    "single_module_distribution": (
        """
- case: single_module_distribution
  main: |
    import my_mod
  files:
    - path: my_mod.py
        """,
        ("my_mod",),
    ),
    "standard_package": (
        """
- case: standard_package
  main: |
    import my_pkg.my_mod
    import my_pkg.my_subpkg.my_mod
  files:
    - path: my_pkg/__init__.py
    - path: my_pkg/my_mod.py
    - path: my_pkg/my_subpkg/__init__.py
    - path: my_pkg/my_subpkg/my_mod.py
        """,
        ("my_pkg/__init__", "my_pkg/my_mod", "my_pkg/my_subpkg/__init__", "my_pkg/my_subpkg/my_mod"),
    ),
    "namespace_package": (
        """
- case: namespace_package
  main: |
    import my_nspkg.my_mod
    import my_nspkg.my_nssubpkg.my_mod
  files:
    - path: my_nspkg/my_mod.py
    - path: my_nspkg/my_nssubpkg/my_mod.py
        """,
        ("my_nspkg", "my_nspkg/my_mod", "my_nspkg/my_nssubpkg", "my_nspkg/my_nssubpkg/my_mod"),
    ),
    "standard_stub_package": (
        """
- case: standard_stub_package
  main: |
    import my_pkg.my_mod
    import my_pkg.my_subpkg.my_mod
  files:
    - path: my_pkg-stubs/__init__.pyi
    - path: my_pkg-stubs/my_mod.pyi
    - path: my_pkg-stubs/my_subpkg/__init__.pyi
    - path: my_pkg-stubs/my_subpkg/my_mod.pyi
        """,
        ("my_pkg/__init__", "my_pkg/my_mod", "my_pkg/my_subpkg/__init__", "my_pkg/my_subpkg/my_mod"),
    ),
    "namespace_stub_package": (
        """
- case: namespace_stub_package
  main: |
    import my_nspkg.my_mod
    import my_nspkg.my_nssubpkg.my_mod
  files:
    - path: my_nspkg-stubs/my_mod.pyi
    - path: my_nspkg-stubs/my_nssubpkg/my_mod.pyi
        """,
        ("my_nspkg", "my_nspkg/my_mod", "my_nspkg/my_nssubpkg", "my_nspkg/my_nssubpkg/my_mod"),
    ),
    "mixed_modules_and_packages": (
        """
- case: mixed_modules_and_packages
  main: |
    import my_mod
    import my_pkg.my_submod
    import my_pkg.my_nssubpkg.my_submod
    import my_nspkg.my_submod
    import my_nspkg.my_subpkg
    import my_stubpkg.my_submod
    import my_stubpkg.my_subpkg.my_submod
    import my_nsstubpkg.my_subpkg
  files:
  - path: my_mod.py
  - path: my_pkg/__init__.py
  - path: my_pkg/my_submod.pyi
  - path: my_pkg/my_nssubpkg/my_submod.pyi
  - path: my_nspkg/my_submod.pyi
  - path: my_nspkg/my_subpkg/__init__.py
  - path: my_stubpkg-stubs/__init__.pyi
  - path: my_stubpkg-stubs/my_submod.pyi
  - path: my_stubpkg-stubs/my_subpkg/my_submod.pyi
  - path: my_nsstubpkg-stubs/my_subpkg/__init__.pyi
        """,
        (
            "my_mod",
            "my_pkg/__init__",
            "my_pkg/my_submod",
            "my_pkg/my_nssubpkg",
            "my_pkg/my_nssubpkg/my_submod",
            "my_nspkg",
            "my_nspkg/my_submod",
            "my_nspkg/my_subpkg",
            "my_nspkg/my_subpkg/__init__",
            "my_stubpkg/__init__",
            "my_stubpkg/my_submod",
            "my_stubpkg/my_subpkg",
            "my_stubpkg/my_subpkg/my_submod",
            "my_nsstubpkg",
            "my_nsstubpkg/my_subpkg/__init__",
        ),
    ),
}


@pytest.mark.parametrize(("contents", "module_fpaths_no_suffix"), CACHE_FILES_REMOVED_TEST_DATA.values(), ids=CACHE_FILES_REMOVED_TEST_DATA.keys())
def test_cache_files_removed(temp_dir: Path, contents: str, module_fpaths_no_suffix: tuple[str, ...]) -> None:
    """Tests that cache files associated with ``files`` in a test case get removed"""

    cache_dir = temp_dir / ".mypy_cache" / f"{version_info[0]}.{version_info[1]}"
    # pytest and mypy hasn't been run yet, so no cache should exist
    assert not cache_dir.is_dir()

    make_yaml_test_file(temp_dir, contents)
    res = subprocess.run(
        ["pytest", f"--mypy-testing-base={temp_dir}"], cwd=temp_dir, stdout=subprocess.DEVNULL, stderr=subprocess.STDOUT
    )

    # pytest was invoked correctly and there are no failures unrelated to tests
    assert res.returncode in (pytest.ExitCode.OK, pytest.ExitCode.TESTS_FAILED)
    # Cache files exist but test case cache files are removed
    assert get_created_cache_files(cache_dir, ("builtins",))
    assert not get_created_cache_files(cache_dir, module_fpaths_no_suffix)


@pytest.fixture
def temp_dir() -> Generator[Path]:
    """
    Create a temporary directory to run each test case in an isolated process.

    Test files and the mypy cache is expected to be created in this temporary directory, and is deleted upon test case
    completion.
    """

    with TemporaryDirectory() as d:
        yield Path(d)


def make_yaml_test_file(
    root_dir: Path,
    contents: str,
    /,
    *,
    file_base_name: str = "test-case",
) -> str:
    path = root_dir / f"{file_base_name}.yml"
    path.write_text(contents)
    return str(path)


def get_created_cache_files(cache_dir: Path, module_rel_paths_no_suffix: tuple[str, ...]) -> list[str]:
    created = []
    for rel_path in module_rel_paths_no_suffix:
        prefix = cache_dir / rel_path
        data_file = prefix.with_suffix(".data.json")
        if data_file.exists():
            created.append(str(data_file.relative_to(cache_dir)))
        meta_file = prefix.with_suffix(".meta.json")
        if meta_file.exists():
            created.append(str(meta_file.relative_to(cache_dir)))
    return created
