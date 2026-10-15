"""Independent invariant checks for publication plans, including corrupted plans.

Checks are stated against source and generation results rather than by
re-running the planner, so a planner defect cannot certify its own output.
"""

from collections.abc import Callable
from dataclasses import asdict, dataclass

from .batch import BatchReport, derive_puzzle_seed, puzzle_digest
from .composition import NumberingScheme, SectionStart, SolutionPlacement
from .errors import ValidationIssue
from .identity import build_identity
from .models import Project
from .publication import (
    BLANK_REASON,
    DIVIDER_BLANK_REASON,
    PLAN_VERSION,
    NumberStyle,
    PageKind,
    PlanPage,
    PublicationPlan,
    PuzzleRef,
    Section,
    Side,
)

_Fail = Callable[[str, str, str], None]
_ORDER = (Section.FRONT_MATTER, Section.PUZZLES, Section.SOLUTIONS, Section.BACK_MATTER)
_MATTER = {
    PageKind.TITLE_PAGE,
    PageKind.COPYRIGHT_PAGE,
    PageKind.INSTRUCTIONS,
    PageKind.ABOUT,
    PageKind.NOTES,
}


@dataclass(frozen=True)
class PlanVerification:
    issues: tuple[ValidationIssue, ...]

    @property
    def valid(self) -> bool:
        return not self.issues


def verify_publication_plan(
    plan: PublicationPlan, project: Project, report: BatchReport
) -> PlanVerification:
    issues: list[ValidationIssue] = []

    def fail(path: str, code: str, message: str) -> None:
        issues.append(ValidationIssue(path, code, message))

    composition, content = project.composition, project.word_search
    if composition is None or content is None:
        fail("plan", "source", "Source has no composition or puzzle definitions.")
        return PlanVerification(tuple(issues))
    identity = build_identity(project)
    if plan.plan_version != PLAN_VERSION:
        fail("plan_version", "version", "Unsupported plan version.")
    if plan.identity != identity or report.identity != identity:
        fail("identity", "identity", "Plan, report and source identities differ.")
    if (plan.book_id, plan.language) != (project.book.id, project.book.language):
        fail("book_id", "book", "Plan book does not match source.")
    pages = plan.pages
    if not pages:
        fail("pages", "empty", "A plan needs at least one page.")
        return PlanVerification(tuple(issues))

    for position, page in enumerate(pages):
        path = f"pages.{position}"
        if page.index != position + 1:
            fail(f"{path}.index", "order", "Logical indexes must be contiguous from 1.")
        if position and _ORDER.index(page.section) < _ORDER.index(pages[position - 1].section):
            fail(f"{path}.section", "order", "Sections are out of reading order.")
        blank = page.kind is PageKind.BLANK
        if blank != (page.blank_reason is not None) or blank != (page.blank_before is not None):
            fail(f"{path}.blank", "blank", "Only blank pages carry a blank reason.")
        if blank:
            _check_blank(page, position, pages, composition.puzzles_start, project, fail)
        if page.kind is not PageKind.SOLUTIONS and (page.solutions or page.heading):
            fail(f"{path}.solutions", "solutions", "Only solution pages list solutions.")
        if (page.kind is PageKind.PUZZLE) != (page.puzzle is not None):
            fail(f"{path}.puzzle", "puzzle", "Exactly puzzle pages reference a puzzle.")
        if (page.kind in _MATTER) != (page.matter is not None):
            fail(f"{path}.matter", "matter", "Exactly matter pages carry matter content.")
        if (page.kind is PageKind.DIVIDER) != (page.divider is not None):
            fail(f"{path}.divider", "divider", "Exactly divider pages carry divider content.")
        expected_section = {
            PageKind.PUZZLE: Section.PUZZLES,
            PageKind.SOLUTIONS: Section.SOLUTIONS,
            PageKind.DIVIDER: Section.PUZZLES,
        }.get(page.kind)
        if expected_section and page.section is not expected_section:
            fail(f"{path}.section", "section", "Page kind is in the wrong section.")

    # Matter: authored kinds, order and text, with title pages from book metadata.
    for section, items in (
        (Section.FRONT_MATTER, composition.front_matter),
        (Section.BACK_MATTER, composition.back_matter),
    ):
        matter = [p for p in pages if p.section is section and p.kind in _MATTER]
        if [p.kind.value for p in matter] != [item.kind.value for item in items]:
            fail(section.value, "matter", "Matter pages differ from the composition.")
            continue
        for page, item in zip(matter, items, strict=True):
            assert page.matter is not None
            book = project.book
            expected = (
                (book.title, book.subtitle, book.author, book.imprint, None)
                if page.kind is PageKind.TITLE_PAGE
                else (item.title, None, None, None, item.text)
            )
            m = page.matter
            if (m.title, m.subtitle, m.author, m.imprint, m.text) != expected:
                fail(f"pages.{page.index - 1}.matter", "matter", "Matter text differs.")

    # Puzzles: every definition once, in authored order, bound to its generation.
    puzzle_pages = [p for p in pages if p.kind is PageKind.PUZZLE]
    refs = [p.puzzle for p in puzzle_pages if p.puzzle is not None]
    results = {result.id: result for result in report.puzzles}
    failed = {d.id for d in content.puzzles if results.get(d.id) is None}
    if [r.id for r in refs] != [d.id for d in content.puzzles]:
        fail("pages", "puzzles", "Planned puzzles differ from authored publication order.")
    else:
        for ordinal, (page, ref, definition) in enumerate(
            zip(puzzle_pages, refs, content.puzzles, strict=True), start=1
        ):
            path = f"pages.{page.index - 1}.puzzle"
            if (ref.ordinal, ref.title, ref.theme) != (ordinal, definition.title, definition.theme):
                fail(path, "puzzle", "Puzzle ordinal or text differs from source.")
            if ref.seed != derive_puzzle_seed(project.build.seed, definition.id):
                fail(f"{path}.seed", "seed", "Puzzle seed is not derived from source.")
            result = results.get(definition.id)
            generated = result is not None and result.puzzle is not None and not result.errors
            if not generated:
                failed.add(definition.id)
            expected_digest = (
                puzzle_digest(result.puzzle)
                if generated and result is not None and result.puzzle is not None
                else None
            )
            if ref.digest != expected_digest:
                fail(f"{path}.digest", "digest", "Puzzle digest does not match generation.")
    section_pages = [
        p for p in pages if p.section is Section.PUZZLES and p.kind is not PageKind.BLANK
    ]
    if composition.puzzles_start is SectionStart.RECTO and section_pages:
        if section_pages[0].side is not Side.RECTO:
            fail("pages", "recto", "Puzzles must start on a recto page.")
    _check_dividers(pages, project, fail)

    _check_solutions(pages, refs, project, fail)
    _check_numbers(pages, project, fail)

    expected_paths = {
        f"word_search.puzzles.{i}" for i, d in enumerate(content.puzzles) if d.id in failed
    }
    actual = {d.path for d in plan.diagnostics if d.code == "generation_failed"}
    if actual != expected_paths or len(plan.diagnostics) != len(actual):
        fail("diagnostics", "diagnostics", "Diagnostics do not match generation failures.")

    stats = plan.statistics
    solutions_end = composition.solutions.placement is SolutionPlacement.END
    if (
        stats.logical_pages != len(pages)
        or stats.puzzles != len(content.puzzles)
        or stats.puzzle_pages != len(puzzle_pages)
        or stats.solutions != (len(content.puzzles) if solutions_end else 0)
        or stats.blank_pages != sum(p.kind is PageKind.BLANK for p in pages)
        or stats.front_matter_pages != len(composition.front_matter)
        or stats.back_matter_pages != len(composition.back_matter)
        or stats.first_puzzle_page != (puzzle_pages[0].index if puzzle_pages else None)
        or stats.divider_pages != sum(p.kind is PageKind.DIVIDER for p in pages)
    ):
        fail("statistics", "statistics", "Statistics do not match the planned pages.")
    return PlanVerification(tuple(issues))


def _check_blank(
    page: PlanPage,
    position: int,
    pages: tuple[PlanPage, ...],
    puzzles_start: SectionStart,
    project: Project,
    fail: _Fail,
) -> None:
    path = f"pages.{position}.blank"
    composition = project.composition
    assert composition is not None
    following = pages[position + 1] if position + 1 < len(pages) else None
    if page.blank_reason == DIVIDER_BLANK_REASON:
        dividers = composition.dividers
        if (
            dividers is None
            or dividers.start is not SectionStart.RECTO
            or following is None
            or following.kind is not PageKind.DIVIDER
            or page.section is not Section.PUZZLES
            or page.blank_before is not Section.PUZZLES
            or page.side is not Side.VERSO
            or position == 0
            or pages[position - 1].kind is PageKind.BLANK
        ):
            fail(path, "blank", "Blank page is not justified by a recto divider start.")
        return
    policies = {Section.PUZZLES: puzzles_start, Section.SOLUTIONS: composition.solutions.start}
    if (
        page.blank_reason != BLANK_REASON
        or following is None
        or page.blank_before is not following.section
        or page.side is not Side.VERSO
        or policies.get(following.section) is not SectionStart.RECTO
        or position == 0
        or pages[position - 1].section is not page.section
        or pages[position - 1].kind is PageKind.BLANK
    ):
        fail(path, "blank", "Blank page is not justified by a recto section start.")


def _check_solutions(
    pages: tuple[PlanPage, ...],
    refs: list[PuzzleRef],
    project: Project,
    fail: _Fail,
) -> None:
    composition = project.composition
    assert composition is not None
    policy = composition.solutions
    solution_pages = [p for p in pages if p.kind is PageKind.SOLUTIONS]
    by_id = {p.puzzle.id: p for p in pages if p.puzzle is not None}
    if policy.placement is SolutionPlacement.OMIT:
        if solution_pages or any(p.solution_page is not None for p in pages):
            fail("pages", "solutions", "Solutions are omitted but the plan places some.")
        return
    listed = [item for page in solution_pages for item in page.solutions]
    if [item.puzzle for item in listed] != refs:
        fail("pages", "solution_coverage", "Each puzzle needs exactly one matching solution.")
    for n, page in enumerate(solution_pages):
        path = f"pages.{page.index - 1}"
        last = n == len(solution_pages) - 1
        if not 1 <= len(page.solutions) <= policy.per_page or (
            not last and len(page.solutions) != policy.per_page
        ):
            fail(f"{path}.solutions", "grouping", "Solution grouping differs from policy.")
        if page.heading != (policy.title if n == 0 else None):
            fail(f"{path}.heading", "heading", "Only the first solution page has the heading.")
        for item in page.solutions:
            puzzle_page = by_id.get(item.puzzle.id)
            if puzzle_page is None or puzzle_page.index != item.puzzle_page:
                fail(f"{path}.solutions", "reference", "Solution points to the wrong page.")
            elif puzzle_page.solution_page != page.index:
                fail(f"{path}.solutions", "reference", "Puzzle points to the wrong solution.")
    if (
        policy.start is SectionStart.RECTO
        and solution_pages
        and solution_pages[0].side is not Side.RECTO
    ):
        fail("pages", "recto", "Solutions must start on a recto page.")


def _check_numbers(pages: tuple[PlanPage, ...], project: Project, fail: _Fail) -> None:
    composition = project.composition
    assert composition is not None
    numbers = composition.page_numbers
    roman_front = numbers.scheme is NumberingScheme.ROMAN_FRONT_MATTER
    shown = {
        Section.FRONT_MATTER: numbers.show_front_matter,
        Section.PUZZLES: True,
        Section.SOLUTIONS: numbers.show_solutions,
        Section.BACK_MATTER: numbers.show_back_matter,
    }
    previous: PlanPage | None = None
    for page in pages:
        path = f"pages.{page.index - 1}.number"
        number = page.number
        roman = roman_front and page.section is Section.FRONT_MATTER
        style = NumberStyle.ROMAN if roman else NumberStyle.ARABIC
        continues = previous is not None and previous.number.style is style
        expected_value = previous.number.value + 1 if previous and continues else 1
        if number.style is not style or number.value != expected_value:
            fail(path, "numbering", "Page number breaks the numbering scheme.")
        printed = page.kind not in (PageKind.BLANK, PageKind.DIVIDER) and shown[page.section]
        if number.displayed != printed:
            fail(path, "display", "Page number visibility differs from policy.")
        previous = page


def _check_dividers(pages: tuple[PlanPage, ...], project: Project, fail: _Fail) -> None:
    """One divider directly before the first puzzle of each theme group, with its words."""
    composition, content = project.composition, project.word_search
    assert composition is not None and content is not None
    dividers = composition.dividers
    found = [p for p in pages if p.kind is PageKind.DIVIDER]
    if dividers is None:
        if found:
            fail("pages", "divider", "The composition has no dividers but the plan places some.")
        return
    starts: list[str] = []
    for definition in content.puzzles:
        if not starts or definition.theme != starts[-1]:
            starts.append(definition.theme)
    if [p.divider.theme for p in found if p.divider] != starts:
        fail("pages", "divider_coverage", "Each theme group needs exactly one divider.")
        return
    for page in found:
        path = f"pages.{page.index - 1}.divider"
        assert page.divider is not None
        entry = dividers.entry(page.divider.theme)
        expected = (entry.title or entry.theme, entry.text, entry.quote, entry.attribution)
        actual = (
            page.divider.title,
            page.divider.text,
            page.divider.quote,
            page.divider.attribution,
        )
        if actual != expected:
            fail(path, "divider", "Divider text differs from the composition.")
        following = pages[page.index] if page.index < len(pages) else None
        if (
            following is None
            or following.puzzle is None
            or following.puzzle.theme != page.divider.theme
        ):
            fail(path, "divider", "A divider must directly precede its theme's first puzzle.")
        if dividers.start is SectionStart.RECTO and page.side is not Side.RECTO:
            fail(path, "recto", "Dividers must start on a recto page.")


def publication_payload(
    report: BatchReport, plan: PublicationPlan, verification: PlanVerification
) -> dict[str, object]:
    """Shared JSON presentation. Quality stays a separate summary, not a plan diagnostic."""
    return {
        "plan": plan.to_dict(),
        "verification": {
            "valid": verification.valid,
            "issues": [asdict(issue) for issue in verification.issues],
        },
        "generation": {
            "success": report.success,
            "clean": report.clean,
            "quality_findings": len(report.findings),
        },
    }
