"""A SYNTHETIC 60-puzzle production book for engine tests, CI and browser acceptance.

Real books live in the separate puzzlepress-books repository; the engine never
depends on them. This module writes a book with the same production shape as a
real one (seven themes allocated 10/10/8/10/8/6/8, three levels on 13/15/17 grids,
split banks, front matter, two solutions a page, open publishing decisions and an
unapproved plan) from invented pseudo-words generated deterministically here.
Nothing in it is authored book content or a claim about any market.

Run as a script to write it: python tests/production_book.py DIRECTORY
"""

import random
import sys
from pathlib import Path

from puzzlepress import validate_project
from puzzlepress.planning import validate_planning, write_planning
from puzzlepress.yaml_io import dump_project

BOOK_ID = "synthetic-production-book"
TITLE = "Synthetic Production Book"
THEMES = (
    ("north", "Northern Words", 10, (3, 3, 4)),
    ("east", "Eastern Words", 10, (4, 3, 3)),
    ("south", "Southern Words", 8, (3, 3, 2)),
    ("west", "Western Words", 10, (3, 4, 3)),
    ("high", "Highland Words", 8, (3, 2, 3)),
    ("low", "Lowland Words", 6, (2, 2, 2)),
    ("coast", "Coastal Words", 8, (2, 3, 3)),
)
LEVELS = (
    ("warm-up", "Warm-up", 13, ["right", "down", "down-right"], (10, 12), (10, 11)),
    ("standard", "Standard", 15, ["right", "down", "down-right", "up-right"], (12, 15), (13, 14)),
    ("challenge", "Challenge", 17,
     ["right", "left", "down", "up", "down-right", "down-left", "up-right", "up-left"],
     (15, 18), (16, 16)),
)  # fmt: skip
SYLLABLES = (
    "BAR DEN FOL GRA HUN JEL KOR LAN MIR NOV PAL QUI ROS SAV TOR VEL WEN YAR ZOL "
    "BRI CAM DRU FEN GOL HAV JUN KAL LOR MEN NIL PER RUN SEL TAV VOR WIL ZEN"
).split()
SCREENING = ["QXQX", "ZZYZX"]  # Nonsense: exercises screening without real policy words.


def _words(rng: random.Random, used: set[str], count: int, longest: int) -> list[str]:
    """`count` new pseudo-words (some two-word), none containing another either way."""
    chosen: list[str] = []
    while len(chosen) < count:
        parts = ["".join(rng.choice(SYLLABLES) for _ in range(rng.randint(2, 3)))]
        if rng.random() < 0.25:
            parts.append("".join(rng.choice(SYLLABLES) for _ in range(2)))
        display = " ".join(parts)
        form = display.replace(" ", "")
        if form in used or not 6 <= len(form) <= longest:
            continue
        if any(form in other or other in form or form[::-1] in other
               for other in (w.replace(" ", "") for w in chosen)):  # fmt: skip
            continue
        used.add(form)
        chosen.append(display)
    return sorted(chosen, key=lambda w: w.replace(" ", ""))


def _puzzles() -> list[tuple[str, str, str, str, list[str]]]:
    """(id, theme, level, title, words) in book order: levels in turn, themes rotating."""
    rng = random.Random(2026)
    used: set[str] = set()
    counters = {theme: 0 for theme, *_ in THEMES}
    order: list[tuple[str, str, str, str, list[str]]] = []
    for level_index, (level, label, side, _, _, (low, high)) in enumerate(LEVELS):
        remaining = {theme: split[level_index] for theme, _, _, split in THEMES}
        while any(remaining.values()):
            for theme, theme_label, _, _ in THEMES:
                if not remaining[theme]:
                    continue
                remaining[theme] -= 1
                counters[theme] += 1
                number = counters[theme]
                count = low if (number + level_index) % 2 else high
                words = _words(rng, used, count, min(side, 15))
                title = f"{theme_label.split()[0]} {label} {number}"
                order.append((f"{theme}-{number:02d}", theme, level, title, words))
    return order


def _slug(word: str) -> str:
    return word.lower().replace(" ", "-")


def book_data() -> dict[str, object]:
    puzzles = _puzzles()
    banks: dict[str, list[str]] = {}
    for _, theme, level, _, words in puzzles:
        bank = f"{theme}-challenge" if level == "challenge" else theme
        banks.setdefault(bank, []).extend(words)
    labels = {theme: label for theme, label, _, _ in THEMES}
    level_labels = {level: label for level, label, *_ in LEVELS}
    return {
        "schema_version": 1,
        "book": {
            "id": BOOK_ID,
            "title": TITLE,
            "subtitle": "60 Synthetic Test Puzzles",
            "description": "SYNTHETIC engine test fixture; not a real book.",
            "language": "en-US",
        },
        "build": {"seed": 2026},
        "output": {"directory": f"../../build/{BOOK_ID}"},
        "word_search": {
            "banks": [
                {"id": bank, "entries": [{"id": _slug(w), "display": w} for w in words]}
                for bank, words in banks.items()
            ],
            "profiles": [
                {"id": level, "width": side, "height": side, "directions": directions}
                for level, _, side, directions, _, _ in LEVELS
            ],
            "puzzles": [
                {
                    "id": pid,
                    "title": title,
                    "theme": f"{labels[theme]} · {level_labels[level]}",
                    "bank": f"{theme}-challenge" if level == "challenge" else theme,
                    "target_ids": [_slug(w) for w in words],
                    "difficulty": level,
                }
                for pid, theme, level, title, words in puzzles
            ],
            "quality": {"max_word_reuse": 2, "prohibited_words": SCREENING},
        },
        "composition": {
            "front_matter": [
                {"kind": "title_page"},
                {"kind": "copyright_page", "text": "SYNTHETIC test fixture. No rights claimed."},
                {
                    "kind": "instructions",
                    "title": "How to Use This Book",
                    "text": "Find each listed word in its grid. Solutions begin on page 61.",
                },
            ],
            "puzzles": {"start": "recto"},
            "solutions": {
                "placement": "end",
                "title": "Solutions",
                "per_page": 2,
                "start": "recto",
            },  # fmt: skip
            "back_matter": [{"kind": "about", "title": "About", "text": "SYNTHETIC fixture."}],
            "page_numbers": {"scheme": "roman_front_matter", "show_front_matter": False},
        },
        "publishing": {
            "version": 2,
            "description": "SYNTHETIC test fixture describing sixty word searches.",
            "keywords": ["synthetic test puzzles"],
            "categories": [],
            "contributors": [],
            "audience": {
                "sexually_explicit": None,
                "reading_age": {"minimum": None, "maximum": None},
            },  # fmt: skip
            "low_content": None,
            "isbn": {"mode": "undecided", "value": None},
            "edition": None,
            "series": None,
            "ai_disclosure": {"text": "unknown", "images": "unknown", "translations": "unknown"},
            "attestations": {
                "rights": None,
                "ai_disclosure": None,
                "metadata": None,
                "isbn": None,
            },  # fmt: skip
            "notes": "SYNTHETIC: every decision stays open, as for a real book before review.",
        },
    }


def plan_data() -> dict[str, object]:
    puzzles = _puzzles()
    pools: dict[str, list[str]] = {}
    for _, theme, _, _, words in puzzles:
        pools.setdefault(theme, []).extend(words)
    return {
        "planning_version": 1,
        "concept": {
            "summary": "SYNTHETIC plan of a 60-puzzle test book in seven themes.",
            "subject": "Synthetic test vocabulary",
            "reader_experience": "Gradual difficulty from warm-up to challenge grids.",
            "scope": "Seven synthetic themes.",
        },
        "positioning": {
            "primary_audience": "Synthetic test audience (not validated)",
            "secondary_audience": None,
            "candidate_audiences": ["Synthetic test audience"],
            "familiarity": "mixed",
            "tone": "Neutral",
            "use_case": "Engine tests",
            "main_benefit": "Exercises production scale.",
            "differentiation": "Hypothesis to test: none; this is a test fixture.",
            "evidence": [],
            "claims": [],
        },
        "structure": {
            "puzzle_type": "word_search",
            "target_puzzles": 60,
            "print_profile": "paperback-8.5x11",
            "solutions": "end",
            "solutions_per_page": 2,
            "front_matter_pages": 3,
            "back_matter_pages": 1,
        },
        "difficulty": {
            "strategy": "gradual",
            "levels": [
                {
                    "id": level,
                    "label": label,
                    "width": side,
                    "height": side,
                    "directions": directions,
                    "words": {"min": low, "max": high},
                }
                for level, label, side, directions, (low, high), _ in LEVELS
            ],  # fmt: skip
        },
        "themes": [{"id": "all", "label": "All Words"}]
        + [
            {"id": theme, "label": label, "parent": "all", "required": True, "puzzles": count}
            for theme, label, count, _ in THEMES
        ],
        "vocabulary": [
            # The words were generated by this script, which an AI model wrote.
            {"theme": theme, "source": "ai_generated", "entries": [{"word": w} for w in words]}
            for theme, words in pools.items()
        ],
        "puzzles": [
            {"id": pid, "theme": theme, "level": level, "title": title, "words": words}
            for pid, theme, level, title, words in puzzles
        ],
        "constraints": {"min_letters": 4, "max_letters": 15, "max_word_reuse": 2},
        "questions": [
            {
                "id": "q-comparables",
                "question": "SYNTHETIC: which comparable books has a person read?",
                "blocking": True,
            }
        ],
        "research": [],
        "comparables": [],
        "approval": None,
    }


def write_production_book(directory: Path | str) -> Path:
    """Write book.yaml and planning.yaml into `directory` (created) and return it."""
    target = Path(directory)
    target.mkdir(parents=True, exist_ok=True)
    project = validate_project(book_data()).require_project()
    (target / "book.yaml").write_text(dump_project(project), encoding="utf-8")
    plan, issues = validate_planning(plan_data())
    assert plan is not None, issues
    write_planning(target, plan, None)
    return target


if __name__ == "__main__":
    print(write_production_book(sys.argv[1]))
