"""Synthetic publishing metadata for tests.

Every declaration and attestation here is SYNTHETIC TEST DATA standing in for a
real author's decision. It is never written to the canonical books.
"""

import copy
from pathlib import Path

from puzzlepress.publishing_config import CONFIRMATIONS
from tests.cover_helpers import cover_project

# SYNTHETIC: a placeholder `confirm_current` replaces with the review identity of the
# content as it is at that moment, standing in for a person confirming after review.
CONFIRM = "confirm-current-content"

DESCRIPTION = (
    "Word searches from harbour walls and tide pools, each printed large on its own page.\n\n"
    "Solutions are at the back."
)


def complete_section(**overrides: object) -> dict[str, object]:
    """A publishing section that passes every metadata, disclosure and attestation rule."""
    section: dict[str, object] = {
        "version": 2,
        "description": DESCRIPTION,
        "keywords": ["seaside puzzles", "coastal vocabulary", "large print activity"],
        "categories": ["Humor & Entertainment > Puzzles & Games > Word Search"],
        "contributors": [],
        "audience": {"sexually_explicit": False, "reading_age": {"minimum": None, "maximum": None}},
        "low_content": False,
        "isbn": {"mode": "kdp_free", "value": None},
        "edition": 1,
        "series": None,
        "ai_disclosure": {"text": "human", "images": "human", "translations": "none"},
        # SYNTHETIC: tests confirm on behalf of no real author.
        "attestations": {"rights": True, "ai_disclosure": True, "metadata": True, "isbn": False},
        "notes": None,
    }
    for key, value in overrides.items():
        section[key] = copy.deepcopy(value)
    attestations = section["attestations"]
    if section["version"] == 2 and isinstance(attestations, dict):
        # True means "confirm the current content"; False means not confirmed.
        values = {name: attestations.get(name, False) for name in CONFIRMATIONS}
        section["attestations"] = {
            name: CONFIRM if value is True else None if value is False else value
            for name, value in values.items()
        }
    return section


def confirm_current(data: dict) -> dict:
    """Replace CONFIRM placeholders with the current review identity (synthetic decision)."""
    from puzzlepress import validate_project
    from puzzlepress.publishing.review import review_identity

    publishing = data.get("publishing")
    attestations = publishing.get("attestations") if publishing else None
    if not attestations:
        return data
    names = [name for name, value in attestations.items() if value == CONFIRM]
    if names:
        probe = copy.deepcopy(data)
        probe["publishing"]["attestations"] = {
            name: None if value == CONFIRM else value for name, value in attestations.items()
        }
        project = validate_project(probe).require_project()
        for name in names:
            attestations[name] = review_identity(project, name)
    return data


def reconfirm(source: Path, *names: str) -> None:
    """Confirm the named statements for the current content of a book.yaml (synthetic)."""
    from puzzlepress import load_project
    from puzzlepress.publishing.review import review_identity
    from puzzlepress.validation import validate_project
    from puzzlepress.yaml_io import dump_project

    project = load_project(source).project
    data = project.to_dict()
    for name in names:
        data["publishing"]["attestations"][name] = review_identity(project, name)
    path = Path(source) / "book.yaml" if Path(source).is_dir() else Path(source)
    path.write_text(dump_project(validate_project(data).require_project()), encoding="utf-8")


def with_publishing(data: dict, **overrides: object) -> dict:
    data["publishing"] = complete_section(**overrides)
    data["book"]["author"] = data["book"].get("author") or "Synthetic Test Author"
    data["book"]["imprint"] = None
    return confirm_current(data)


def publishing_project(
    root,
    puzzles: int | None = 16,
    cover: bool = True,
    photo: bytes | None = None,
    **overrides: object,
):
    """A disposable book with interior (and cover) built, ready unless overridden.

    Returns (source directory, output directory). 16 puzzles give 29 pages.
    """
    from puzzlepress import load_project
    from puzzlepress.cover.build import build_cover, write_cover

    def mutate(data: dict) -> None:
        with_publishing(data, **overrides)

    source, output = cover_project(root, data=photo, puzzles=puzzles, mutate=mutate)
    if cover:
        project = load_project(source).project
        write_cover(build_cover(project, source, output), output, source)
    return Path(source), Path(output)
