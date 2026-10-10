"""docs/automotive-content-audit.md stays a faithful view of the production book."""

import re

from puzzlepress import load_project
from puzzlepress.planning import read_planning
from tests.helpers import ROOT

BOOK = ROOT / "books" / "automotive"
AUDIT = (ROOT / "docs" / "automotive-content-audit.md").read_text(encoding="utf-8")
LEVEL = {"warm-up": "Warm-up", "standard": "Standard", "challenge": "Challenge"}


def test_audit_tables_match_the_book() -> None:
    project = load_project(BOOK).project
    plan = read_planning(BOOK).document
    assert project.word_search is not None and plan is not None
    content = project.word_search
    labels = {t.id: t.label for t in plan.themes}
    planned = {p.id: p for p in plan.puzzles}
    profiles = {p.id: p.config for p in content.profiles}
    rows = re.findall(r"^\| (\d+) \| `([^`]+)` \| (.+?) \| (.+?) \| (\S+) \| (\d+) x (\d+) "
                      r"\| (\d+) \| (\w+) \|$", AUDIT, re.MULTILINE)  # fmt: skip
    lists = re.findall(r"^- \*\*(\d+)\. (.+?)\*\* \(`([^`]+)`\): (.+)$", AUDIT, re.MULTILINE)
    assert len(rows) == len(lists) == len(content.puzzles) == 60
    for page, (definition, row, listed) in enumerate(
        zip(content.puzzles, rows, lists, strict=True), 1
    ):
        size = profiles[definition.difficulty].size
        assert row == (
            str(page), definition.id, definition.title, labels[planned[definition.id].theme],
            LEVEL[definition.difficulty], str(size.width), str(size.height),
            str(len(definition.target_ids)), "clean",
        )  # fmt: skip
        words = ", ".join(e.display for e in content.entries_for(definition))
        assert listed == (str(page), definition.title, definition.id, words)


def test_audit_claims_no_human_review_or_approval() -> None:
    assert "No person has reviewed or approved this content yet" in AUDIT
    assert "| Human review | Not done" in AUDIT
    plan = read_planning(BOOK).document
    assert plan is not None and plan.approval is None
