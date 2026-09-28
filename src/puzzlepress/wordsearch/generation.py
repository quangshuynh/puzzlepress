"""Bounded greedy placement with deterministic restarts and local randomness."""

from collections.abc import Sequence
from random import Random

from ..validation import ValidationIssue
from .models import (
    ALPHABET,
    Coordinate,
    GenerationConfig,
    GenerationStats,
    Grid,
    Placement,
    Solution,
    TargetEntry,
    WordSearch,
    WordSearchError,
)
from .validation import normalize_config, normalize_seed, normalize_targets, validate_fit


def _can_place(cells: list[list[str]], placement: Placement) -> bool:
    """An empty cell or the same letter may be shared, never a conflict."""
    width, height = len(cells[0]), len(cells)
    end = placement.end
    if not (
        0 <= placement.start.x < width
        and 0 <= placement.start.y < height
        and 0 <= end.x < width
        and 0 <= end.y < height
    ):
        return False
    return all(
        cells[c.y][c.x] in ("", letter)
        for c, letter in zip(placement.coordinates, placement.search, strict=True)
    )


def generate_word_search(
    entries: Sequence[TargetEntry], config: GenerationConfig, seed: int | str
) -> WordSearch:
    """Generate all targets or raise WordSearchError; no I/O or global RNG use.

    max_attempts is a total candidate-check budget across all restarts, including
    out-of-bounds candidates. max_restarts excludes the initial empty-grid pass.
    Exhaustion does not prove that no arrangement exists.
    """
    targets = normalize_targets(entries)
    config = normalize_config(config)
    seed = normalize_seed(seed)
    validate_fit(targets, config)
    rng = Random(seed)
    width, height = config.size.width, config.size.height
    attempts = 0
    for restart in range(config.max_restarts + 1):
        cells = [[""] * width for _ in range(height)]
        order = list(targets)
        rng.shuffle(order)
        order.sort(key=lambda target: -len(target.search))
        placements: dict[str, Placement] = {}
        for target in order:
            candidates = list(range(width * height * len(config.directions)))
            rng.shuffle(candidates)
            for candidate in candidates:
                if attempts >= config.max_attempts:
                    raise _exhausted(attempts, restart)
                attempts += 1
                cell, direction_index = divmod(candidate, len(config.directions))
                y, x = divmod(cell, width)
                placement = Placement(
                    target.id, target.search, Coordinate(x, y), config.directions[direction_index]
                )
                if _can_place(cells, placement):
                    for coordinate, letter in zip(
                        placement.coordinates, target.search, strict=True
                    ):
                        cells[coordinate.y][coordinate.x] = letter
                    placements[target.id] = placement
                    break
            else:
                break
        else:
            rows = tuple("".join(letter or rng.choice(ALPHABET) for letter in row) for row in cells)
            return WordSearch(
                targets,
                config,
                seed,
                Grid(rows),
                Solution(tuple(placements[target.id] for target in targets)),
                GenerationStats(attempts, restart),
            )
    raise _exhausted(attempts, config.max_restarts)


def _exhausted(attempts: int, restarts: int) -> WordSearchError:
    return WordSearchError(
        (
            ValidationIssue(
                "generation",
                "search_exhausted",
                "Could not place every target within the search limits. "
                "Try a different seed, larger grid, more directions, or higher limits.",
            ),
        ),
        GenerationStats(attempts, restarts),
    )
