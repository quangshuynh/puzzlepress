"""Shared planning fixtures: a small complete plan and helpers to evaluate variants.

The complete plan reaches `ready_for_approval` against books/automotive. Its
words are generic automotive terms written for tests; the research note is a
synthetic test record, not a claim about any real source.
"""

import copy
import shutil
from pathlib import Path
from typing import TYPE_CHECKING

from puzzlepress import load_project
from puzzlepress.models import Project
from puzzlepress.planning import PlanningDocument, validate_planning

if TYPE_CHECKING:
    from puzzlepress.planning import PlanningReadinessReport

ROOT = Path(__file__).resolve().parents[1]
AUTOMOTIVE = ROOT / "books" / "automotive"

ENGINE_WORDS = [
    "PISTON",
    "VALVE",
    "CAMSHAFT",
    "CYLINDER",
    "GASKET",
    "INJECTOR",
    "TURBO",
    "MANIFOLD",
    "FLYWHEEL",
    "CLUTCH",
    "GEARBOX",
    "AXLE",
    "TORQUE",
    "THROTTLE",
    "IGNITION",
    "DIESEL",
    "SPARK PLUG",
    "TIMING BELT",
    "OIL PUMP",
    "CRANKCASE",
    "INTAKE",
    "EXHAUST",
    "PUSHROD",
    "BEARING",
]
TOOL_WORDS = [
    "WRENCH",
    "SOCKET",
    "RATCHET",
    "PLIERS",
    "HAMMER",
    "MALLET",
    "CREEPER",
    "FUNNEL",
    "VISE",
    "TOOLBOX",
    "GLOVES",
    "PRY BAR",
    "FLOOR JACK",
    "MULTIMETER",
    "WORKBENCH",
    "FLASHLIGHT",
    "COMPRESSOR",
    "TIRE GAUGE",
    "BREAKER BAR",
    "CHISEL",
    "FILE",
    "CLAMP",
    "SNIPS",
    "SCRAPER",
]


def project() -> Project:
    return load_project(AUTOMOTIVE).project


def complete_plan() -> dict[str, object]:
    """A plan with every gate passing: 12 puzzles, two themes, two levels."""
    puzzles: list[dict[str, object]] = []
    for level, offset in (("easy", 0), ("hard", 3)):
        for theme, words in (("engines", ENGINE_WORDS), ("tools", TOOL_WORDS)):
            for n in range(3):
                start = (offset + n) * 4
                puzzles.append(
                    {
                        "id": f"{theme}-{offset + n + 1}",
                        "theme": theme,
                        "level": level,
                        "title": f"{theme.title()} {offset + n + 1}",
                        "words": words[start : start + 4],
                    }
                )
    return {
        "planning_version": 1,
        "concept": {
            "summary": "Word searches about engines and the tools used to work on them.",
            "subject": "Automotive",
            "reader_experience": "Short, steady puzzles.",
            "scope": "Two themes.",
        },
        "positioning": {
            "primary_audience": "Adult car enthusiasts",
            "secondary_audience": "Automotive students",
            "candidate_audiences": ["Car enthusiasts", "Mechanics"],
            "familiarity": "enthusiast",
            "tone": "Friendly",
            "use_case": "Leisure",
            "main_benefit": "Real workshop vocabulary.",
            "differentiation": "Engines and tools only.",
            "evidence": ["r-test"],
            "claims": [],
        },
        "structure": {
            "puzzle_type": "word_search",
            "target_puzzles": 12,
            "print_profile": "paperback-8.5x11",
            "solutions": "end",
            "solutions_per_page": 1,
            "front_matter_pages": 3,
            "back_matter_pages": 1,
        },
        "difficulty": {
            "strategy": "gradual",
            "levels": [
                {
                    "id": "easy",
                    "label": "Easy",
                    "width": 10,
                    "height": 10,
                    "directions": ["right", "down"],
                    "words": {"min": 4, "max": 6},
                },
                {
                    "id": "hard",
                    "label": "Hard",
                    "width": 12,
                    "height": 12,
                    "directions": ["right", "down", "down-right", "left"],
                    "words": {"min": 4, "max": 8},
                },
            ],
        },
        "themes": [
            {"id": "engines", "label": "Engines", "required": True, "puzzles": 6},
            {"id": "tools", "label": "Tools", "puzzles": 6},
        ],
        "vocabulary": [
            {"theme": "engines", "source": "human", "entries": [{"word": w} for w in ENGINE_WORDS]},
            {"theme": "tools", "source": "human", "entries": [{"word": w} for w in TOOL_WORDS]},
        ],
        "puzzles": puzzles,
        "constraints": {"min_letters": 3, "max_letters": 15, "max_word_reuse": 2},
        "questions": [
            {
                "id": "q-test",
                "question": "Is two themes enough?",
                "blocking": True,
                "resolution": "Yes, for a first book.",
            },
        ],
        "research": [
            {
                "id": "r-test",
                "question": "q-test",
                "observation": "Synthetic test observation.",
                "evidence": "verified_source",
                "source": {
                    "citation": "Synthetic test citation",
                    "url": "https://example.com/a",
                    "type": "other",
                },
                "observed": "2026-10-09",
            }
        ],
        "comparables": [],
        "approval": None,
    }


def document(data: dict[str, object]) -> PlanningDocument:
    found, issues = validate_planning(data)
    assert found is not None, issues
    return found


def evaluate(data: dict[str, object], against: Project | None = None) -> "PlanningReadinessReport":
    from puzzlepress.planning import evaluate_plan

    return evaluate_plan(against or project(), document(data))


def variant(**changes: object) -> dict[str, object]:
    """complete_plan() with top-level sections replaced or dotted paths set."""
    data = complete_plan()
    for key, value in changes.items():
        target: object = data
        parts = key.split("__")
        for part in parts[:-1]:
            target = target[int(part)] if isinstance(target, list) else target[part]  # type: ignore[index]
        last = parts[-1]
        if isinstance(target, list):
            target[int(last)] = value
        else:
            assert isinstance(target, dict)
            target[last] = value
    return copy.deepcopy(data)


def codes(report: "PlanningReadinessReport") -> set[str]:
    return {f.rule.code for f in report.findings}


def copy_book(tmp_path: Path, name: str = "automotive") -> Path:
    target = tmp_path / "books" / name
    shutil.copytree(ROOT / "books" / name, target)
    return target
