"""Candidate vocabulary through the generator's own normalization rules.

Each authored word is passed to `wordsearch.normalize_targets` exactly as the
project schema would pass a bank entry, so "valid" here means what it means in
production: ASCII letters and spaces, at most 50 letters once spaces are
removed. Invalid words stay in the plan and become findings; nothing is
transliterated, trimmed of punctuation or replaced.
"""

from dataclasses import dataclass

from ..wordsearch import TargetEntry, WordSearchError, normalize_targets
from .model import PlanningDocument, Pool, WordSource


@dataclass(frozen=True)
class WordInfo:
    theme: str
    index: int
    word: str
    source: WordSource
    search: str | None  # Normalized search form; None when the engine rejects the word.
    problem: str | None = None  # The engine's message for an invalid word.
    duplicate_of: int | None = None  # Earlier entry in the same pool with this search form.

    @property
    def usable(self) -> bool:
        return self.search is not None and self.duplicate_of is None


@dataclass(frozen=True)
class PoolInfo:
    pool: Pool
    path: str
    words: tuple[WordInfo, ...]

    @property
    def forms(self) -> tuple[str, ...]:
        """Distinct valid search forms in authored order."""
        return tuple(w.search for w in self.words if w.usable and w.search is not None)

    def by_text(self) -> dict[str, WordInfo]:
        found: dict[str, WordInfo] = {}
        for info in self.words:
            found.setdefault(info.word, info)
        return found


def search_form(word: str) -> tuple[str | None, str | None]:
    """(search form, None) for a valid word, or (None, the engine's message)."""
    try:
        (target,) = normalize_targets((TargetEntry("word", word),))
    except WordSearchError as error:
        return None, error.issues[0].message
    return target.search, None


def analyze_pools(document: PlanningDocument) -> tuple[PoolInfo, ...]:
    pools: list[PoolInfo] = []
    for i, pool in enumerate(document.vocabulary):
        seen: dict[str, int] = {}
        words: list[WordInfo] = []
        for j, entry in enumerate(pool.entries):
            search, problem = search_form(entry.word)
            duplicate = seen.get(search) if search is not None else None
            if search is not None and duplicate is None:
                seen[search] = j
            words.append(
                WordInfo(
                    pool.theme, j, entry.word, pool.source_of(entry), search, problem, duplicate
                )
            )
        pools.append(PoolInfo(pool, f"vocabulary.{i}", tuple(words)))
    return tuple(pools)
