import subprocess
import sys
from pathlib import Path

import pytest

from puzzlepress import __version__, build_identity, load_project
from puzzlepress.cli import main


def run_cli(*args):
    return subprocess.run(
        [sys.executable, "-m", "puzzlepress", *map(str, args)],
        capture_output=True,
        text=True,
        check=False,
    )


def test_version():
    result = run_cli("--version")
    assert result.returncode == 0
    assert result.stdout.strip() == f"PuzzlePress {__version__}"
    assert not result.stderr


def test_validate_and_inspect(example_path):
    result = run_cli("validate", example_path.parent)
    assert result.returncode == 0
    assert "Valid: automotive-word-search" in result.stdout
    assert not result.stderr
    result = run_cli("inspect", example_path)
    assert result.returncode == 0
    for expected in (
        "Title: Automotive Word Search",
        "Seed: 2026",
        "Schema version: 1",
        str(example_path),
        build_identity(load_project(example_path).project),
    ):
        assert expected in result.stdout


@pytest.mark.parametrize(
    "source", ["book: [", "schema_version: 7", "schema_version: 1\nbook: {}\nbuild: {}"]
)
def test_configuration_failure_exit_code_and_no_traceback(tmp_path, source):
    path = tmp_path / "book.yaml"
    path.write_text(source, encoding="utf-8")
    result = run_cli("validate", path)
    assert result.returncode == 1
    assert result.stderr
    assert not result.stdout
    assert "Traceback" not in result.stderr


def test_missing_path(tmp_path):
    result = run_cli("inspect", tmp_path / "missing")
    assert result.returncode == 1
    assert "[not_found]" in result.stderr


def test_cli_rejects_source_output_overlap(source, tmp_path):
    path = tmp_path / "book.yaml"
    path.write_text(source.replace("../../build/automotive-word-search", "."), encoding="utf-8")
    before = path.read_bytes()
    result = run_cli("validate", path)
    assert result.returncode == 1
    assert "[source_overlap]" in result.stderr
    assert path.read_bytes() == before


@pytest.mark.parametrize("args", [(), ("build",), ("inspect",)])
def test_usage_failure(args):
    result = run_cli(*args)
    assert result.returncode == 2
    assert "usage:" in result.stderr


def test_installed_console_script(example_path):
    script = Path(sys.executable).parent / (
        "puzzlepress.exe" if sys.platform == "win32" else "puzzlepress"
    )
    result = subprocess.run(
        [str(script), "validate", str(example_path)], capture_output=True, text=True, check=False
    )
    assert result.returncode == 0
    assert "Valid:" in result.stdout


def test_unexpected_programmer_error_is_not_misreported(monkeypatch):
    def broken_loader(path):
        raise RuntimeError("internal defect")

    monkeypatch.setattr("puzzlepress.cli.load_project", broken_loader)
    with pytest.raises(RuntimeError, match="internal defect"):
        main(["validate", "anything"])
