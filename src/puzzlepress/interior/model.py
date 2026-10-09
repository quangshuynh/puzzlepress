"""Immutable physical layout model consumed by the PDF renderer.

Coordinates are PDF points with the origin at the bottom-left corner of the
trim box and y increasing upward. The layout engine decides every position;
the renderer draws exactly these elements and nothing else.
"""

from dataclasses import dataclass
from enum import StrEnum

from .issues import LayoutIssue
from .spec import PrintSpecification


@dataclass(frozen=True)
class Box:
    x: float
    y: float
    width: float
    height: float

    @property
    def right(self) -> float:
        return self.x + self.width

    @property
    def top(self) -> float:
        return self.y + self.height

    def expanded(self, margin: float) -> "Box":
        return Box(
            self.x - margin, self.y - margin, self.width + 2 * margin, self.height + 2 * margin
        )

    def contains(self, other: "Box", tolerance: float) -> bool:
        return (
            other.x >= self.x - tolerance
            and other.y >= self.y - tolerance
            and other.right <= self.right + tolerance
            and other.top <= self.top + tolerance
        )

    def overlaps(self, other: "Box", tolerance: float) -> bool:
        return (
            self.x < other.right - tolerance
            and other.x < self.right - tolerance
            and self.y < other.top - tolerance
            and other.y < self.top - tolerance
        )


class Face(StrEnum):
    REGULAR = "regular"
    BOLD = "bold"
    ITALIC = "italic"


class Anchor(StrEnum):
    START = "start"
    MIDDLE = "middle"
    END = "end"


@dataclass(frozen=True)
class TextLine:
    """One measured line. `bounds` covers the font's full ascent and descent."""

    role: str
    text: str
    face: Face
    size: float
    x: float
    baseline: float
    anchor: Anchor
    bounds: Box
    gray: float = 0.0  # DeviceGray ink: 0 is black.


@dataclass(frozen=True)
class Rule:
    role: str
    x1: float
    y1: float
    x2: float
    y2: float
    width: float
    bounds: Box
    gray: float = 0.0


@dataclass(frozen=True)
class SolutionMark:
    """A capsule outline joining the centers of a target's first and last cells."""

    target_id: str
    start: tuple[float, float]
    end: tuple[float, float]
    radius: float
    line_width: float


@dataclass(frozen=True)
class LetterGrid:
    """Authoritative letters drawn centered in square cells; row 0 is the top row."""

    role: str
    rows: tuple[str, ...]
    origin_x: float  # Left edge of the cell area.
    top: float  # Top edge of the cell area.
    cell: float
    letter_size: float
    face: Face
    frame: Box
    frame_width: float
    baseline_offset: float  # Center-to-baseline distance for capital letters.
    emphasized: frozenset[tuple[int, int]] = frozenset()  # (column, row) cells.
    emphasized_face: Face = Face.BOLD
    muted_gray: float = 0.0  # Gray for letters outside `emphasized` when marks exist.
    marks: tuple[SolutionMark, ...] = ()

    @property
    def columns(self) -> int:
        return len(self.rows[0]) if self.rows else 0

    def center(self, column: int, row: int) -> tuple[float, float]:
        return (
            self.origin_x + (column + 0.5) * self.cell,
            self.top - (row + 0.5) * self.cell,
        )

    @property
    def bounds(self) -> Box:
        """Painted extent: the frame stroke is centered, so half of it lies outside."""
        return self.frame.expanded(self.frame_width / 2)


Element = TextLine | Rule | LetterGrid


@dataclass(frozen=True)
class PageFrame:
    """Media, trim and live (content) boxes for one physical page."""

    media: Box
    trim: Box
    content: Box
    recto: bool


@dataclass(frozen=True)
class PhysicalPage:
    number: int  # 1-based physical PDF page.
    plan_index: int
    kind: str
    frame: PageFrame
    elements: tuple[Element, ...]
    folio: str | None  # Displayed label, exactly as the plan states it.


@dataclass(frozen=True)
class InteriorLayout:
    spec: PrintSpecification
    book_id: str
    identity: str
    plan_digest: str
    pages: tuple[PhysicalPage, ...]
    warnings: tuple[LayoutIssue, ...]
