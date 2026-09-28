from pathlib import Path

import pytest

from puzzlepress import load_project


@pytest.fixture
def example_path() -> Path:
    return Path(__file__).resolve().parents[1] / "books" / "automotive" / "book.yaml"


@pytest.fixture
def source(example_path: Path) -> str:
    return example_path.read_text(encoding="utf-8")


@pytest.fixture
def garden():
    return load_project(Path(__file__).resolve().parents[1] / "books/garden-demo").project
