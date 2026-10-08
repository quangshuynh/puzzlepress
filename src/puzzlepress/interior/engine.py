"""Layout engine: verified PublicationPlan + batch report + print spec -> InteriorLayout.

One physical page per plan entry, in plan order. The engine decides positions
only. It never reorders, omits, inserts, regroups or repaginates entries, and it
rejects content that does not fit instead of shrinking it below profile limits.
"""

import hashlib
import json
import math
from collections.abc import Callable
from dataclasses import dataclass, field

from ..batch import BatchReport, puzzle_digest
from ..publication import PageKind, PlanPage, PublicationPlan
from ..wordsearch import WordSearch, verify_word_search
from .fonts import ASCENT, CAP_HEIGHT, DESCENT, missing_characters, text_width
from .geometry import (
    SOLUTION_TEMPLATES,
    GridGeometry,
    fit_grid,
    max_cell_for_letter,
    page_frame,
    solution_slots,
    solution_template,
)
from .issues import InteriorError, LayoutIssue
from .model import (
    Anchor,
    Box,
    Element,
    Face,
    InteriorLayout,
    LetterGrid,
    PageFrame,
    PhysicalPage,
    Rule,
    SolutionMark,
)
from .spec import KDP, FolioPlacement, PrintSpecification, to_inches, validate_print_spec
from .text import text_line, wrap_text

# 2: grid frames fit their region by painted extent (frame plus half its stroke).
RENDERER_VERSION = 2

# Template spacing (points). Changing any value changes output: bump RENDERER_VERSION.
FOLIO_BAND = 24.0  # Reserved at the bottom of every live area for the page number.
TEXT_MEASURE = 396.0  # 5.5 in reading measure for running text.
HEADING_GAP = 24.0
WORD_GAP = 22.0  # Between a puzzle grid's painted frame and its word list.
WORD_COLUMN_GAP = 36.0
MAX_WORD_COLUMNS = 5
WORD_LEADING = 1.5
SOLUTION_GAP_X = 24.0
SOLUTION_GAP_Y = 20.0
CAPTION_GAP = 6.0
NOTES_SPACING = 27.0
MARK_RADIUS = 0.4  # Capsule radius as a fraction of one cell.
MUTED_GRAY = 0.55  # Non-solution letters on solution pages.
NOTES_GRAY = 0.6
LABEL_GRAY = 0.35


def plan_digest(plan: PublicationPlan) -> str:
    material = json.dumps(
        plan.to_dict(), sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False
    ).encode("ascii")
    return "sha256-" + hashlib.sha256(material).hexdigest()


def verify_puzzle_bindings(
    plan: PublicationPlan, report: BatchReport
) -> tuple[dict[str, WordSearch], tuple[LayoutIssue, ...]]:
    """Bind every planned puzzle and solution to generated content by digest.

    Puzzle IDs alone are never trusted. Nothing is regenerated.
    """
    issues: list[LayoutIssue] = []
    if not plan.complete:
        issues.extend(
            LayoutIssue("incomplete_plan", d.message, region=d.path) for d in plan.diagnostics
        )
    if report.identity != plan.identity:
        issues.append(
            LayoutIssue(
                "identity_mismatch",
                "Batch report and plan come from different sources.",
                actual=report.identity,
                required=plan.identity,
            )
        )
    results = {result.id: result for result in report.puzzles}
    bound: dict[str, WordSearch] = {}
    for page in plan.pages:
        refs = [page.puzzle] if page.puzzle else [item.puzzle for item in page.solutions]
        for ref in refs:

            def fail(
                code: str,
                message: str,
                actual: str | None = None,
                required: str | None = None,
                page: PlanPage = page,
                subject: str = ref.id,
            ) -> None:
                issues.append(
                    LayoutIssue(
                        code,
                        message,
                        page=page.index,
                        kind=str(page.kind),
                        subject=subject,
                        actual=actual,
                        required=required,
                    )
                )

            result = results.get(ref.id)
            if result is None or result.puzzle is None or result.errors:
                fail("missing_puzzle", "No generated puzzle for entry.")
                continue
            actual = puzzle_digest(result.puzzle)
            if ref.digest != actual:
                fail(
                    "digest_mismatch",
                    "Generated puzzle content differs from the plan's digest.",
                    actual,
                    ref.digest,
                )
                continue
            if ref.id not in bound:
                if not verify_word_search(result.puzzle).valid:
                    fail("solution_invalid", "Generated solution failed independent verification.")
                    continue
                bound[ref.id] = result.puzzle
    return bound, tuple(issues)


def page_count_checks(
    spec: PrintSpecification, page_count: int
) -> tuple[tuple[LayoutIssue, ...], tuple[LayoutIssue, ...]]:
    """(errors, warnings) for the physical page count: gutter and KDP page limits."""
    errors: list[LayoutIssue] = []
    warnings: list[LayoutIssue] = []
    required = KDP.required_gutter(page_count)
    if required is None:
        errors.append(
            LayoutIssue(
                "page_count_unsupported",
                "Page count exceeds the KDP gutter table.",
                actual=str(page_count),
                required=f"at most {KDP.max_pages}",
            )
        )
    elif spec.margins.inside < required - 1e-6:
        errors.append(
            LayoutIssue(
                "gutter_too_small",
                f"Inside margin is below the KDP gutter for {page_count} pages.",
                region="print.margins.inside",
                actual=f"{to_inches(spec.margins.inside):.4g} in",
                required=f"{to_inches(required):.4g} in",
            )
        )
    if page_count < KDP.min_pages:
        warnings.append(
            LayoutIssue(
                "kdp_minimum_page_count",
                "KDP paperbacks need at least 24 pages; the plan, not the renderer, "
                "owns page count.",
                actual=str(page_count),
                required=f"at least {KDP.min_pages}",
            )
        )
    return tuple(errors), tuple(warnings)


@dataclass
class _Page:
    """Mutable per-page accumulator; frozen into a PhysicalPage when complete."""

    spec: PrintSpecification
    plan_page: PlanPage
    number: int
    frame: PageFrame
    elements: list[Element] = field(default_factory=list)
    issues: list[LayoutIssue] = field(default_factory=list)

    @property
    def body(self) -> Box:
        content = self.frame.content
        return Box(content.x, content.y + FOLIO_BAND, content.width, content.height - FOLIO_BAND)

    @property
    def center_x(self) -> float:
        return self.frame.content.x + self.frame.content.width / 2

    def issue(self, code: str, message: str, **context: str | None) -> None:
        subject = context.pop("subject", None)
        if subject is None and self.plan_page.puzzle is not None:
            subject = self.plan_page.puzzle.id
        self.issues.append(
            LayoutIssue(
                code,
                message,
                page=self.plan_page.index,
                physical_page=self.number,
                kind=str(self.plan_page.kind),
                subject=subject,
                **context,
            )
        )

    def check_glyphs(self, text: str, face: Face, region: str) -> None:
        missing = missing_characters(text, face)
        if missing:
            self.issue(
                "unsupported_character",
                "The bundled font cannot draw these characters.",
                region=region,
                actual=" ".join(f"U+{ord(c):04X}" for c in missing),
            )

    def line(
        self,
        role: str,
        text: str,
        face: Face,
        size: float,
        x: float,
        baseline: float,
        anchor: Anchor = Anchor.START,
        gray: float = 0.0,
    ) -> None:
        self.check_glyphs(text, face, role)
        self.elements.append(text_line(role, text, face, size, x, baseline, anchor, gray))

    def block(
        self,
        role: str,
        text: str,
        face: Face,
        size: float,
        leading: float,
        measure: Box,
        top: float,
        anchor: Anchor,
    ) -> float:
        """Place wrapped text from `top` downward; return the block's bottom edge."""
        wrapped = wrap_text(text, face, size, measure.width)
        if wrapped.overflow_word is not None:
            self.issue(
                "text_overflow",
                "A word is wider than the available measure.",
                region=role,
                actual=f"{wrapped.overflow_width:.2f} pt",
                required=f"at most {measure.width:.2f} pt",
            )
            return top
        x = {
            Anchor.START: measure.x,
            Anchor.MIDDLE: measure.x + measure.width / 2,
            Anchor.END: measure.right,
        }[anchor]
        baseline = top - ASCENT * size
        for index, text_value in enumerate(wrapped.lines):
            if index:
                baseline -= leading
            if text_value:
                self.line(role, text_value, face, size, x, baseline, anchor)
        return baseline - DESCENT * size

    def require_within(self, role: str, bottom: float, floor: float, height: float) -> None:
        if bottom < floor - 1e-6:
            self.issue(
                "text_overflow",
                "Text does not fit its region.",
                region=role,
                actual=f"{height + (floor - bottom):.2f} pt tall",
                required=f"at most {height:.2f} pt",
            )

    def freeze(self) -> PhysicalPage:
        number = self.plan_page.number
        return PhysicalPage(
            number=self.number,
            plan_index=self.plan_page.index,
            kind=str(self.plan_page.kind),
            frame=self.frame,
            elements=tuple(self.elements),
            folio=number.label if number.displayed else None,
        )


def layout_interior(
    plan: PublicationPlan, report: BatchReport, spec: PrintSpecification
) -> InteriorLayout:
    """Lay out a plan that `verify_publication_plan` has already accepted.

    Raises InteriorError with every collected diagnostic when the print spec is
    invalid, content is not bound to the plan, or any element does not fit.
    """
    spec_issues = validate_print_spec(spec)
    if spec_issues:
        raise InteriorError("print_spec", spec_issues)
    puzzles, binding_issues = verify_puzzle_bindings(plan, report)
    if binding_issues:
        raise InteriorError("integrity", binding_issues)
    count_errors, warnings = page_count_checks(spec, len(plan.pages))
    if count_errors:
        raise InteriorError("layout", count_errors)

    # One template for the whole book, from the plan's largest group; never regrouped.
    largest = max((len(p.solutions) for p in plan.pages), default=0)
    if largest > max(SOLUTION_TEMPLATES):
        raise InteriorError(
            "layout",
            (
                LayoutIssue(
                    "unsupported_solution_density",
                    "No solution page template holds this many solutions.",
                    actual=str(largest),
                    required=f"at most {max(SOLUTION_TEMPLATES)}",
                ),
            ),
        )
    density = solution_template(largest) if largest else 1
    renderers: dict[PageKind, Callable[[_Page], None]] = {
        PageKind.TITLE_PAGE: _title_page,
        PageKind.COPYRIGHT_PAGE: _copyright_page,
        PageKind.INSTRUCTIONS: _text_page,
        PageKind.ABOUT: _text_page,
        PageKind.NOTES: _notes_page,
        PageKind.PUZZLE: lambda page: _puzzle_page(page, puzzles),
        PageKind.SOLUTIONS: lambda page: _solution_page(page, puzzles, plan, density),
        PageKind.BLANK: lambda page: None,
    }
    pages: list[PhysicalPage] = []
    issues: list[LayoutIssue] = []
    for position, plan_page in enumerate(plan.pages):
        page = _Page(spec, plan_page, position + 1, page_frame(spec, position + 1))
        if plan_page.index != page.number:
            page.issue("plan_order", "Plan indexes must equal physical page order.")
        renderer = renderers.get(plan_page.kind)
        if renderer is None:
            page.issue("unsupported_page_type", "The renderer cannot draw this entry kind.")
        else:
            renderer(page)
            if plan_page.number.displayed:
                _folio(page)
        issues.extend(page.issues)
        pages.append(page.freeze())
    if issues:
        raise InteriorError("layout", tuple(issues))
    return InteriorLayout(
        spec=spec,
        book_id=plan.book_id,
        identity=plan.identity,
        plan_digest=plan_digest(plan),
        pages=tuple(pages),
        warnings=warnings,
    )


def _folio(page: _Page) -> None:
    size = page.spec.typography.folio
    content = page.frame.content
    baseline = content.y + DESCENT * size
    if page.spec.folio_placement is FolioPlacement.CENTER:
        x, anchor = page.center_x, Anchor.MIDDLE
    elif page.frame.recto:
        x, anchor = content.right, Anchor.END
    else:
        x, anchor = content.x, Anchor.START
    page.line("folio", page.plan_page.number.label, Face.REGULAR, size, x, baseline, anchor)


def _measure(page: _Page) -> Box:
    body = page.body
    width = min(TEXT_MEASURE, body.width)
    return Box(page.center_x - width / 2, body.y, width, body.height)


def _title_page(page: _Page) -> None:
    matter = page.plan_page.matter
    assert matter is not None and matter.title is not None
    t, body = page.spec.typography, page.body
    full = body
    bottom = page.block(
        "title",
        matter.title,
        Face.BOLD,
        t.title,
        t.title * 1.2,
        full,
        body.top - body.height * 0.22,
        Anchor.MIDDLE,
    )
    rule_y = bottom - 18
    width = page.spec.strokes.rule
    page.elements.append(
        Rule(
            "title_rule",
            page.center_x - 36,
            rule_y,
            page.center_x + 36,
            rule_y,
            width,
            Box(page.center_x - 36, rule_y - width / 2, 72, width),
        )
    )
    bottom = rule_y - 18
    if matter.subtitle:
        bottom = page.block(
            "subtitle",
            matter.subtitle,
            Face.REGULAR,
            t.subtitle,
            t.subtitle * 1.3,
            _measure(page),
            bottom,
            Anchor.MIDDLE,
        )
    if matter.author:
        bottom = page.block(
            "author",
            matter.author,
            Face.REGULAR,
            t.author,
            t.author * 1.3,
            full,
            bottom - 36,
            Anchor.MIDDLE,
        )
    floor = body.y
    if matter.imprint:
        wrapped = wrap_text(matter.imprint, Face.REGULAR, t.imprint, body.width)
        lines = max(len(wrapped.lines), 1)
        height = (lines - 1) * t.imprint * 1.3 + (ASCENT + DESCENT) * t.imprint
        page.block(
            "imprint",
            matter.imprint,
            Face.REGULAR,
            t.imprint,
            t.imprint * 1.3,
            full,
            body.y + height,
            Anchor.MIDDLE,
        )
        floor = body.y + height + 18
    page.require_within("title_page", bottom, floor, body.top - floor)


def _copyright_page(page: _Page) -> None:
    """A notice sits at the foot of its page, in authored lines."""
    matter = page.plan_page.matter
    assert matter is not None and matter.text is not None
    t, measure = page.spec.typography, _measure(page)
    size, leading = t.copyright, t.copyright * 1.4
    wrapped = wrap_text(matter.text, Face.REGULAR, size, measure.width)
    height = (len(wrapped.lines) - 1) * leading + (ASCENT + DESCENT) * size
    if wrapped.overflow_word is None and height > measure.height:
        page.issue(
            "text_overflow",
            "Text does not fit its region.",
            region="copyright",
            actual=f"{height:.2f} pt tall",
            required=f"at most {measure.height:.2f} pt",
        )
        return
    page.block(
        "copyright",
        matter.text,
        Face.REGULAR,
        size,
        leading,
        measure,
        measure.y + height,
        Anchor.START,
    )


def _heading(page: _Page, text: str) -> float:
    t = page.spec.typography
    body = page.body
    return page.block(
        "heading", text, Face.BOLD, t.heading, t.heading * 1.2, body, body.top, Anchor.MIDDLE
    )


def _text_page(page: _Page) -> None:
    matter = page.plan_page.matter
    assert matter is not None and matter.title is not None and matter.text is not None
    t = page.spec.typography
    top = _heading(page, matter.title) - HEADING_GAP
    measure = _measure(page)
    bottom = page.block(
        "body", matter.text, Face.REGULAR, t.body, t.body * 1.45, measure, top, Anchor.START
    )
    page.require_within("body", bottom, measure.y, top - measure.y)


def _notes_page(page: _Page) -> None:
    matter = page.plan_page.matter
    assert matter is not None and matter.title is not None
    top = _heading(page, matter.title) - HEADING_GAP - NOTES_SPACING
    body, width = page.body, page.spec.strokes.notes_line
    y = top
    while y >= body.y + width / 2 - 1e-6:
        page.elements.append(
            Rule(
                "notes_line",
                body.x,
                y,
                body.right,
                y,
                width,
                Box(body.x, y - width / 2, body.width, width),
                NOTES_GRAY,
            )
        )
        y -= NOTES_SPACING


@dataclass(frozen=True)
class _WordTable:
    words: tuple[str, ...]
    columns: int
    rows: int
    widest: float
    height: float


def _word_table(page: _Page, words: tuple[str, ...]) -> _WordTable | None:
    """Most columns (up to five) whose uniform width fits the live area."""
    size = page.spec.typography.word_list
    width = page.frame.content.width
    widest = max(text_width(word, Face.REGULAR, size) for word in words)
    if widest > width:
        page.issue(
            "word_list_overflow",
            "A word-list entry is wider than the page's live area.",
            region="word_list",
            actual=f"{widest:.2f} pt",
            required=f"at most {width:.2f} pt",
        )
        return None
    columns = next(
        n
        for n in range(min(MAX_WORD_COLUMNS, len(words)), 0, -1)
        if n * widest + (n - 1) * WORD_COLUMN_GAP <= width
    )
    rows = math.ceil(len(words) / columns)
    height = (rows - 1) * size * WORD_LEADING + (ASCENT + DESCENT) * size
    return _WordTable(words, columns, rows, widest, height)


def _place_word_table(page: _Page, table: _WordTable, top: float) -> None:
    """Column-major, in authoritative target order, centered as one table."""
    size = page.spec.typography.word_list
    span = table.columns * table.widest + (table.columns - 1) * WORD_COLUMN_GAP
    left = page.center_x - span / 2
    for index, word in enumerate(table.words):
        column, row = divmod(index, table.rows)
        x = left + column * (table.widest + WORD_COLUMN_GAP)
        baseline = top - ASCENT * size - row * size * WORD_LEADING
        page.line("word_list", word, Face.REGULAR, size, x, baseline)


def _grid_letters_fit(page: _Page, geometry: GridGeometry, minimum: float, region: str) -> bool:
    if geometry.cell <= 0 or geometry.letter_size < minimum - 1e-6:
        page.issue(
            "grid_too_small",
            "Grid letters would fall below the profile's minimum size.",
            region=region,
            actual=f"{max(geometry.letter_size, 0):.2f} pt",
            required=f"at least {minimum:g} pt",
        )
        return False
    return True


def _letter_grid(
    role: str, puzzle: WordSearch, geometry: GridGeometry, spec: PrintSpecification, marks: bool
) -> LetterGrid:
    placements = puzzle.solution.placements if marks else ()
    cells = frozenset((c.x, c.y) for p in placements for c in p.coordinates)

    def center(x: int, y: int) -> tuple[float, float]:
        return (
            geometry.origin_x + (x + 0.5) * geometry.cell,
            geometry.top - (y + 0.5) * geometry.cell,
        )

    return LetterGrid(
        role=role,
        rows=puzzle.grid.rows,
        origin_x=geometry.origin_x,
        top=geometry.top,
        cell=geometry.cell,
        letter_size=geometry.letter_size,
        face=Face.REGULAR,
        frame=geometry.frame,
        frame_width=geometry.stroke,
        baseline_offset=CAP_HEIGHT * geometry.letter_size / 2,
        emphasized=cells,
        muted_gray=MUTED_GRAY if marks else 0.0,
        marks=tuple(
            SolutionMark(
                p.target_id,
                center(p.start.x, p.start.y),
                center(p.end.x, p.end.y),
                geometry.cell * MARK_RADIUS,
                spec.strokes.solution_mark,
            )
            for p in placements
        ),
    )


def _puzzle_page(page: _Page, puzzles: dict[str, WordSearch]) -> None:
    ref = page.plan_page.puzzle
    assert ref is not None
    puzzle = puzzles[ref.id]
    t, body = page.spec.typography, page.body
    bottom = page.block(
        "puzzle_title",
        ref.title,
        Face.BOLD,
        t.puzzle_title,
        t.puzzle_title * 1.2,
        body,
        body.top,
        Anchor.MIDDLE,
    )
    bottom = page.block(
        "theme", ref.theme, Face.ITALIC, t.theme, t.theme * 1.3, body, bottom - 6, Anchor.MIDDLE
    )
    region_top = bottom - HEADING_GAP
    if page.issues:
        return
    table = _word_table(page, tuple(target.display for target in puzzle.targets))
    if table is None:
        return
    available = region_top - body.y
    grid_height = available - table.height - WORD_GAP
    if grid_height <= 0:
        page.issue(
            "word_list_overflow",
            "The word list leaves no room for the grid.",
            region="word_list",
            actual=f"{table.height:.2f} pt tall",
            required=f"less than {available - WORD_GAP:.2f} pt",
        )
        return
    grid_region = Box(body.x, region_top - grid_height, body.width, grid_height)
    geometry = fit_grid(
        puzzle.config.size.width,
        puzzle.config.size.height,
        grid_region,
        t.grid_letter_max,
        page.spec.strokes.grid_frame,
        max_cell_for_letter(t.grid_letter_max),
    )
    if not _grid_letters_fit(page, geometry, t.grid_letter_min, "puzzle_grid"):
        return
    # Center the painted grid and word list together in the space below the header.
    block = geometry.bounds.height + WORD_GAP + table.height
    geometry = geometry.moved(-(available - block) / 2)
    page.elements.append(_letter_grid("puzzle_grid", puzzle, geometry, page.spec, marks=False))
    _place_word_table(page, table, geometry.bounds.y - WORD_GAP)


def _solution_page(
    page: _Page, puzzles: dict[str, WordSearch], plan: PublicationPlan, density: int
) -> None:
    t, body = page.spec.typography, page.body
    top = body.top
    if page.plan_page.heading:
        top = _heading(page, page.plan_page.heading) - HEADING_GAP + 6
    region = Box(body.x, body.y, body.width, top - body.y)
    slots = solution_slots(density, region, SOLUTION_GAP_X, SOLUTION_GAP_Y)
    caption_height = (ASCENT + DESCENT) * t.caption
    for slot, item in zip(slots, page.plan_page.solutions, strict=False):
        puzzle = puzzles[item.puzzle.id]
        grid_region = Box(slot.x, slot.y, slot.width, slot.height - caption_height - CAPTION_GAP)
        geometry = fit_grid(
            puzzle.config.size.width,
            puzzle.config.size.height,
            grid_region,
            t.solution_letter_max,
            page.spec.strokes.grid_frame,
            max_cell_for_letter(t.solution_letter_max),
        )
        if not _grid_letters_fit(page, geometry, t.solution_letter_min, "solution_grid"):
            continue
        label = plan.pages[item.puzzle_page - 1].number.label
        title_width = text_width(item.puzzle.title, Face.BOLD, t.caption)
        label_width = text_width(label, Face.REGULAR, t.caption)
        combined = title_width + CAPTION_GAP + label_width
        if combined > slot.width:
            page.issue(
                "text_overflow",
                "Solution caption is wider than its slot.",
                region="solution_caption",
                subject=item.puzzle.id,
                actual=f"{combined:.2f} pt",
                required=f"at most {slot.width:.2f} pt",
            )
            continue
        center = geometry.frame.x + geometry.frame.width / 2
        baseline = slot.top - ASCENT * t.caption
        start = center - combined / 2
        page.line("solution_caption", item.puzzle.title, Face.BOLD, t.caption, start, baseline)
        page.line(
            "solution_page_ref",
            label,
            Face.REGULAR,
            t.caption,
            start + title_width + CAPTION_GAP,
            baseline,
            gray=LABEL_GRAY,
        )
        page.elements.append(_letter_grid("solution_grid", puzzle, geometry, page.spec, marks=True))
