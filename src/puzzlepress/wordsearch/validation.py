"""Input policy for the standalone engine, independent of project schema v1."""

import re
from collections.abc import Sequence
from dataclasses import replace

from ..errors import MAX_SEED, ValidationIssue
from .models import Direction, GenerationConfig, Target, TargetEntry, WordSearchError

# Engine input limits (docs/word-search.md).
MAX_TARGETS = 100
MAX_SEARCH_LETTERS = 50
MAX_GRID_SIDE = 50


def normalize_targets(entries: Sequence[TargetEntry]) -> tuple[Target, ...]:
    """Preserve display casing/spacing except edge ASCII spaces; grid uses A-Z.

    Only ASCII letters and literal spaces are accepted. Spaces are removed from
    search forms. IDs and normalized search forms must both be unique.
    """
    issues: list[ValidationIssue] = []
    targets: list[Target] = []
    ids: set[str] = set()
    forms: set[str] = set()
    if not 1 <= len(entries) <= MAX_TARGETS:
        raise WordSearchError(
            (ValidationIssue("targets", "count", f"Use 1..{MAX_TARGETS} targets."),)
        )
    for index, entry in enumerate(entries):
        path = f"targets.{index}"
        if not isinstance(entry.id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", entry.id):
            issues.append(
                ValidationIssue(f"{path}.id", "id", "Use 1..64 ASCII letters/digits/_/-.")
            )
        elif entry.id in ids:
            issues.append(
                ValidationIssue(f"{path}.id", "duplicate_id", "Target IDs must be unique.")
            )
        else:
            ids.add(entry.id)
        if (
            not isinstance(entry.display, str)
            or not 1 <= len(entry.display) <= 200
            or not re.fullmatch(r"[A-Za-z ]+", entry.display)
        ):
            issues.append(
                ValidationIssue(
                    f"{path}.display", "characters", "Use 1..200 ASCII letters and spaces only."
                )
            )
            continue
        display = entry.display.strip(" ")
        search = display.replace(" ", "").upper()
        if not search:
            issues.append(ValidationIssue(f"{path}.display", "empty", "A target needs letters."))
        elif len(search) > MAX_SEARCH_LETTERS:
            issues.append(
                ValidationIssue(
                    f"{path}.display", "length", f"Use at most {MAX_SEARCH_LETTERS} letters."
                )
            )
        elif search in forms:
            issues.append(
                ValidationIssue(
                    f"{path}.display", "duplicate_search", "Search forms must be unique."
                )
            )
        else:
            forms.add(search)
            targets.append(Target(entry.id, display, search))
    if issues:
        raise WordSearchError(tuple(issues))
    return tuple(targets)


def normalize_config(config: GenerationConfig) -> GenerationConfig:
    issues: list[ValidationIssue] = []
    for name, value, low, high in (
        ("width", config.size.width, 1, MAX_GRID_SIDE),
        ("height", config.size.height, 1, MAX_GRID_SIDE),
        ("max_restarts", config.max_restarts, 0, 100),
        ("max_attempts", config.max_attempts, 1, 1_000_000),
    ):
        if type(value) is not int or not low <= value <= high:
            issues.append(
                ValidationIssue(f"config.{name}", "range", f"Use an integer {low}..{high}.")
            )
    if (
        not config.directions
        or any(not isinstance(direction, Direction) for direction in config.directions)
        or len(set(config.directions)) != len(config.directions)
    ):
        issues.append(
            ValidationIssue("config.directions", "directions", "Enable distinct Direction values.")
        )
    if issues:
        raise WordSearchError(tuple(issues))
    # Caller ordering is not a semantic input. Always use declaration order.
    return replace(config, directions=tuple(d for d in Direction if d in config.directions))


def normalize_seed(seed: int | str) -> int:
    if isinstance(seed, str) and re.fullmatch(r"[0-9]+", seed.strip()):
        digits = seed.strip().lstrip("0") or "0"
        seed = int(digits) if len(digits) <= 20 else MAX_SEED + 1
    if type(seed) is not int or not 0 <= seed <= MAX_SEED:
        raise WordSearchError(
            (
                ValidationIssue(
                    "seed", "seed", f"Use an integer or decimal string in 0..{MAX_SEED}."
                ),
            )
        )
    return seed


def validate_fit(targets: tuple[Target, ...], config: GenerationConfig) -> None:
    issues = tuple(
        ValidationIssue(
            f"targets.{i}", "cannot_fit", f"{target.id}: target cannot fit any enabled direction."
        )
        for i, target in enumerate(targets)
        if not any(
            (d.dx == 0 or len(target.search) <= config.size.width)
            and (d.dy == 0 or len(target.search) <= config.size.height)
            for d in config.directions
        )
    )
    if issues:
        raise WordSearchError(issues)
