"""Production handoff: what an approved plan hands to production, and nothing more.

The handoff is a deterministic, versioned JSON document derived from an approved
plan. It names the planned book and the approved identity, and lists the theme
allocations, level settings, planned puzzles with their words, vocabulary with
provenance, constraints, open editorial findings, what production must still
verify and the decisions only a person can make. It is printed, never written
into the project: it does not create or change puzzle definitions in book.yaml,
choose word IDs or seeds, or generate anything. Producing the book is the next
interval's work.
"""

import json

from .. import __version__
from ..preflight.model import Severity
from .model import WordSource
from .readiness import PlanningReadinessReport
from .rules import RULESET_ID, RULESET_VERSION
from .vocabulary import search_form

HANDOFF_VERSION = 1

NOT_VERIFIED = (
    "Whether the generator places every planned word in every grid: production generates and "
    "verifies each puzzle.",
    "Accidental or prohibited words in generated grids: screened after generation.",
    "Exact page count, layout fit with the real word lists, and KDP interior preflight.",
    "Cover geometry, spine width and spine text: they derive from the built interior.",
    "Research notes, comparable books and audience choices: recorded as the author entered "
    "them; PuzzlePress verified none of them.",
)
DECISIONS = (
    "Word-bank entry IDs and puzzle definition IDs for book.yaml (seeds derive from them).",
    "Book composition: front matter, copyright text, instructions and solution headings.",
    "Whether to raise the 20-puzzle project cap or produce a smaller book, if the plan exceeds it.",
    "The AI content disclosure in Publishing, given the vocabulary provenance below.",
    "Publishing metadata, confirmations and the cover photograph.",
)


class HandoffUnavailable(Exception):
    """The plan is not approved as it stands, so there is nothing to hand off."""


def handoff_document(report: PlanningReadinessReport) -> dict[str, object]:
    if not report.approved:
        raise HandoffUnavailable(
            "Only an approved plan hands off to production. "
            f"State: {report.state.value}; approval: {report.approval.status}."
        )
    doc = report.document
    level_rows = report.views["levels"]
    assert isinstance(level_rows, list)
    levels = {row["id"]: row for row in level_rows}
    pools = {pool.theme: pool for pool in doc.vocabulary}
    sources: dict[str, int] = {source.value: 0 for source in WordSource}
    vocabulary: list[dict[str, object]] = []
    for pool in doc.vocabulary:
        entries = []
        for entry in pool.entries:
            search, problem = search_form(entry.word)
            source = pool.source_of(entry)
            sources[source.value] += 1
            entries.append(
                {
                    "word": entry.word,
                    "search": search,
                    "valid": problem is None,
                    "source": source.value,
                    "reference": entry.reference or pool.reference,
                }
            )
        vocabulary.append({"theme": pool.theme, "entries": entries})
    puzzles = []
    for order, puzzle in enumerate(doc.puzzles, 1):
        theme_pool = pools.get(puzzle.theme)
        origin = (
            {e.word: theme_pool.source_of(e).value for e in theme_pool.entries}
            if theme_pool
            else {}
        )
        puzzles.append(
            {
                "order": order,
                "id": puzzle.id,
                "title": puzzle.title,
                "theme": puzzle.theme,
                "level": puzzle.level,
                "settings": levels.get(puzzle.level) if puzzle.level else None,
                "words": [
                    {"word": w, "search": search_form(w)[0], "source": origin.get(w)}
                    for w in puzzle.words
                ],
                "notes": puzzle.notes,
            }
        )
    positioning = doc.positioning
    open_questions = [q.to_dict() for q in doc.questions if q.resolution is None]
    return {
        "handoff_version": HANDOFF_VERSION,
        "engine_version": __version__,
        "ruleset": {"id": RULESET_ID, "version": RULESET_VERSION},
        "book": {"id": report.project.book.id, "title": report.project.book.title},
        "planning_identity": report.identity,
        "approved_identity": report.approval.approved_identity,
        "concept": {
            **doc.concept.to_dict(),
            "primary_audience": positioning.primary_audience,
            "secondary_audience": positioning.secondary_audience,
            "familiarity": positioning.familiarity.value,
            "tone": positioning.tone,
            "use_case": positioning.use_case,
            "main_benefit": positioning.main_benefit,
            "differentiation": positioning.differentiation,
        },
        "structure": doc.structure.to_dict(),
        "difficulty": {
            "strategy": doc.difficulty.strategy.value,
            "levels": report.views["levels"],
        },
        "themes": report.views["allocation"],
        "puzzles": puzzles,
        "vocabulary": vocabulary,
        "constraints": doc.constraints.to_dict(),
        "provenance": {
            "words_by_source": sources,
            "note": "Sources are the author's records. A source records origin, not "
            "permission. AI-generated words must not be presented as human-authored.",
        },
        "page_estimate": report.pages.to_dict(),
        "known_constraints": [item.to_dict() for item in report.feasibility],
        "open_editorial_findings": [
            f.to_dict() for f in report.findings if f.severity is not Severity.ERROR
        ],
        "open_questions": open_questions,
        "not_verified": list(NOT_VERIFIED),
        "required_human_decisions": list(DECISIONS),
    }


def handoff_bytes(report: PlanningReadinessReport) -> bytes:
    text = json.dumps(handoff_document(report), sort_keys=True, indent=2, ensure_ascii=True,
                      allow_nan=False)  # fmt: skip
    return (text + "\n").encode("ascii")
