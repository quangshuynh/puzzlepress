"""Immutable word-search values. Coordinates are zero-based (column, row)."""

from dataclasses import dataclass
from enum import Enum

from ..errors import ValidationIssue

ALPHABET = "ABCDEFGHIJKLMNOPQRSTUVWXYZ"
GENERATION_VERSION = 1


class Direction(Enum):
    RIGHT = (1, 0)
    LEFT = (-1, 0)
    DOWN = (0, 1)
    UP = (0, -1)
    DOWN_RIGHT = (1, 1)
    DOWN_LEFT = (-1, 1)
    UP_RIGHT = (1, -1)
    UP_LEFT = (-1, -1)

    @property
    def dx(self) -> int:
        return self.value[0]

    @property
    def dy(self) -> int:
        return self.value[1]


@dataclass(frozen=True)
class Coordinate:
    x: int
    y: int


@dataclass(frozen=True)
class TargetEntry:
    id: str
    display: str


@dataclass(frozen=True)
class Target:
    id: str
    display: str
    search: str


@dataclass(frozen=True)
class GridSize:
    width: int
    height: int


@dataclass(frozen=True)
class GenerationConfig:
    size: GridSize
    directions: tuple[Direction, ...] = tuple(Direction)
    max_restarts: int = 20
    max_attempts: int = 100_000


@dataclass(frozen=True)
class Placement:
    target_id: str
    search: str
    start: Coordinate
    direction: Direction

    @property
    def coordinates(self) -> tuple[Coordinate, ...]:
        return tuple(
            Coordinate(self.start.x + i * self.direction.dx, self.start.y + i * self.direction.dy)
            for i in range(len(self.search))
        )

    @property
    def end(self) -> Coordinate:
        return Coordinate(
            self.start.x + (len(self.search) - 1) * self.direction.dx,
            self.start.y + (len(self.search) - 1) * self.direction.dy,
        )


@dataclass(frozen=True)
class Grid:
    rows: tuple[str, ...]


@dataclass(frozen=True)
class Solution:
    placements: tuple[Placement, ...]


@dataclass(frozen=True)
class GenerationStats:
    attempts: int
    restarts: int


@dataclass(frozen=True)
class WordSearch:
    targets: tuple[Target, ...]
    config: GenerationConfig
    seed: int
    grid: Grid
    solution: Solution
    stats: GenerationStats
    generation_version: int = GENERATION_VERSION


class WordSearchError(Exception):
    """Expected input or bounded search failure, suitable for any adapter."""

    def __init__(
        self, issues: tuple[ValidationIssue, ...], stats: GenerationStats | None = None
    ) -> None:
        self.issues = issues
        self.stats = stats
        super().__init__("; ".join(f"{issue.path}: {issue.message}" for issue in issues))


@dataclass(frozen=True)
class VerificationResult:
    issues: tuple[ValidationIssue, ...]

    @property
    def valid(self) -> bool:
        return not self.issues
