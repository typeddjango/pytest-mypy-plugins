import subprocess
from pathlib import Path


def test_marks_filter_selects_only_marked_cases(tmp_path: Path) -> None:
    """`pytest -m <marker>` should collect only the cases tagged with that marker.

    The marked case is parametrized to verify the marker is applied to every
    generated variant, not just the first.
    """
    make_yaml_test_file(
        tmp_path,
        """
- case: marked_case
  marks:
    - slow
  parametrized:
    - rt: int
    - rt: str
  main: |
    reveal_type('abc')  # N: Revealed type is "str"

- case: plain_case
  main: |
    reveal_type('abc')  # N: Revealed type is "str"
        """,
    )
    # Register the marker so no `PytestUnknownMarkWarning` is emitted.
    (tmp_path / "pytest.ini").write_text("[pytest]\nmarkers =\n    slow: slow tests\n")

    res = subprocess.run(
        ["pytest", "-m", "slow", "--co", "-q", f"--mypy-testing-base={tmp_path}"],
        cwd=tmp_path,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )

    assert res.returncode == 0, res.stdout
    # Both parametrized variants of the marked case are selected...
    assert res.stdout.count("marked_case") == 2
    # ...and the unmarked case is deselected.
    assert "plain_case" not in res.stdout
    assert "1 deselected" in res.stdout


def make_yaml_test_file(root_dir: Path, contents: str, /, *, file_base_name: str = "test-case") -> str:
    path = root_dir / f"{file_base_name}.yml"
    path.write_text(contents)
    return str(path)
