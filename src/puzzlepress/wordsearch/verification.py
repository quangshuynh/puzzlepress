"""Check authoritative solutions independently of the placement implementation."""

from ..errors import ValidationIssue
from .models import (
    ALPHABET,
    GENERATION_VERSION,
    Direction,
    TargetEntry,
    VerificationResult,
    WordSearch,
    WordSearchError,
)
from .validation import normalize_config, normalize_seed, normalize_targets, validate_fit


def verify_word_search(puzzle: WordSearch) -> VerificationResult:
    """Check typed values, including deliberately corrupted result metadata.

    Targets embedded in the result are the requested manifest. This checks
    internal consistency, not authenticity against an external source or seed
    replay. No search for incidental occurrences is performed.
    """
    issues: list[ValidationIssue] = []
    try:
        config = normalize_config(puzzle.config)
        targets = normalize_targets(tuple(TargetEntry(t.id, t.display) for t in puzzle.targets))
        normalize_seed(puzzle.seed)
        validate_fit(targets, config)
    except WordSearchError as error:
        return VerificationResult(error.issues)
    if targets != puzzle.targets:
        issues.append(ValidationIssue("targets", "metadata", "Target normalization disagrees."))
    if puzzle.generation_version != GENERATION_VERSION:
        issues.append(ValidationIssue("generation_version", "version", "Unsupported generation."))
    width, height = config.size.width, config.size.height
    rows = puzzle.grid.rows
    if len(rows) != height or any(len(row) != width for row in rows):
        issues.append(
            ValidationIssue("grid", "dimensions", "Grid dimensions disagree with config.")
        )
    if any(letter not in ALPHABET for row in rows for letter in row):
        issues.append(ValidationIssue("grid", "alphabet", "Grid must contain only A-Z."))
    expected = {target.id: target for target in targets}
    seen: set[str] = set()
    occupied: dict[tuple[int, int], str] = {}
    for index, placement in enumerate(puzzle.solution.placements):
        path = f"solution.placements.{index}"
        target = expected.get(placement.target_id)
        if target is None:
            issues.append(ValidationIssue(path, "unknown_target", "Unknown target ID."))
        if placement.target_id in seen:
            issues.append(
                ValidationIssue(path, "duplicate_placement", "Target placed more than once.")
            )
        seen.add(placement.target_id)
        if target is None or target.search != placement.search:
            issues.append(ValidationIssue(path, "metadata", "Placement search form disagrees."))
        if (
            not isinstance(placement.direction, Direction)
            or placement.direction not in config.directions
        ):
            issues.append(ValidationIssue(path, "direction", "Direction is not enabled."))
            continue
        if type(placement.start.x) is not int or type(placement.start.y) is not int:
            issues.append(ValidationIssue(path, "coordinate", "Coordinates must be integers."))
            continue
        # Deliberately do not call Placement.coordinates, .end, or _can_place.
        dx, dy = placement.direction.value
        for offset, letter in enumerate(placement.search):
            x = placement.start.x + offset * dx
            y = placement.start.y + offset * dy
            if not (0 <= x < width and 0 <= y < height):
                issues.append(ValidationIssue(path, "bounds", "Placement leaves the grid."))
                break
            if y >= len(rows) or x >= len(rows[y]) or rows[y][x] != letter:
                issues.append(ValidationIssue(path, "spelling", "Grid disagrees with placement."))
                break
            if (x, y) in occupied and occupied[x, y] != letter:
                issues.append(ValidationIssue(path, "overlap", "Overlapping letters conflict."))
            occupied[x, y] = letter
    for target in targets:
        if target.id not in seen:
            issues.append(
                ValidationIssue("solution", "missing_target", f"Missing target {target.id}.")
            )
    return VerificationResult(tuple(issues))
