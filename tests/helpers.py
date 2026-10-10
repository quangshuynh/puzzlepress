import sys
import sysconfig
from pathlib import Path


def installed_puzzlepress() -> Path:
    scripts_dir = Path(sysconfig.get_path("scripts"))
    executable = scripts_dir / ("puzzlepress.exe" if sys.platform == "win32" else "puzzlepress")

    assert executable.is_file(), f"Installed PuzzlePress console script not found: {executable}"

    return executable


ROOT = Path(__file__).resolve().parents[1]
DEMO = ROOT / "books" / "composition-demo"
CANONICAL_BOOKS = ("composition-demo", "cover-demo", "garden-demo", "publishing-demo")
# The tiny legacy schema-v1 source books/automotive once held. Byte-identical, so its
# pinned build identity is unchanged. Real books live in the puzzlepress-books repository.
LEGACY_FIXTURE = ROOT / "tests" / "fixtures" / "legacy-automotive"


def demo_variant(mutate=None, puzzles: int | None = None):
    """A validated composition-demo copy, optionally with more puzzles or edits."""
    from puzzlepress import load_project, validate_project

    data = load_project(DEMO).project.to_dict()
    if puzzles is not None:
        bank = [e["id"] for e in data["word_search"]["banks"][0]["entries"]]
        data["word_search"]["puzzles"] = [
            {
                "id": f"p{n}",
                "title": f"Puzzle {n}",
                "theme": "Variant",
                "bank": "seaside",
                "target_ids": [bank[(n + k) % len(bank)] for k in range(3)],
                "difficulty": "gentle" if n % 2 else "varied",
            }
            for n in range(1, puzzles + 1)
        ]
    if mutate is not None:
        mutate(data)
    return validate_project(data).require_project()
