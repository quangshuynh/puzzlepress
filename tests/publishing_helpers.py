"""Synthetic publishing metadata for tests.

Every declaration and attestation here is SYNTHETIC TEST DATA standing in for a
real author's decision. It is never written to the canonical books.
"""

import copy
from pathlib import Path

from tests.cover_helpers import cover_project

DESCRIPTION = (
    "Word searches from harbour walls and tide pools, each printed large on its own page.\n\n"
    "Solutions are at the back."
)


def complete_section(**overrides: object) -> dict[str, object]:
    """A publishing section that passes every metadata, disclosure and attestation rule."""
    section: dict[str, object] = {
        "version": 1,
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
    return section


def with_publishing(data: dict, **overrides: object) -> dict:
    data["publishing"] = complete_section(**overrides)
    data["book"]["author"] = data["book"].get("author") or "Synthetic Test Author"
    data["book"]["imprint"] = None
    return data


def publishing_project(root, puzzles: int = 16, cover: bool = True, **overrides: object):
    """A disposable book with interior (and cover) built, ready unless overridden.

    Returns (source directory, output directory). 16 puzzles give 29 pages.
    """
    from puzzlepress import load_project
    from puzzlepress.cover.build import build_cover, write_cover

    def mutate(data: dict) -> None:
        with_publishing(data, **overrides)

    source, output = cover_project(root, puzzles=puzzles, mutate=mutate)
    if cover:
        project = load_project(source).project
        write_cover(build_cover(project, source, output), output, source)
    return Path(source), Path(output)
