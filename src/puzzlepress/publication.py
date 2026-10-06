"""Deterministic logical publication plan. No layout, coordinates, fonts or files.

Each plan page is one logical page in reading order. Page 1 is recto. Structure
depends only on validated source; generation supplies puzzle digests and
completeness. Interval-7 renderers decide physical layout, not page membership.
"""

from dataclasses import dataclass
from enum import StrEnum

from .batch import BatchReport, generate_batch, puzzle_digest
from .composition import (
    Composition,
    MatterItem,
    MatterKind,
    NumberingScheme,
    SectionStart,
    SolutionPlacement,
)
from .errors import ProjectError, ValidationIssue
from .identity import build_identity
from .models import Project
from .validation import validate_project

PLAN_VERSION = 1
BLANK_REASON = "section_recto_start"


class Section(StrEnum):
    FRONT_MATTER = "front_matter"
    PUZZLES = "puzzles"
    SOLUTIONS = "solutions"
    BACK_MATTER = "back_matter"


class PageKind(StrEnum):
    TITLE_PAGE = "title_page"
    COPYRIGHT_PAGE = "copyright_page"
    INSTRUCTIONS = "instructions"
    ABOUT = "about"
    NOTES = "notes"
    PUZZLE = "puzzle"
    SOLUTIONS = "solutions"
    BLANK = "blank"


class Side(StrEnum):
    RECTO = "recto"
    VERSO = "verso"


class NumberStyle(StrEnum):
    ARABIC = "arabic"
    ROMAN = "roman"


def roman(value: int) -> str:
    if not 1 <= value <= 3999:
        raise ValueError("Roman page numbers support 1..3999")
    result = ""
    for amount, digits in (
        (1000, "m"),
        (900, "cm"),
        (500, "d"),
        (400, "cd"),
        (100, "c"),
        (90, "xc"),
        (50, "l"),
        (40, "xl"),
        (10, "x"),
        (9, "ix"),
        (5, "v"),
        (4, "iv"),
        (1, "i"),
    ):
        count, value = divmod(value, amount)
        result += digits * count
    return result


@dataclass(frozen=True)
class PageNumber:
    """Abstract folio: its value counts even when a renderer must not display it."""

    value: int
    style: NumberStyle
    displayed: bool

    @property
    def label(self) -> str:
        return roman(self.value) if self.style is NumberStyle.ROMAN else str(self.value)


@dataclass(frozen=True)
class MatterContent:
    title: str | None = None
    subtitle: str | None = None
    author: str | None = None
    imprint: str | None = None
    text: str | None = None


@dataclass(frozen=True)
class PuzzleRef:
    """Authoritative link to one generated puzzle; digest is None if generation failed."""

    id: str
    ordinal: int
    title: str
    theme: str
    seed: int
    digest: str | None


@dataclass(frozen=True)
class SolutionRef:
    puzzle: PuzzleRef
    puzzle_page: int


@dataclass(frozen=True)
class PlanPage:
    index: int
    section: Section
    kind: PageKind
    number: PageNumber
    heading: str | None = None
    matter: MatterContent | None = None
    puzzle: PuzzleRef | None = None
    solution_page: int | None = None
    solutions: tuple[SolutionRef, ...] = ()
    blank_reason: str | None = None
    blank_before: Section | None = None

    @property
    def side(self) -> Side:
        return Side.RECTO if self.index % 2 else Side.VERSO

    def to_dict(self) -> dict[str, object]:
        def ref(puzzle: PuzzleRef) -> dict[str, object]:
            return {
                "id": puzzle.id,
                "ordinal": puzzle.ordinal,
                "title": puzzle.title,
                "theme": puzzle.theme,
                "seed": str(puzzle.seed),
                "digest": puzzle.digest,
            }

        matter = self.matter
        return {
            "index": self.index,
            "side": self.side.value,
            "section": self.section.value,
            "kind": self.kind.value,
            "number": {
                "value": self.number.value,
                "style": self.number.style.value,
                "label": self.number.label,
                "displayed": self.number.displayed,
            },
            "heading": self.heading,
            "matter": None
            if matter is None
            else {
                "title": matter.title,
                "subtitle": matter.subtitle,
                "author": matter.author,
                "imprint": matter.imprint,
                "text": matter.text,
            },
            "puzzle": None if self.puzzle is None else ref(self.puzzle),
            "solution_page": self.solution_page,
            "solutions": [
                {"puzzle": ref(item.puzzle), "puzzle_page": item.puzzle_page}
                for item in self.solutions
            ],
            "blank": None
            if self.blank_reason is None
            else {
                "reason": self.blank_reason,
                "before_section": self.blank_before.value if self.blank_before else None,
            },
        }


@dataclass(frozen=True)
class PlanStatistics:
    """Logical counts only; physical page count is decided by a future renderer."""

    logical_pages: int
    front_matter_pages: int
    puzzle_pages: int
    solution_pages: int
    back_matter_pages: int
    blank_pages: int
    puzzles: int
    solutions: int
    first_puzzle_page: int | None
    first_solution_page: int | None


def plan_statistics(pages: tuple[PlanPage, ...]) -> PlanStatistics:
    def count(section: Section) -> int:
        return sum(p.section is section and p.kind is not PageKind.BLANK for p in pages)

    def first(kind: PageKind) -> int | None:
        return next((p.index for p in pages if p.kind is kind), None)

    return PlanStatistics(
        logical_pages=len(pages),
        front_matter_pages=count(Section.FRONT_MATTER),
        puzzle_pages=count(Section.PUZZLES),
        solution_pages=count(Section.SOLUTIONS),
        back_matter_pages=count(Section.BACK_MATTER),
        blank_pages=sum(p.kind is PageKind.BLANK for p in pages),
        puzzles=sum(p.puzzle is not None for p in pages),
        solutions=sum(len(p.solutions) for p in pages),
        first_puzzle_page=first(PageKind.PUZZLE),
        first_solution_page=first(PageKind.SOLUTIONS),
    )


@dataclass(frozen=True)
class PublicationPlan:
    identity: str
    book_id: str
    language: str
    pages: tuple[PlanPage, ...]
    statistics: PlanStatistics
    diagnostics: tuple[ValidationIssue, ...]
    plan_version: int = PLAN_VERSION

    @property
    def complete(self) -> bool:
        """Every planned puzzle and solution references a generated puzzle."""
        return not self.diagnostics

    def to_dict(self) -> dict[str, object]:
        stats = self.statistics
        return {
            "plan_version": self.plan_version,
            "identity": self.identity,
            "book_id": self.book_id,
            "language": self.language,
            "complete": self.complete,
            "pages": [page.to_dict() for page in self.pages],
            "statistics": {
                "logical_pages": stats.logical_pages,
                "front_matter_pages": stats.front_matter_pages,
                "puzzle_pages": stats.puzzle_pages,
                "solution_pages": stats.solution_pages,
                "back_matter_pages": stats.back_matter_pages,
                "blank_pages": stats.blank_pages,
                "puzzles": stats.puzzles,
                "solutions": stats.solutions,
                "first_puzzle_page": stats.first_puzzle_page,
                "first_solution_page": stats.first_solution_page,
            },
            "diagnostics": [
                {"path": d.path, "code": d.code, "message": d.message} for d in self.diagnostics
            ],
        }


def require_composition(project: Project) -> Composition:
    if project.composition is None or project.word_search is None:
        raise ProjectError(
            (
                ValidationIssue(
                    "composition",
                    "required",
                    "Project has no book composition. Add a composition section first.",
                ),
            )
        )
    return project.composition


def build_publication(project: Project) -> tuple[BatchReport, PublicationPlan]:
    """Validate, generate every puzzle, then plan. Neither step writes files."""
    project = validate_project(project.to_dict()).require_project()
    require_composition(project)
    report = generate_batch(project)
    return report, plan_publication(project, report)


def _matter(item: MatterItem, project: Project) -> MatterContent:
    if item.kind is MatterKind.TITLE_PAGE:
        book = project.book
        return MatterContent(book.title, book.subtitle, book.author, book.imprint)
    return MatterContent(title=item.title, text=item.text)


@dataclass(frozen=True)
class _Slot:
    section: Section
    kind: PageKind
    heading: str | None = None
    matter: MatterContent | None = None
    puzzle: PuzzleRef | None = None
    solutions: tuple[SolutionRef, ...] = ()
    blank_before: Section | None = None


def plan_publication(project: Project, report: BatchReport) -> PublicationPlan:
    """Plan validated source using the batch report generated from that same source."""
    project = validate_project(project.to_dict()).require_project()
    composition = require_composition(project)
    content = project.word_search
    if content is None:  # Guaranteed by require_composition.
        raise RuntimeError("Composition without word_search passed validation")
    identity = build_identity(project)
    if report.identity != identity or [r.id for r in report.puzzles] != [
        d.id for d in content.puzzles
    ]:
        raise ValueError("Batch report was not generated from this project source")

    # Pass 1: logical slots in reading order. Blanks only satisfy recto starts.
    slots: list[_Slot] = []

    def open_section(section: Section, start: SectionStart) -> None:
        if start is SectionStart.RECTO and len(slots) % 2 == 1:
            slots.append(_Slot(slots[-1].section, PageKind.BLANK, blank_before=section))

    for item in composition.front_matter:
        slots.append(
            _Slot(Section.FRONT_MATTER, PageKind(item.kind.value), matter=_matter(item, project))
        )
    open_section(Section.PUZZLES, composition.puzzles_start)
    diagnostics: list[ValidationIssue] = []
    refs: list[PuzzleRef] = []
    puzzle_pages: dict[str, int] = {}
    for ordinal, (definition, result) in enumerate(
        zip(content.puzzles, report.puzzles, strict=True), start=1
    ):
        if result.puzzle is None or result.errors:
            diagnostics.append(
                ValidationIssue(
                    f"word_search.puzzles.{ordinal - 1}",
                    "generation_failed",
                    f"Puzzle {definition.id} did not generate; its pages have no content.",
                )
            )
        ref = PuzzleRef(
            definition.id,
            ordinal,
            definition.title,
            definition.theme,
            result.seed,
            None if result.puzzle is None else puzzle_digest(result.puzzle),
        )
        refs.append(ref)
        slots.append(_Slot(Section.PUZZLES, PageKind.PUZZLE, puzzle=ref))
        puzzle_pages[ref.id] = len(slots)
    solution_pages: dict[str, int] = {}
    policy = composition.solutions
    if policy.placement is SolutionPlacement.END:
        open_section(Section.SOLUTIONS, policy.start)
        for offset in range(0, len(refs), policy.per_page):
            group = refs[offset : offset + policy.per_page]
            slots.append(
                _Slot(
                    Section.SOLUTIONS,
                    PageKind.SOLUTIONS,
                    heading=policy.title if offset == 0 else None,
                    solutions=tuple(SolutionRef(r, puzzle_pages[r.id]) for r in group),
                )
            )
            for r in group:
                solution_pages[r.id] = len(slots)
    for item in composition.back_matter:
        slots.append(
            _Slot(Section.BACK_MATTER, PageKind(item.kind.value), matter=_matter(item, project))
        )

    # Pass 2: abstract numbering and cross-references.
    numbers = composition.page_numbers
    roman_front = numbers.scheme is NumberingScheme.ROMAN_FRONT_MATTER
    front_count = sum(slot.section is Section.FRONT_MATTER for slot in slots)
    shown = {
        Section.FRONT_MATTER: numbers.show_front_matter,
        Section.PUZZLES: True,
        Section.SOLUTIONS: numbers.show_solutions,
        Section.BACK_MATTER: numbers.show_back_matter,
    }
    pages: list[PlanPage] = []
    for index, slot in enumerate(slots, start=1):
        in_front = slot.section is Section.FRONT_MATTER
        number = PageNumber(
            index - front_count if roman_front and not in_front else index,
            NumberStyle.ROMAN if roman_front and in_front else NumberStyle.ARABIC,
            slot.kind is not PageKind.BLANK and shown[slot.section],
        )
        pages.append(
            PlanPage(
                index=index,
                section=slot.section,
                kind=slot.kind,
                number=number,
                heading=slot.heading,
                matter=slot.matter,
                puzzle=slot.puzzle,
                solution_page=solution_pages.get(slot.puzzle.id) if slot.puzzle else None,
                solutions=slot.solutions,
                blank_reason=BLANK_REASON if slot.kind is PageKind.BLANK else None,
                blank_before=slot.blank_before,
            )
        )
    frozen = tuple(pages)
    return PublicationPlan(
        identity,
        project.book.id,
        project.book.language,
        frozen,
        plan_statistics(frozen),
        tuple(diagnostics),
    )
