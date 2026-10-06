"""Immutable, normalized schema-v1 values produced by validation."""

from dataclasses import asdict, dataclass

from .composition import Composition
from .content import WordSearchContent


@dataclass(frozen=True)
class Book:
    id: str
    title: str
    language: str
    subtitle: str | None = None
    description: str | None = None
    author: str | None = None
    imprint: str | None = None


@dataclass(frozen=True)
class Build:
    seed: int


@dataclass(frozen=True)
class Content:
    """Ordered authored items; no puzzle-specific interpretation in schema v1."""

    items: tuple[str, ...] = ()


@dataclass(frozen=True)
class Output:
    directory: str


@dataclass(frozen=True)
class Project:
    schema_version: int
    book: Book
    build: Build
    content: Content
    output: Output
    word_search: WordSearchContent | None = None
    composition: Composition | None = None

    def to_dict(self) -> dict[str, object]:
        """Return an independent, JSON/YAML-compatible source representation."""
        data = asdict(self)
        data["content"]["items"] = list(self.content.items)
        if self.word_search is None:
            del data["word_search"]
        else:
            data["word_search"] = self.word_search.to_dict()
        if self.composition is None:
            del data["composition"]
        else:
            data["composition"] = self.composition.to_dict()
        return data
