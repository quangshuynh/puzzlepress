"""Per-puzzle editorial review: author judgments bound to the content they cover.

A review records what a person decided about one puzzle's authored content
(terminology, title, theme, level and words): `reviewed`, `needs_changes`, or
nothing yet (`not_reviewed`). It is never inferred from automated quality
checks, never defaulted and never generated. Reviews live in reviews.yaml
beside book.yaml, outside every production identity: recording one never
changes seeds, grids, plans or PDFs.

Each recorded judgment stores the review identity of the puzzle content it
covered, `pp1-puzzle-review-sha256-...` over canonical JSON of the book ID, the
puzzle ID, title, theme, difficulty profile (grid size and directions) and the
ordered words (ID and display text). Editing any of those makes the judgment
stale; restoring exactly the same content restores it. The identity excludes
seeds, publication order, formatting and every other puzzle.

A reviewer name and date are optional words the author types; PuzzlePress never
fills them in and records no clock time.
"""

import hashlib
import json
import re
from dataclasses import dataclass, replace
from enum import StrEnum
from pathlib import Path

import yaml

from .content_validation import _Reader
from .errors import ProjectError, ValidationIssue
from .identity import IDENTITY_VERSION
from .models import Project
from .sidecar import LoadedSidecar, read_sidecar, write_sidecar

REVIEW_FILE = "reviews.yaml"
REVIEW_VERSION = 1
# Bump when what a review covers changes: every recorded judgment goes stale.
REVIEW_IDENTITY_VERSION = 1
MAX_NOTE = 2000
MAX_REVIEWER = 120
DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
IDENTITY = re.compile(r"pp1-puzzle-review-sha256-[0-9a-f]{64}")


class ReviewStatus(StrEnum):
    NOT_REVIEWED = "not_reviewed"
    NEEDS_CHANGES = "needs_changes"
    REVIEWED = "reviewed"


@dataclass(frozen=True)
class PuzzleReview:
    puzzle: str
    status: ReviewStatus
    content: str | None = None  # The review identity judged; None while not reviewed.
    note: str | None = None
    reviewer: str | None = None  # Typed by the author; never inferred.
    reviewed_on: str | None = None  # YYYY-MM-DD typed by the author; never a clock.

    def to_dict(self) -> dict[str, object]:
        data: dict[str, object] = {"puzzle": self.puzzle, "status": self.status.value}
        for key in ("content", "note", "reviewer", "reviewed_on"):
            value = getattr(self, key)
            if value is not None:
                data[key] = value
        return data


@dataclass(frozen=True)
class ReviewPolicy:
    """An internal workflow gate, not a KDP requirement."""

    require_all: bool = False  # Production approval waits for every puzzle's review.

    def to_dict(self) -> dict[str, object]:
        return {"require_all": self.require_all}


@dataclass(frozen=True)
class ReviewDocument:
    version: int = REVIEW_VERSION
    policy: ReviewPolicy = ReviewPolicy()
    puzzles: tuple[PuzzleReview, ...] = ()

    def get(self, puzzle: str) -> PuzzleReview | None:
        return next((r for r in self.puzzles if r.puzzle == puzzle), None)

    def to_dict(self) -> dict[str, object]:
        return {
            "review_version": self.version,
            "policy": self.policy.to_dict(),
            "puzzles": [review.to_dict() for review in self.puzzles],
        }


# ------------------------------------------------------------------ identity


def _canonical(data: object) -> bytes:
    return json.dumps(
        data, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False
    ).encode("ascii")


def puzzle_content(project: Project, puzzle_id: str) -> dict[str, object] | None:
    """The authored values one review covers, or None for an unknown puzzle."""
    content = project.word_search
    if content is None:
        return None
    definition = next((p for p in content.puzzles if p.id == puzzle_id), None)
    if definition is None:
        return None
    config = content.config_for(definition)
    return {
        "review_identity_version": REVIEW_IDENTITY_VERSION,
        "book_id": project.book.id,
        "puzzle": {
            "id": definition.id,
            "title": definition.title,
            "theme": definition.theme,
            "difficulty": {
                "id": definition.difficulty,
                "width": config.size.width,
                "height": config.size.height,
                "directions": sorted(d.name.lower() for d in config.directions),
            },
            "words": [
                {"id": entry.id, "display": entry.display}
                for entry in content.entries_for(definition)
            ],
        },
    }


def review_identity(project: Project, puzzle_id: str) -> str | None:
    content = puzzle_content(project, puzzle_id)
    if content is None:
        return None
    digest = hashlib.sha256(_canonical(content)).hexdigest()
    return f"pp{IDENTITY_VERSION}-puzzle-review-sha256-{digest}"


# ------------------------------------------------------------------ schema


def validate_reviews(value: object) -> tuple[ReviewDocument | None, tuple[ValidationIssue, ...]]:
    reader = _Reader()
    data = reader.mapping(value, "reviews", {"review_version", "policy", "puzzles"})
    if not isinstance(value, dict):
        return None, tuple(reader.issues)
    if data.get("review_version") != REVIEW_VERSION:
        reader.issue(
            "reviews.review_version",
            "unsupported_version",
            f"Review version {data.get('review_version')!r} is not supported. Supported: 1.",
        )
        return None, tuple(reader.issues)
    policy_data = reader.mapping(data.get("policy", {}), "reviews.policy", {"require_all"})
    require_all = policy_data.get("require_all", False)
    if not isinstance(require_all, bool):
        reader.issue("reviews.policy.require_all", "type", "Expected true or false.")
        require_all = False
    reviews: list[PuzzleReview] = []
    seen: set[str] = set()
    for index, entry in enumerate(
        reader.sequence(data.get("puzzles", []), "reviews.puzzles", 500, 0)
    ):
        path = f"reviews.puzzles.{index}"
        item = reader.mapping(
            entry, path, {"puzzle", "status", "content", "note", "reviewer", "reviewed_on"}
        )
        puzzle = reader.text(item.get("puzzle"), f"{path}.puzzle", identifier=True)
        if puzzle in seen:
            reader.issue(f"{path}.puzzle", "duplicate", f"Puzzle {puzzle!r} is reviewed twice.")
        seen.add(puzzle)
        raw_status = item.get("status")
        if not isinstance(raw_status, str) or raw_status not in {s.value for s in ReviewStatus}:
            reader.issue(
                f"{path}.status", "choice", "Use one of: not_reviewed, needs_changes, reviewed."
            )
            continue
        status = ReviewStatus(raw_status)
        content = item.get("content")
        if status is ReviewStatus.NOT_REVIEWED:
            if content is not None:
                reader.issue(f"{path}.content", "not_applicable", "Only a judgment has content.")
        elif not isinstance(content, str) or not IDENTITY.fullmatch(content):
            reader.issue(
                f"{path}.content",
                "identity",
                "A judgment records the review identity of the content it covers.",
            )
        note = _optional(reader, item.get("note"), f"{path}.note", MAX_NOTE, multiline=True)
        reviewer = _optional(reader, item.get("reviewer"), f"{path}.reviewer", MAX_REVIEWER)
        reviewed_on = item.get("reviewed_on")
        if reviewed_on is not None and (
            not isinstance(reviewed_on, str) or not DATE.fullmatch(reviewed_on)
        ):
            reader.issue(f"{path}.reviewed_on", "date", "Use a date as YYYY-MM-DD.")
            reviewed_on = None
        reviews.append(
            PuzzleReview(
                puzzle,
                status,
                content if isinstance(content, str) else None,
                note,
                reviewer,
                reviewed_on if isinstance(reviewed_on, str) else None,
            )
        )
    if reader.issues:
        return None, tuple(reader.issues)
    return ReviewDocument(REVIEW_VERSION, ReviewPolicy(require_all), tuple(reviews)), ()


def _optional(
    reader: _Reader, value: object, path: str, limit: int, multiline: bool = False
) -> str | None:
    if value is None:
        return None
    if (
        not isinstance(value, str)
        or not value.strip()
        or len(value) > limit
        or any((ord(c) < 32 and not (multiline and c == "\n")) or ord(c) == 127 for c in value)
    ):
        reader.issue(path, "text", f"Expected 1..{limit} characters of plain text.")
        return None
    return value.strip()


def _require(value: object) -> ReviewDocument:
    document, issues = validate_reviews(value)
    if document is None:
        raise ProjectError(issues)
    return document


# ------------------------------------------------------------------ store


@dataclass(frozen=True)
class LoadedReviews:
    document: ReviewDocument
    revision: str | None  # None: reviews.yaml does not exist yet.


def read_reviews(source_directory: Path) -> LoadedReviews:
    loaded: LoadedSidecar = read_sidecar(source_directory, REVIEW_FILE)
    if loaded.data is None:
        return LoadedReviews(ReviewDocument(), loaded.revision)
    return LoadedReviews(_require(loaded.data), loaded.revision)


def dump_reviews(document: ReviewDocument) -> str:
    return yaml.safe_dump(document.to_dict(), allow_unicode=True, sort_keys=False, width=88)


def write_reviews(source_directory: Path, document: ReviewDocument, revision: str | None) -> str:
    return write_sidecar(source_directory, REVIEW_FILE, dump_reviews(document), revision, _require)


# ------------------------------------------------------------------ judgments


class ReviewError(Exception):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


def record_review(
    project: Project,
    document: ReviewDocument,
    puzzle_id: str,
    status: ReviewStatus,
    identity: str | None,
    note: str | None = None,
    reviewer: str | None = None,
    reviewed_on: str | None = None,
) -> ReviewDocument:
    """A new document with one puzzle's review replaced. Raises ReviewError.

    A judgment must name the review identity Python reports for the saved
    content now (`content_changed` otherwise), so a person always judges what
    is actually in the book. Resetting to not_reviewed keeps any note.
    """
    current = review_identity(project, puzzle_id)
    if current is None:
        raise ReviewError("unknown_puzzle", f"The book has no puzzle {puzzle_id!r}.")
    if status is not ReviewStatus.NOT_REVIEWED and identity != current:
        raise ReviewError(
            "content_changed",
            "This puzzle changed since you opened it. Reload and review the saved content.",
        )
    review = PuzzleReview(
        puzzle_id,
        status,
        None if status is ReviewStatus.NOT_REVIEWED else current,
        note,
        reviewer,
        reviewed_on,
    )
    _require(ReviewDocument(document.version, document.policy, (review,)).to_dict())
    order = [p.id for p in project.word_search.puzzles] if project.word_search else []
    others = [r for r in document.puzzles if r.puzzle != puzzle_id]
    keep = review.status is not ReviewStatus.NOT_REVIEWED or review.note is not None
    reviews = others + ([review] if keep else [])
    reviews.sort(
        key=lambda r: (order.index(r.puzzle) if r.puzzle in order else len(order), r.puzzle)
    )
    return replace(document, puzzles=tuple(reviews))


def set_policy(document: ReviewDocument, require_all: bool) -> ReviewDocument:
    return replace(document, policy=ReviewPolicy(require_all))


@dataclass(frozen=True)
class PuzzleReviewState:
    puzzle: str
    title: str
    theme: str
    identity: str
    state: str  # not_reviewed, needs_changes, reviewed, stale
    recorded: PuzzleReview | None

    def to_dict(self) -> dict[str, object]:
        return {
            "puzzle": self.puzzle,
            "title": self.title,
            "theme": self.theme,
            "identity": self.identity,
            "state": self.state,
            "recorded": None if self.recorded is None else self.recorded.to_dict(),
        }


@dataclass(frozen=True)
class ReviewReport:
    puzzles: tuple[PuzzleReviewState, ...]
    orphaned: tuple[PuzzleReview, ...]  # Recorded for puzzles no longer in the book.
    policy: ReviewPolicy

    def count(self, state: str) -> int:
        return sum(p.state == state for p in self.puzzles)

    @property
    def complete(self) -> bool:
        return bool(self.puzzles) and all(p.state == "reviewed" for p in self.puzzles)

    def summary(self) -> dict[str, object]:
        return {
            "total": len(self.puzzles),
            "reviewed": self.count("reviewed"),
            "needs_changes": self.count("needs_changes"),
            "not_reviewed": self.count("not_reviewed"),
            "stale": self.count("stale"),
            "complete": self.complete,
            "require_all": self.policy.require_all,
        }

    def to_dict(self) -> dict[str, object]:
        return {
            "summary": self.summary(),
            "puzzles": [p.to_dict() for p in self.puzzles],
            "orphaned": [r.to_dict() for r in self.orphaned],
        }


def evaluate_reviews(project: Project, document: ReviewDocument) -> ReviewReport:
    """Each puzzle's review state against the content as it is now."""
    states: list[PuzzleReviewState] = []
    known: set[str] = set()
    for definition in project.word_search.puzzles if project.word_search else ():
        known.add(definition.id)
        identity = review_identity(project, definition.id)
        assert identity is not None
        recorded = document.get(definition.id)
        if recorded is None or recorded.status is ReviewStatus.NOT_REVIEWED:
            state = "not_reviewed"
        elif recorded.content != identity:
            state = "stale"
        else:
            state = recorded.status.value
        states.append(
            PuzzleReviewState(
                definition.id, definition.title, definition.theme, identity, state, recorded
            )
        )
    orphaned = tuple(r for r in document.puzzles if r.puzzle not in known)
    return ReviewReport(tuple(states), orphaned, document.policy)
