"""Deterministic occurrence screening and transparent similarity measurements."""

from collections.abc import Sequence
from dataclasses import dataclass

from .errors import ValidationIssue
from .wordsearch import (
    ALPHABET,
    Coordinate,
    Direction,
    Grid,
    TargetEntry,
    WordSearch,
    WordSearchError,
    normalize_targets,
    verify_word_search,
)

MAX_SCAN_HITS = 1000
PathKey = tuple[tuple[int, int], ...]


@dataclass(frozen=True)
class Occurrence:
    word: str
    coordinates: tuple[Coordinate, ...]


@dataclass(frozen=True)
class ScanResult:
    occurrences: tuple[Occurrence, ...]
    truncated: bool = False


@dataclass(frozen=True)
class PuzzleQuality:
    accidental_targets: ScanResult
    prohibited: ScanResult
    prohibited_screening_enabled: bool = False


@dataclass(frozen=True)
class QualityFinding:
    code: str
    message: str
    puzzle_ids: tuple[str, ...]
    words: tuple[str, ...] = ()
    severity: str = "warning"


@dataclass(frozen=True)
class WordReuse:
    word: str
    puzzle_ids: tuple[str, ...]


@dataclass(frozen=True)
class PuzzleSimilarity:
    left_id: str
    right_id: str
    shared_words: tuple[str, ...]
    target_jaccard: float
    target_overlap: float
    identical_targets: bool
    grid_agreement: float | None


def _path_key(coordinates: tuple[Coordinate, ...]) -> PathKey:
    path = tuple((c.x, c.y) for c in coordinates)
    return min(path, tuple(reversed(path)))


def screen_words(grid: Grid, words: Sequence[str]) -> ScanResult:
    """Screen an explicit caller-supplied policy list; no built-in prohibited list.

    Finds contiguous straight-line occurrences in all eight directions. A
    palindrome/reversed traversal of the same cells counts once per word.
    Results are capped; truncated=True means screening is incomplete.
    """
    if isinstance(words, str):
        raise WordSearchError(
            (ValidationIssue("words", "type", "Pass a sequence of word strings, not one string."),)
        )
    if len(words) > 100:
        raise WordSearchError(
            (ValidationIssue("words", "count", "Use at most 100 screening words."),)
        )
    if not words:
        return _scan(grid, ())
    targets = normalize_targets(tuple(TargetEntry(str(i), word) for i, word in enumerate(words)))
    return _scan(grid, tuple(sorted(t.search for t in targets)))


def analyze_word_search(puzzle: WordSearch, prohibited_words: Sequence[str] = ()) -> PuzzleQuality:
    """Check a verified puzzle without altering its grid or authoritative solution."""
    verification = verify_word_search(puzzle)
    if not verification.valid:
        raise WordSearchError(verification.issues)
    authoritative = frozenset(
        (placement.search, _path_key(placement.coordinates))
        for placement in puzzle.solution.placements
    )
    accidental = _scan(puzzle.grid, tuple(t.search for t in puzzle.targets), authoritative)
    return PuzzleQuality(
        accidental, screen_words(puzzle.grid, prohibited_words), bool(prohibited_words)
    )


def _scan(
    grid: Grid, words: tuple[str, ...], excluded: frozenset[tuple[str, PathKey]] = frozenset()
) -> ScanResult:
    rows = grid.rows
    if (
        not 1 <= len(rows) <= 50
        or not 1 <= len(rows[0]) <= 50
        or any(len(row) != len(rows[0]) or any(c not in ALPHABET for c in row) for row in rows)
    ):
        raise WordSearchError(
            (ValidationIssue("grid", "grid", "Expected a 1..50 rectangular A-Z grid."),)
        )
    if not words:
        return ScanResult(())
    forms = set(words)
    prefixes = {word[:length] for word in words for length in range(1, len(word) + 1)}
    max_length = max(map(len, words))
    found: list[Occurrence] = []
    seen: set[tuple[str, PathKey]] = set()
    for y in range(len(rows)):
        for x in range(len(rows[0])):
            for direction in Direction:
                text = ""
                for offset in range(max_length):
                    cx, cy = x + offset * direction.dx, y + offset * direction.dy
                    if not (0 <= cy < len(rows) and 0 <= cx < len(rows[0])):
                        break
                    text += rows[cy][cx]
                    if text not in prefixes:
                        break
                    if text not in forms:
                        continue
                    coordinates = tuple(
                        Coordinate(x + i * direction.dx, y + i * direction.dy)
                        for i in range(offset + 1)
                    )
                    key = (text, _path_key(coordinates))
                    if key in seen or key in excluded:
                        continue
                    if len(found) == MAX_SCAN_HITS:
                        return ScanResult(tuple(found), truncated=True)
                    seen.add(key)
                    found.append(Occurrence(text, coordinates))
    return ScanResult(tuple(found))


def compare_target_sets(
    left_id: str,
    right_id: str,
    left: frozenset[str],
    right: frozenset[str],
    left_grid: Grid | None = None,
    right_grid: Grid | None = None,
) -> PuzzleSimilarity:
    """Jaccard, containment overlap, and same-position grid agreement (0..1).

    Inputs are normalized nonempty target sets. Grid agreement is unavailable
    for missing or differently sized grids. No rotation/translation invariance.
    """
    shared = left & right
    union = left | right
    agreement = None
    if (
        left_grid is not None
        and right_grid is not None
        and left_grid.rows
        and right_grid.rows
        and len(left_grid.rows) == len(right_grid.rows)
        and all(len(a) == len(b) for a, b in zip(left_grid.rows, right_grid.rows, strict=True))
    ):
        a, b = "".join(left_grid.rows), "".join(right_grid.rows)
        if a:
            agreement = sum(x == y for x, y in zip(a, b, strict=True)) / len(a)
    return PuzzleSimilarity(
        left_id,
        right_id,
        tuple(sorted(shared)),
        len(shared) / len(union) if union else 0.0,
        len(shared) / min(len(left), len(right)) if left and right else 0.0,
        bool(left) and left == right,
        agreement,
    )
