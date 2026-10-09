"""The automotive planning demonstration: what it shows and what it must never claim."""

import re

from planning_helpers import AUTOMOTIVE

from puzzlepress import build_identity, load_project
from puzzlepress.planning import State, evaluate_plan, read_planning
from puzzlepress.planning.model import Evidence, WordSource

TEXT = (AUTOMOTIVE / "planning.yaml").read_text(encoding="utf-8")


def report():  # type: ignore[no-untyped-def]
    plan = read_planning(AUTOMOTIVE).document
    assert plan is not None
    return evaluate_plan(load_project(AUTOMOTIVE).project, plan)


def test_demo_plans_the_automotive_book_beside_its_untouched_source() -> None:
    project = load_project(AUTOMOTIVE).project
    assert project.word_search is None  # The legacy source fixture is not production content.
    # The identity pinned in test_core: planning.yaml beside it changes nothing.
    assert build_identity(project) == (
        "pp1-sha256-7c31474f1712b985957d7edaa7ecff27f702060320eadbee7343819e13507bf2"
    )
    r = report()
    assert r.state is State.NEEDS_RESEARCH
    assert r.document.approval is None and r.approval.status == "none"


def test_demo_shows_structure_allocation_and_progression() -> None:
    r = report()
    doc = r.document
    assert doc.structure.target_puzzles == 60
    assert sum(t.puzzles or 0 for t in doc.themes) == 60
    assert [t.parent for t in doc.themes].count("automotive") == 7
    assert doc.difficulty.strategy.value == "gradual"
    assert [level.id for level in doc.difficulty.levels] == ["warm-up", "standard", "challenge"]
    assert len(doc.puzzles) == 7
    data = r.to_dict()
    assert data["page_estimate"] == {
        "minimum": 94,
        "maximum": 96,
        "parts": {"puzzles": 60, "solutions": 30, "front_matter": 3, "back_matter": 1},
    }


def test_demo_reports_the_puzzle_cap_honestly() -> None:
    r = report()
    codes = {f.rule.code for f in r.findings}
    assert "puzzle_count_unsupported" in codes
    assert next(i for i in r.feasibility if i.code == "puzzle_count").status == "unsupported"
    assert {"puzzles_unspecified", "question_blocking_open", "print_profile_undecided"} <= codes
    assert "pool_thin" in codes  # The candidate pools are too small for 60 puzzles.


def test_demo_fabricates_no_research_and_labels_provenance() -> None:
    doc = report().document
    assert doc.comparables == ()  # None recorded until a person has read and cited them.
    assert not [n for n in doc.research if n.evidence is Evidence.VERIFIED_SOURCE]
    for note in doc.research:
        if note.evidence is Evidence.UNVERIFIED_SOURCE:
            assert note.source.citation and "Not re-read for this book" in note.source.citation
            assert note.source.url is None  # No URL the repository does not record.
    assert {pool.source for pool in doc.vocabulary} == {WordSource.AI_GENERATED}
    assert all(e.source is None for pool in doc.vocabulary for e in pool.entries)
    assert "not validated" in (doc.positioning.primary_audience or "")
    assert doc.positioning.claims == ()
    lowered = TEXT.lower()
    for forbidden in ("profit", "revenue", "royalt", "sales rank", "bestsell", "best-sell",
                      "rating", "amazon.com"):  # fmt: skip
        assert forbidden not in lowered, forbidden
    assert not re.search(r"\$\s?\d", TEXT)
