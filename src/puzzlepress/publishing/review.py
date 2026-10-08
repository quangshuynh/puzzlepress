"""Review identities: exactly what an author's confirmation was given for.

A confirmation in `publishing.attestations` stores the review identity of the
content the author reviewed. It applies only while that identity equals the
identity of the current content: editing reviewed content makes it stale, and
restoring exactly the reviewed content makes it apply again (identity, not time).
Each confirmation covers only what its statement is about, so an unrelated edit
leaves it in place. Identities are SHA-256 over canonical JSON of values: no
paths, times, display labels or file names (the photograph counts by its pinned
SHA-256). Python computes them; a digest identifies content and proves nothing
about authorship, rights or ownership.
"""

import hashlib

from ..identity import IDENTITY_VERSION
from ..models import Project
from .identity import canonical

# Bump when what a confirmation covers changes: every stored confirmation goes stale.
REVIEW_VERSION = 1

# What each confirmation covers, in words, for the author (docs/publishing.md).
COVERS = {
    "rights": "puzzle titles, themes and word lists, front and back matter text, the "
    "solutions heading, the cover's back text and the cover photograph",
    "ai_disclosure": "the AI content declaration and what it describes: the content the "
    "rights confirmation covers, plus the description",
    "metadata": "title, subtitle, author, contributors, series, edition, language, "
    "description, keywords, categories and audience",
    "isbn": "the ISBN option and number, title, subtitle, author and imprint",
}


def _content(project: Project) -> dict[str, object]:
    """The book's own words and photograph as printed; never generation settings."""
    puzzles: list[dict[str, object]] = []
    if project.word_search is not None:
        banks = {
            bank.id: {entry.id: entry.display for entry in bank.entries}
            for bank in project.word_search.banks
        }
        puzzles = [
            {
                "title": puzzle.title,
                "theme": puzzle.theme,
                "words": [banks.get(puzzle.bank, {}).get(t) for t in puzzle.target_ids],
            }
            for puzzle in project.word_search.puzzles
        ]
        # Publication order is composition, not content: reordering is not re-review.
        puzzles.sort(key=canonical)
    composition = project.composition
    cover = project.cover
    return {
        "puzzles": puzzles,
        "matter": [
            item.to_dict()
            for item in (composition.front_matter + composition.back_matter if composition else ())
        ],
        "solutions_title": composition.solutions.title if composition else None,
        "cover_text": cover.back_text if cover else None,
        "photograph": cover.image.sha256 if cover else None,
    }


def reviewed_content(project: Project, name: str) -> dict[str, object]:
    """The values confirmation `name` covers (COVERS), for a project with publishing."""
    book, publishing = project.book, project.publishing
    assert publishing is not None
    if name == "rights":
        return {"content": _content(project)}
    if name == "ai_disclosure":
        return {
            "declaration": publishing.ai_disclosure.to_dict(),
            "content": _content(project),
            "description": publishing.description,
        }
    if name == "metadata":
        return {
            "title": book.title,
            "subtitle": book.subtitle,
            "author": book.author,
            "language": book.language,
            "contributors": [c.to_dict() for c in publishing.contributors],
            "series": publishing.series.to_dict() if publishing.series else None,
            "edition": publishing.edition,
            "description": publishing.description,
            "keywords": list(publishing.keywords),
            "categories": list(publishing.categories),
            "audience": publishing.audience.to_dict(),
        }
    if name == "isbn":
        return {
            "isbn": publishing.isbn.to_dict(),
            "title": book.title,
            "subtitle": book.subtitle,
            "author": book.author,
            "imprint": book.imprint,
        }
    raise ValueError(f"Unknown confirmation {name!r}")


def review_identity(project: Project, name: str) -> str:
    """`pp1-review-sha256-...` of the content confirmation `name` covers, as it is now."""
    material = {
        "review_version": REVIEW_VERSION,
        "book_id": project.book.id,
        "confirmation": name,
        "reviewed": reviewed_content(project, name),
    }
    digest = hashlib.sha256(canonical(material)).hexdigest()
    return f"pp{IDENTITY_VERSION}-review-sha256-{digest}"
