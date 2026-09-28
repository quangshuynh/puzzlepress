"""Pure standalone word-search engine; no project schema or filesystem coupling."""

from .generation import generate_word_search
from .models import (
    ALPHABET,
    GENERATION_VERSION,
    Coordinate,
    Direction,
    GenerationConfig,
    GenerationStats,
    Grid,
    GridSize,
    Placement,
    Solution,
    Target,
    TargetEntry,
    VerificationResult,
    WordSearch,
    WordSearchError,
)
from .validation import normalize_targets
from .verification import verify_word_search

__all__ = [
    "ALPHABET",
    "GENERATION_VERSION",
    "Coordinate",
    "Direction",
    "GenerationConfig",
    "GenerationStats",
    "Grid",
    "GridSize",
    "Placement",
    "Solution",
    "Target",
    "TargetEntry",
    "VerificationResult",
    "WordSearch",
    "WordSearchError",
    "generate_word_search",
    "normalize_targets",
    "verify_word_search",
]
