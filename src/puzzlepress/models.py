"""Immutable, normalized schema-v1 values produced by validation."""

from dataclasses import asdict, dataclass


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

    def to_dict(self) -> dict[str, object]:
        """Return an independent, JSON/YAML-compatible source representation."""
        data = asdict(self)
        data["content"]["items"] = list(self.content.items)
        return data
