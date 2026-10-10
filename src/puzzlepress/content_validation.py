"""Schema-v1 optional word_search section, including reference and fit checks."""

import math
import re
from typing import cast

from .content import (
    MAX_BANK_ENTRIES,
    MAX_BANKS,
    MAX_BATCH_ATTEMPTS,
    MAX_PROFILES,
    MAX_PUZZLE_TARGETS,
    MAX_PUZZLES,
    DifficultyProfile,
    PuzzleDefinition,
    QualityConfig,
    WordBank,
    WordSearchContent,
)
from .errors import ValidationIssue
from .wordsearch.models import Direction, GenerationConfig, GridSize, TargetEntry, WordSearchError
from .wordsearch.validation import normalize_config, normalize_targets, validate_fit


class _Reader:
    def __init__(self) -> None:
        self.issues: list[ValidationIssue] = []

    def issue(self, path: str, code: str, message: str) -> None:
        self.issues.append(ValidationIssue(path, code, message))

    def mapping(self, value: object, path: str, fields: set[str]) -> dict[str, object]:
        if not isinstance(value, dict):
            self.issue(path, "type", "Expected a mapping.")
            return {}
        for key in sorted(value, key=str):
            if not isinstance(key, str) or key not in fields:
                self.issue(f"{path}.{key}", "unknown_field", "Unknown field.")
        return cast(dict[str, object], value)

    def sequence(self, value: object, path: str, maximum: int, minimum: int = 1) -> list[object]:
        if not isinstance(value, list) or not minimum <= len(value) <= maximum:
            self.issue(path, "count", f"Expected a list with {minimum}..{maximum} entries.")
            return []
        return cast(list[object], value)

    def text(self, value: object, path: str, identifier: bool = False) -> str:
        if (
            not isinstance(value, str)
            or not value.strip()
            or len(value) > 200
            or any(0xD800 <= ord(c) <= 0xDFFF for c in value)
        ):
            self.issue(path, "text", "Expected 1..200 characters of nonempty valid text.")
            return ""
        value = value.strip()
        if identifier and not re.fullmatch(r"[A-Za-z0-9_-]{1,64}", value):
            self.issue(path, "id", "Use 1..64 ASCII letters/digits/_/-.")
        return value

    def unique(self, ids: list[str], path: str) -> None:
        seen: set[str] = set()
        for index, identifier in enumerate(ids):
            if identifier in seen:
                self.issue(f"{path}.{index}", "duplicate_id", f"Duplicate ID: {identifier}.")
            seen.add(identifier)

    def engine_issues(
        self,
        error: WordSearchError,
        path: str,
        target_field: str = "target_ids",
        scalar_targets: bool = False,
    ) -> None:
        for issue in error.issues:
            parts = issue.path.split(".")
            if parts[0] == "config":
                parts = parts[1:]
            elif parts[0] == "targets":
                parts[0] = target_field
                if scalar_targets:
                    parts = parts[:2]
            self.issue(f"{path}.{'.'.join(parts)}", issue.code, issue.message)


def validate_word_search_content(
    value: object,
) -> tuple[WordSearchContent | None, tuple[ValidationIssue, ...]]:
    reader = _Reader()
    root = reader.mapping(value, "word_search", {"banks", "profiles", "puzzles", "quality"})
    banks = _banks(reader, root.get("banks"))
    profiles = _profiles(reader, root.get("profiles"))
    puzzles: list[PuzzleDefinition] = []
    for i, raw in enumerate(
        reader.sequence(root.get("puzzles"), "word_search.puzzles", MAX_PUZZLES)
    ):
        path = f"word_search.puzzles.{i}"
        data = reader.mapping(
            raw, path, {"id", "title", "theme", "bank", "target_ids", "difficulty"}
        )
        values = {
            key: reader.text(data.get(key), f"{path}.{key}", key not in ("title", "theme"))
            for key in ("id", "title", "theme", "bank", "difficulty")
        }
        target_ids = tuple(
            reader.text(item, f"{path}.target_ids.{j}", True)
            for j, item in enumerate(
                reader.sequence(data.get("target_ids"), f"{path}.target_ids", MAX_PUZZLE_TARGETS)
            )
        )
        reader.unique(list(target_ids), f"{path}.target_ids")
        definition = PuzzleDefinition(
            values["id"],
            values["title"],
            values["theme"],
            values["bank"],
            target_ids,
            values["difficulty"],
        )
        puzzles.append(definition)
        bank = next((b for b in banks if b.id == definition.bank), None)
        profile = next((p for p in profiles if p.id == definition.difficulty), None)
        if bank is None:
            reader.issue(f"{path}.bank", "reference", "Unknown or invalid word bank.")
        if profile is None:
            reader.issue(
                f"{path}.difficulty", "reference", "Unknown or invalid difficulty profile."
            )
        if bank is not None:
            entries = {entry.id: entry for entry in bank.entries}
            for j, target_id in enumerate(target_ids):
                if target_id not in entries:
                    reader.issue(
                        f"{path}.target_ids.{j}", "reference", f"Unknown target {target_id}."
                    )
            if profile is not None and target_ids and all(t in entries for t in target_ids):
                try:
                    targets = normalize_targets(tuple(entries[t] for t in target_ids))
                    validate_fit(targets, profile.config)
                except WordSearchError as error:
                    reader.engine_issues(error, path, scalar_targets=True)
    reader.unique([p.id for p in puzzles], "word_search.puzzles")
    budgets = {profile.id: profile.config.max_attempts for profile in profiles}
    work = sum(budgets.get(p.difficulty, 0) for p in puzzles)
    if work > MAX_BATCH_ATTEMPTS:
        reader.issue(
            "word_search.puzzles",
            "work_budget",
            f"The puzzles' profiles allow {work:,} candidate checks in total; a batch may "
            f"use at most {MAX_BATCH_ATTEMPTS:,}. Lower max_attempts or use fewer puzzles.",
        )
    quality = _quality(reader, root.get("quality", {}))
    if reader.issues:
        return None, tuple(reader.issues)
    return WordSearchContent(tuple(banks), tuple(profiles), tuple(puzzles), quality), ()


def _banks(reader: _Reader, raw: object) -> list[WordBank]:
    banks: list[WordBank] = []
    ids: list[str] = []
    for i, item in enumerate(reader.sequence(raw, "word_search.banks", MAX_BANKS)):
        path = f"word_search.banks.{i}"
        data = reader.mapping(item, path, {"id", "entries"})
        identifier = reader.text(data.get("id"), f"{path}.id", True)
        ids.append(identifier)
        entries: list[TargetEntry] = []
        for j, raw_entry in enumerate(
            reader.sequence(data.get("entries"), f"{path}.entries", MAX_BANK_ENTRIES)
        ):
            entry_path = f"{path}.entries.{j}"
            entry = reader.mapping(raw_entry, entry_path, {"id", "display"})
            entry_id = reader.text(entry.get("id"), f"{entry_path}.id", True)
            # Pass untrimmed display through the engine's exact ASCII policy.
            display = entry.get("display")
            entries.append(TargetEntry(entry_id, cast(str, display)))
        if entries:
            try:
                normalized = normalize_targets(entries)
                banks.append(
                    WordBank(identifier, tuple(TargetEntry(t.id, t.display) for t in normalized))
                )
            except WordSearchError as error:
                reader.engine_issues(error, path, "entries")
    reader.unique(ids, "word_search.banks")
    return banks


def _profiles(reader: _Reader, raw: object) -> list[DifficultyProfile]:
    profiles: list[DifficultyProfile] = []
    ids: list[str] = []
    for i, item in enumerate(reader.sequence(raw, "word_search.profiles", MAX_PROFILES)):
        path = f"word_search.profiles.{i}"
        data = reader.mapping(
            item, path, {"id", "width", "height", "directions", "max_restarts", "max_attempts"}
        )
        identifier = reader.text(data.get("id"), f"{path}.id", True)
        ids.append(identifier)
        directions: list[Direction] = []
        names = {d.name.lower().replace("_", "-"): d for d in Direction}
        for j, name in enumerate(reader.sequence(data.get("directions"), f"{path}.directions", 8)):
            if not isinstance(name, str) or name not in names:
                reader.issue(f"{path}.directions.{j}", "direction", "Unknown direction name.")
            else:
                directions.append(names[name])
        config = GenerationConfig(
            GridSize(cast(int, data.get("width")), cast(int, data.get("height"))),
            tuple(directions),
            cast(int, data.get("max_restarts", 20)),
            cast(int, data.get("max_attempts", 100_000)),
        )
        try:
            profiles.append(DifficultyProfile(identifier, normalize_config(config)))
        except WordSearchError as error:
            reader.engine_issues(error, path)
    reader.unique(ids, "word_search.profiles")
    return profiles


def _quality(reader: _Reader, raw: object) -> QualityConfig:
    path = "word_search.quality"
    data = reader.mapping(
        raw,
        path,
        {
            "max_word_reuse",
            "target_similarity_threshold",
            "grid_similarity_threshold",
            "prohibited_words",
        },
    )
    reuse = data.get("max_word_reuse", 2)
    if type(reuse) is not int or not 1 <= reuse <= 20:
        reader.issue(f"{path}.max_word_reuse", "range", "Use an integer 1..20.")
        reuse = 2
    thresholds: list[float] = []
    for key, default in (("target_similarity_threshold", 0.8), ("grid_similarity_threshold", 0.9)):
        value = data.get(key, default)
        if (
            type(value) not in (int, float)
            or not 0 < cast(float, value) <= 1
            or not math.isfinite(cast(float, value))
        ):
            reader.issue(
                f"{path}.{key}", "range", "Use a finite number greater than 0 and at most 1."
            )
            value = default
        thresholds.append(float(cast(float, value)))
    words = reader.sequence(data.get("prohibited_words", []), f"{path}.prohibited_words", 100, 0)
    prohibited: tuple[str, ...] = ()
    if words:
        try:
            prohibited = tuple(
                sorted(
                    t.search
                    for t in normalize_targets(
                        tuple(TargetEntry(str(i), cast(str, word)) for i, word in enumerate(words))
                    )
                )
            )
        except WordSearchError as error:
            reader.engine_issues(error, path, "prohibited_words", scalar_targets=True)
    return QualityConfig(reuse, thresholds[0], thresholds[1], prohibited)
