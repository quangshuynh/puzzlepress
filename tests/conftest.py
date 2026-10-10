import hashlib
from pathlib import Path

import pytest

from puzzlepress import load_project
from tests.helpers import CANONICAL_BOOKS, LEGACY_FIXTURE, ROOT


@pytest.fixture
def example_path() -> Path:
    """The minimal schema-v1 source fixture (formerly books/automotive/book.yaml)."""
    return LEGACY_FIXTURE / "book.yaml"


@pytest.fixture
def source(example_path: Path) -> str:
    return example_path.read_text(encoding="utf-8")


@pytest.fixture
def garden():
    return load_project(Path(__file__).resolve().parents[1] / "books/garden-demo").project


def _fixture_digests() -> dict[str, str]:
    """Every authored file of the canonical books and the legacy fixture."""
    roots = [ROOT / "books" / name for name in CANONICAL_BOOKS] + [LEGACY_FIXTURE]
    return {
        path.relative_to(ROOT).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for root in roots
        for path in sorted(root.rglob("*"))
        if path.is_file()
    }


@pytest.fixture(scope="session", autouse=True)
def canonical_fixtures_unchanged():
    """Every test writes to temporary copies; authored fixtures stay byte-identical."""
    before = _fixture_digests()
    yield
    assert _fixture_digests() == before
