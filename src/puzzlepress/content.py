"""Reusable authored word banks, explicit difficulty profiles, and puzzle definitions."""

from dataclasses import asdict, dataclass

from .wordsearch.models import GenerationConfig, TargetEntry

PIPELINE_VERSION = 1
# Schema caps for a project's word_search section; planning reports a larger plan
# against them rather than changing them (docs/book-planning.md). 100 puzzles were
# verified through generation, interior, preflight, cover and publishing
# (docs/production-scale.md#generator-scaling).
MAX_BANKS = 20
MAX_BANK_ENTRIES = 100
MAX_PROFILES = 20
MAX_PUZZLES = 100
MAX_PUZZLE_TARGETS = 100
# Worst-case generation work for a whole batch: the sum of every puzzle's profile
# max_attempts. It equals the bound before the cap was raised (20 puzzles x the
# 1,000,000-attempt maximum), so raising the puzzle cap never raises worst-case work.
MAX_BATCH_ATTEMPTS = 20_000_000


@dataclass(frozen=True)
class WordBank:
    id: str
    entries: tuple[TargetEntry, ...]


@dataclass(frozen=True)
class DifficultyProfile:
    """Named generation settings, not an empirical difficulty score."""

    id: str
    config: GenerationConfig


@dataclass(frozen=True)
class PuzzleDefinition:
    id: str
    title: str
    theme: str
    bank: str
    target_ids: tuple[str, ...]
    difficulty: str


@dataclass(frozen=True)
class QualityConfig:
    max_word_reuse: int = 2
    target_similarity_threshold: float = 0.8
    grid_similarity_threshold: float = 0.9
    prohibited_words: tuple[str, ...] = ()


@dataclass(frozen=True)
class WordSearchContent:
    banks: tuple[WordBank, ...]
    profiles: tuple[DifficultyProfile, ...]
    puzzles: tuple[PuzzleDefinition, ...]
    quality: QualityConfig = QualityConfig()

    def to_dict(self) -> dict[str, object]:
        return {
            "banks": [
                {"id": bank.id, "entries": [asdict(entry) for entry in bank.entries]}
                for bank in self.banks
            ],
            "profiles": [
                {
                    "id": profile.id,
                    "width": profile.config.size.width,
                    "height": profile.config.size.height,
                    "directions": [
                        d.name.lower().replace("_", "-") for d in profile.config.directions
                    ],
                    "max_restarts": profile.config.max_restarts,
                    "max_attempts": profile.config.max_attempts,
                }
                for profile in self.profiles
            ],
            "puzzles": [
                {**asdict(puzzle), "target_ids": list(puzzle.target_ids)} for puzzle in self.puzzles
            ],
            "quality": {
                **asdict(self.quality),
                "prohibited_words": list(self.quality.prohibited_words),
            },
        }

    def entries_for(self, definition: PuzzleDefinition) -> tuple[TargetEntry, ...]:
        bank = next(bank for bank in self.banks if bank.id == definition.bank)
        entries = {entry.id: entry for entry in bank.entries}
        return tuple(entries[target_id] for target_id in definition.target_ids)

    def config_for(self, definition: PuzzleDefinition) -> GenerationConfig:
        return next(
            profile.config for profile in self.profiles if profile.id == definition.difficulty
        )
