"""Authored KDP paperback publishing metadata: an optional, versioned section.

Title, subtitle, author, imprint and language stay authoritative in `book`; this
section holds only what KDP asks for beyond them, plus the author's own
disclosure and review decisions. It is excluded from the project build identity
(editing keywords never stales an interior) and identified by the publishing
identity instead. Undecided values are explicit (`None`, `undecided`, `unknown`)
and never default to a claim on the author's behalf.
"""

from dataclasses import dataclass, field
from enum import StrEnum

PUBLISHING_VERSION = 1

# Generous schema bounds keep a draft savable; KDP limits are reported by
# publishing validation with their official source (docs/publishing.md).
MAX_DESCRIPTION = 10_000
MAX_KEYWORDS = 20
MAX_KEYWORD = 200
MAX_CATEGORIES = 10
MAX_CATEGORY = 300
MAX_CONTRIBUTORS = 20
MAX_NAME = 200
MAX_NOTES = 2_000
MAX_EDITION = 999
MAX_SERIES_NUMBER = 9_999
MAX_READING_AGE = 18  # 18 stands for "18 and over".


class IsbnMode(StrEnum):
    UNDECIDED = "undecided"
    KDP_FREE = "kdp_free"  # KDP assigns a free ISBN during setup; usable only on KDP.
    OWN = "own"  # An ISBN the author registered with an ISBN agency.
    NONE = "none"  # Only low-content books may publish without an ISBN.


class ContentOrigin(StrEnum):
    """Who or what created a kind of content, as the author declares it."""

    UNKNOWN = "unknown"  # Not yet reviewed; blocks a package.
    HUMAN = "human"
    AI_ASSISTED = "ai_assisted"  # Author-created, AI used to edit or refine.
    AI_GENERATED = "ai_generated"  # Created by an AI-based tool, even if edited later.
    NONE = "none"  # Translations only: the book is not a translation.


class ContributorRole(StrEnum):
    AUTHOR = "author"
    EDITOR = "editor"
    ILLUSTRATOR = "illustrator"
    PHOTOGRAPHER = "photographer"
    TRANSLATOR = "translator"
    FOREWORD = "foreword"
    INTRODUCTION = "introduction"
    PREFACE = "preface"


@dataclass(frozen=True)
class Contributor:
    role: ContributorRole
    name: str

    def to_dict(self) -> dict[str, object]:
        return {"role": self.role.value, "name": self.name}


@dataclass(frozen=True)
class Series:
    title: str
    number: int | None = None

    def to_dict(self) -> dict[str, object]:
        return {"title": self.title, "number": self.number}


@dataclass(frozen=True)
class ReadingAge:
    minimum: int | None = None
    maximum: int | None = None

    def to_dict(self) -> dict[str, object]:
        return {"minimum": self.minimum, "maximum": self.maximum}


@dataclass(frozen=True)
class Audience:
    # KDP requires a yes/no answer; None means the author has not answered.
    sexually_explicit: bool | None = None
    reading_age: ReadingAge = field(default_factory=ReadingAge)

    def to_dict(self) -> dict[str, object]:
        return {
            "sexually_explicit": self.sexually_explicit,
            "reading_age": self.reading_age.to_dict(),
        }


@dataclass(frozen=True)
class Isbn:
    mode: IsbnMode = IsbnMode.UNDECIDED
    value: str | None = None  # Exactly as entered; only with mode `own`.

    def to_dict(self) -> dict[str, object]:
        return {"mode": self.mode.value, "value": self.value}


@dataclass(frozen=True)
class AiDisclosure:
    text: ContentOrigin = ContentOrigin.UNKNOWN
    images: ContentOrigin = ContentOrigin.UNKNOWN
    translations: ContentOrigin = ContentOrigin.UNKNOWN

    def to_dict(self) -> dict[str, object]:
        return {
            "text": self.text.value,
            "images": self.images.value,
            "translations": self.translations.value,
        }


@dataclass(frozen=True)
class Attestations:
    """The author's own confirmations. Never set by PuzzlePress; no timestamps."""

    rights: bool = False  # Holds the rights to the text, word lists and photograph.
    ai_disclosure: bool = False  # Reviewed the AI disclosure as declared.
    metadata: bool = False  # Description, keywords and categories represent the book.
    isbn: bool = False  # Own ISBN registered with this title, author and imprint.

    def to_dict(self) -> dict[str, object]:
        return {
            "rights": self.rights,
            "ai_disclosure": self.ai_disclosure,
            "metadata": self.metadata,
            "isbn": self.isbn,
        }


@dataclass(frozen=True)
class PublishingConfig:
    description: str | None = None
    keywords: tuple[str, ...] = ()
    categories: tuple[str, ...] = ()
    contributors: tuple[Contributor, ...] = ()
    audience: Audience = field(default_factory=Audience)
    low_content: bool | None = None
    isbn: Isbn = field(default_factory=Isbn)
    edition: int | None = None
    series: Series | None = None
    ai_disclosure: AiDisclosure = field(default_factory=AiDisclosure)
    attestations: Attestations = field(default_factory=Attestations)
    notes: str | None = None
    version: int = PUBLISHING_VERSION

    def to_dict(self) -> dict[str, object]:
        return {
            "version": self.version,
            "description": self.description,
            "keywords": list(self.keywords),
            "categories": list(self.categories),
            "contributors": [c.to_dict() for c in self.contributors],
            "audience": self.audience.to_dict(),
            "low_content": self.low_content,
            "isbn": self.isbn.to_dict(),
            "edition": self.edition,
            "series": self.series.to_dict() if self.series else None,
            "ai_disclosure": self.ai_disclosure.to_dict(),
            "attestations": self.attestations.to_dict(),
            "notes": self.notes,
        }
