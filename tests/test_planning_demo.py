"""The automotive production plan: what it records and what it must never claim."""

import re

from planning_helpers import AUTOMOTIVE

from puzzlepress import load_project
from puzzlepress.planning import State, evaluate_plan, read_planning
from puzzlepress.planning.model import Evidence, WordSource

TEXT = (AUTOMOTIVE / "planning.yaml").read_text(encoding="utf-8")
ADDED = "Added in Interval 12."


def report():  # type: ignore[no-untyped-def]
    plan = read_planning(AUTOMOTIVE).document
    assert plan is not None
    return evaluate_plan(load_project(AUTOMOTIVE).project, plan)


def test_plan_sits_beside_the_production_source_and_is_not_approved() -> None:
    project = load_project(AUTOMOTIVE).project
    assert project.word_search is not None and len(project.word_search.puzzles) == 60
    r = report()
    assert r.state is State.NEEDS_RESEARCH
    assert r.document.approval is None and r.approval.status == "none"
    # Only the comparables question blocks: no comparable book has been read.
    errors = {f.rule.code for f in r.findings if f.severity.value == "error"}
    assert errors == {"question_blocking_open"}
    open_blocking = [q.id for q in r.document.questions if q.blocking and q.resolution is None]
    assert open_blocking == ["q-comparables"]


def test_plan_specifies_every_puzzle_allocation_and_progression() -> None:
    r = report()
    doc = r.document
    assert doc.structure.target_puzzles == 60
    assert doc.structure.print_profile == "paperback-8.5x11"
    allocation = {t.id: t.puzzles for t in doc.themes if t.parent == "automotive"}
    assert allocation == {"engines": 10, "maintenance": 10, "tools": 8, "systems": 10,
                          "motorsport": 8, "history": 6, "driving": 8}  # fmt: skip
    assert doc.difficulty.strategy.value == "gradual"
    assert [level.id for level in doc.difficulty.levels] == ["warm-up", "standard", "challenge"]
    assert len(doc.puzzles) == 60
    assert [p.level for p in doc.puzzles] == ["warm-up"] * 20 + ["standard"] * 20 + [
        "challenge"
    ] * 20
    for theme, count in allocation.items():
        assert sum(p.theme == theme for p in doc.puzzles) == count
    # The Interval 11 opening section keeps its IDs, order and titles.
    assert [p.id for p in doc.puzzles[:7]] == [
        f"{theme}-01" for theme in ("engines", "maintenance", "tools", "systems", "motorsport",
                                    "history", "driving")
    ]  # fmt: skip
    assert r.to_dict()["page_estimate"] == {
        "minimum": 94,
        "maximum": 96,
        "parts": {"puzzles": 60, "solutions": 30, "front_matter": 3, "back_matter": 1},
    }


def test_plan_is_feasible_within_the_raised_cap() -> None:
    r = report()
    items = {i.code: i.status for i in r.feasibility}
    assert items["puzzle_count"] == "verified" and items["word_fit"] == "verified"
    assert items["generation"] == "unknown"  # Only production generates.
    codes = {f.rule.code for f in r.findings}
    assert "puzzle_count_unsupported" not in codes and "puzzles_unspecified" not in codes
    # Six pools exceed one 100-entry bank; production splits them by section.
    assert sum(f.rule.code == "bank_size_exceeds" for f in r.findings) == 6


def test_plan_fabricates_no_research_and_keeps_ai_provenance() -> None:
    doc = report().document
    assert doc.comparables == ()  # None recorded until a person has read and cited them.
    assert not [n for n in doc.research if n.evidence is Evidence.VERIFIED_SOURCE]
    for note in doc.research:
        if note.evidence is Evidence.UNVERIFIED_SOURCE:
            assert note.source.citation and "Not re-read for this book" in note.source.citation
            assert note.source.url is None  # No URL the repository does not record.
    positioning = next(n for n in doc.research if n.id == "r-positioning-default")
    assert positioning.evidence is Evidence.PREFERENCE  # The author's choice, not a finding.
    assert {pool.source for pool in doc.vocabulary} == {WordSource.AI_GENERATED}
    assert all(e.source is None for pool in doc.vocabulary for e in pool.entries)
    entries = [e for pool in doc.vocabulary for e in pool.entries]
    assert sum(e.note != ADDED for e in entries) == 184  # The Interval 11 candidates.
    assert sum(e.note == ADDED for e in entries) == len(entries) - 184
    assert "not validated" in (doc.positioning.primary_audience or "")
    assert doc.positioning.claims == ()
    # Market language may not appear outside the word lists (tire LOAD RATING is a term).
    prose = TEXT[: TEXT.index("\nvocabulary:")] + TEXT[TEXT.index("\nconstraints:") :]
    lowered = prose.lower()
    for forbidden in ("profit", "revenue", "royalt", "sales rank", "bestsell", "best-sell",
                      "rating", "amazon.com"):  # fmt: skip
        assert forbidden not in lowered, forbidden
    assert not re.search(r"\$\s?\d", TEXT)
