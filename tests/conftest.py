import hashlib
from pathlib import Path

import pytest

from puzzlepress import load_project
from tests.helpers import CANONICAL_BOOKS, ROOT


@pytest.fixture
def example_path() -> Path:
    return Path(__file__).resolve().parents[1] / "books" / "automotive" / "book.yaml"


@pytest.fixture
def source(example_path: Path) -> str:
    return example_path.read_text(encoding="utf-8")


@pytest.fixture
def garden():
    return load_project(Path(__file__).resolve().parents[1] / "books/garden-demo").project


def _fixture_digests() -> dict[str, str]:
    """Every authored file of the canonical books, including cover photographs."""
    return {
        path.relative_to(ROOT).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for name in CANONICAL_BOOKS
        for path in sorted((ROOT / "books" / name).rglob("*"))
        if path.is_file()
    }


@pytest.fixture(scope="session", autouse=True)
def canonical_fixtures_unchanged():
    """Every test writes to temporary copies; authored fixtures stay byte-identical."""
    before = _fixture_digests()
    yield
    assert _fixture_digests() == before
