from pathlib import Path

import pytest


@pytest.fixture
def example_path() -> Path:
    return Path(__file__).resolve().parents[1] / "books" / "automotive" / "book.yaml"


@pytest.fixture
def source(example_path: Path) -> str:
    return example_path.read_text(encoding="utf-8")
