"""Layout-model contracts: plan consumption, page templates, overflow and integrity."""

import re
from dataclasses import replace

import pytest

from puzzlepress import load_project
from puzzlepress.interior import InteriorError, layout_interior
from puzzlepress.interior.engine import FOLIO_BAND
from puzzlepress.interior.model import LetterGrid, Rule, TextLine
from puzzlepress.interior.spec import KDP, PAPERBACK_LETTER, FolioPlacement
from puzzlepress.interior.validation import validate_layout
from puzzlepress.publication import PageKind, build_publication
from puzzlepress.publication_verification import verify_publication_plan
from puzzlepress.wordsearch.models import Grid
from tests.helpers import DEMO, ROOT, demo_variant

SPEC = PAPERBACK_LETTER


def built(project):
    report, plan = build_publication(project)
    assert verify_publication_plan(plan, project, report).valid
    return report, plan


@pytest.fixture(scope="module")
def demo():
    project = load_project(DEMO).project
    report, plan = built(project)
    return project, report, plan, layout_interior(plan, report, SPEC)


def texts(page, role=None):
    return [e.text for e in page.elements if isinstance(e, TextLine) and role in (None, e.role)]


def grids(page):
    return [e for e in page.elements if isinstance(e, LetterGrid)]


def failure(plan, report, spec=SPEC):
    with pytest.raises(InteriorError) as caught:
        layout_interior(plan, report, spec)
    return caught.value


def test_one_physical_page_per_plan_entry_in_order(demo):
    _, report, plan, layout = demo
    assert [p.number for p in layout.pages] == list(range(1, 12))
    assert [(p.plan_index, p.kind) for p in layout.pages] == [
        (p.index, p.kind.value) for p in plan.pages
    ]
    assert [p.frame.recto for p in layout.pages] == [n % 2 == 1 for n in range(1, 12)]
    assert validate_layout(layout, plan, report) == ()
    assert layout.identity == plan.identity and layout.plan_digest.startswith("sha256-")
    assert [w.code for w in layout.warnings] == ["kdp_minimum_page_count"]


def test_folios_are_the_plans_labels_and_blanks_stay_blank(demo):
    _, _, plan, layout = demo
    assert [p.folio for p in layout.pages] == [
        None,
        None,
        None,
        None,
        "1",
        "2",
        "3",
        "4",
        "5",
        "6",
        "7",
    ]
    for page, entry in zip(layout.pages, plan.pages, strict=True):
        assert texts(page, "folio") == ([entry.number.label] if entry.number.displayed else [])
    blank = layout.pages[3]
    assert blank.kind == "blank" and blank.elements == () and blank.folio is None


def test_folio_placement_center_and_outside(demo):
    _, report, plan, layout = demo
    for page in layout.pages[4:6]:
        folio = next(e for e in page.elements if e.role == "folio")
        content = page.frame.content
        assert folio.x == content.x + content.width / 2
        assert content.y <= folio.bounds.y and folio.bounds.top <= content.y + FOLIO_BAND
    outside = layout_interior(plan, report, replace(SPEC, folio_placement=FolioPlacement.OUTSIDE))
    recto, verso = outside.pages[4], outside.pages[5]
    recto_folio = next(e for e in recto.elements if e.role == "folio")
    verso_folio = next(e for e in verso.elements if e.role == "folio")
    assert abs(recto_folio.bounds.right - recto.frame.content.right) < 1e-9
    assert abs(verso_folio.bounds.x - verso.frame.content.x) < 1e-9
    assert recto_folio.bounds.right > 500 and verso_folio.bounds.x < 100
    assert validate_layout(outside, plan, report) == ()


def test_front_matter_uses_only_authored_text(demo):
    project, _, _, layout = demo
    title, copyright_page, instructions = layout.pages[:3]
    assert texts(title, "title") == ["Seaside Word Searches"]
    assert texts(title, "subtitle") == ["A small composition demonstration"]
    assert texts(title, "author") == ["PuzzlePress Examples"]
    assert [e.role for e in title.elements if isinstance(e, Rule)] == ["title_rule"]
    notice = project.composition.front_matter[1].text
    assert " ".join(texts(copyright_page)) == notice
    lines = [e for e in copyright_page.elements if isinstance(e, TextLine)]
    assert min(e.bounds.y for e in lines) >= copyright_page.frame.content.y + FOLIO_BAND - 1e-9
    assert min(e.bounds.y for e in lines) < copyright_page.frame.content.y + FOLIO_BAND + 1
    assert texts(instructions, "heading") == ["How to Play"]
    assert texts(instructions, "body") == project.composition.front_matter[2].text.split("\n")


def test_every_printed_word_comes_from_source_or_plan(demo):
    project, _, plan, layout = demo
    source = repr(project.to_dict()) + " ".join(p.number.label for p in plan.pages)
    allowed = set(re.findall(r"[A-Za-z0-9]+", source))
    for page in layout.pages:
        for text in texts(page):
            assert set(re.findall(r"[A-Za-z0-9]+", text)) <= allowed, text


def test_puzzle_pages_draw_authoritative_grids_and_word_lists(demo):
    _, report, plan, layout = demo
    by_id = {r.id: r.puzzle for r in report.puzzles}
    for page, entry in zip(layout.pages[4:8], plan.pages[4:8], strict=True):
        puzzle = by_id[entry.puzzle.id]
        (grid,) = grids(page)
        assert grid.rows == puzzle.grid.rows and not grid.marks and not grid.emphasized
        assert texts(page, "word_list") == [t.display for t in puzzle.targets]
        assert texts(page, "puzzle_title") == [entry.puzzle.title]
        assert texts(page, "theme") == [entry.puzzle.theme]
        assert SPEC.typography.grid_letter_min <= grid.letter_size <= 20
        assert page.frame.content.contains(grid.frame, 1e-9)
        words = [e for e in page.elements if e.role == "word_list"]
        assert max(w.bounds.top for w in words) < grid.frame.y  # list below the grid
        # Grid and word list are centered as one block below the header.
        x, y = grid.center(0, 0)
        assert abs(x - (grid.origin_x + grid.cell / 2)) < 1e-9
        assert abs(y - (grid.top - grid.cell / 2)) < 1e-9


# Interval 9's cover-demo build (renderer 1): the plan, not the renderer, owns these.
COVER_DEMO_IDENTITY = "pp1-sha256-5a45b845092f74a285e07ed25a110ab5ae685bdf79d56e88d03a075bafe7ddf5"
COVER_DEMO_PLAN = "sha256-ddaacb36734594843a30aa69c6811f2686b1dc17447a04ba2019b5cbe096c9b1"


@pytest.fixture(scope="module")
def cover_demo():
    project = load_project(ROOT / "books" / "cover-demo").project
    report, plan = built(project)
    layout = layout_interior(plan, report, SPEC)
    assert validate_layout(layout, plan, report) == ()
    return plan, layout


def _minimum_letter(grid):
    t = SPEC.typography
    return t.grid_letter_min if grid.role == "puzzle_grid" else t.solution_letter_min


def test_cover_demo_grid_strokes_paint_inside_the_live_area(cover_demo):
    """Renderer 1 sized 14 x 14 frames to the live width; half the stroke overhung it."""
    plan, layout = cover_demo
    seen = set()
    for page in layout.pages:
        content = page.frame.content
        for grid in grids(page):
            half = grid.frame_width / 2
            painted = grid.bounds
            assert painted == grid.frame.expanded(half)
            assert content.contains(painted, 1e-9), (page.number, grid.role)
            assert grid.frame_width >= KDP.min_line_weight
            assert all(m.line_width >= KDP.min_line_weight for m in grid.marks)
            assert _minimum_letter(grid) <= grid.letter_size
            assert grid.cell * 0.56 >= grid.letter_size - 1e-9  # Square cells, letters inside.
            seen.add((grid.role, "recto" if page.frame.recto else "verso", grid.columns))
            if grid.role == "puzzle_grid" and grid.columns == 14:
                # Width-limited: the painted extent meets both live edges exactly.
                assert painted.x == pytest.approx(content.x, abs=1e-9)
                assert painted.right == pytest.approx(content.right, abs=1e-9)
                assert grid.frame.x - content.x == pytest.approx(half)
    assert {
        ("puzzle_grid", "verso", 14),
        ("puzzle_grid", "recto", 13),
        ("solution_grid", "recto", 13),
        ("solution_grid", "recto", 14),
        ("solution_grid", "verso", 13),
        ("solution_grid", "verso", 14),
    } <= seen


def test_cover_demo_geometry_fix_keeps_plan_and_pagination(cover_demo):
    plan, layout = cover_demo
    assert (layout.identity, layout.plan_digest) == (COVER_DEMO_IDENTITY, COVER_DEMO_PLAN)
    assert len(layout.pages) == len(plan.pages) == 35
    assert [(p.number, p.kind, p.folio) for p in layout.pages] == [
        (e.index, str(e.kind), e.number.label if e.number.displayed else None) for e in plan.pages
    ]
    letters = sorted({round(g.letter_size, 3) for p in layout.pages for g in grids(p)})
    assert letters[0] >= SPEC.typography.solution_letter_min and letters[-1] == 20


def _square_grids(size):
    def mutate(data):
        for profile in data["word_search"]["profiles"]:
            profile["width"] = profile["height"] = size

    return built(demo_variant(mutate, puzzles=4))


@pytest.mark.parametrize("size", [5, 14, 20, 22])
def test_small_and_large_grids_paint_inside_puzzle_and_solution_regions(size):
    report, plan = _square_grids(size)
    layout = layout_interior(plan, report, SPEC)
    assert validate_layout(layout, plan, report) == ()
    drawn = [(page, grid) for page in layout.pages for grid in grids(page)]
    assert {g.role for _, g in drawn} == {"puzzle_grid", "solution_grid"}
    for page, grid in drawn:
        assert page.frame.content.contains(grid.bounds, 1e-9)
        assert grid.letter_size >= _minimum_letter(grid)
        words = [e for e in page.elements if e.role == "word_list"]
        assert all(w.bounds.top <= grid.bounds.y - 22 + 1e-9 for w in words)


def test_grids_too_large_for_minimum_letters_still_fail_rather_than_shrink():
    # 22 x 22 is the largest 2-per-page solution grid, as under renderer 1.
    report, plan = _square_grids(24)
    error = failure(plan, report)
    assert {(i.code, i.region) for i in error.issues} == {("grid_too_small", "solution_grid")}


def test_puzzle_grid_geometry_is_identical_on_recto_and_verso_except_shift(demo):
    *_, layout = demo
    recto, verso = grids(layout.pages[4])[0], grids(layout.pages[5])[0]
    assert recto.cell == verso.cell  # same 10x8 profile
    assert recto.frame.x - verso.frame.x == pytest.approx(18)  # (54 - 36) mirrored margin


@pytest.mark.parametrize(
    ("per_page", "puzzles", "groups"),
    [(1, 3, [1, 1, 1]), (2, 3, [2, 1]), (4, 8, [4, 4]), (6, 7, [6, 1]), (6, 4, [4])],
)
def test_solution_pages_render_exactly_the_planned_groups(per_page, puzzles, groups):
    def mutate(data):
        data["composition"]["solutions"]["per_page"] = per_page

    project = demo_variant(mutate, puzzles=puzzles)
    report, plan = built(project)
    layout = layout_interior(plan, report, SPEC)
    assert validate_layout(layout, plan, report) == ()
    by_id = {r.id: r.puzzle for r in report.puzzles}
    solution_pages = [
        (page, entry)
        for page, entry in zip(layout.pages, plan.pages, strict=True)
        if entry.kind is PageKind.SOLUTIONS
    ]
    assert [len(grids(page)) for page, _ in solution_pages] == groups
    density = min(d for d in (1, 2, 4, 6) if d >= max(groups))
    columns = {1: 1, 2: 1, 4: 2, 6: 2}[density]
    for page, entry in solution_pages:
        drawn = grids(page)
        expected = [by_id[item.puzzle.id] for item in entry.solutions]
        assert [g.rows for g in drawn] == [p.grid.rows for p in expected]
        for grid, puzzle in zip(drawn, expected, strict=True):
            assert [m.target_id for m in grid.marks] == [
                p.target_id for p in puzzle.solution.placements
            ]
            cells = {(c.x, c.y) for p in puzzle.solution.placements for c in p.coordinates}
            assert grid.emphasized == cells and grid.letter_size >= 7
            assert all(m.line_width >= 0.75 for m in grid.marks)
        labels = [plan.pages[item.puzzle_page - 1].number.label for item in entry.solutions]
        assert texts(page, "solution_page_ref") == labels
        assert texts(page, "solution_caption") == [i.puzzle.title for i in entry.solutions]
        # Slots fill left-to-right then top-down.
        centers = [(round(g.frame.top, 3), g.frame.x + g.frame.width / 2) for g in drawn]
        assert len({x for _, x in centers}) <= columns
        assert [c[0] for c in centers] == sorted((c[0] for c in centers), reverse=True)
    first = solution_pages[0][0]
    assert texts(first, "heading") == ["Solutions"]
    assert all(texts(page, "heading") == [] for page, _ in solution_pages[1:])


def test_solution_marks_join_first_and_last_cells(demo):
    _, report, _, layout = demo
    grid = grids(layout.pages[9])[0]  # Solutions for puzzles 3 and 4.
    puzzle = next(r.puzzle for r in report.puzzles if r.id == "harbour")
    for mark, placement in zip(grid.marks, puzzle.solution.placements, strict=True):
        assert mark.start == grid.center(placement.start.x, placement.start.y)
        assert mark.end == grid.center(placement.end.x, placement.end.y)
        assert mark.radius == pytest.approx(grid.cell * 0.4)


def test_layout_is_deterministic_and_does_not_mutate_inputs(demo):
    _, report, plan, layout = demo
    before = (plan.to_dict(), report.to_dict())
    assert layout_interior(plan, report, SPEC) == layout
    assert (plan.to_dict(), report.to_dict()) == before


def test_digest_mismatch_is_rejected_without_regeneration(demo):
    _, report, plan, _ = demo
    target = report.puzzles[1]
    rows = list(target.puzzle.grid.rows)
    rows[0] = rows[0][::-1]
    tampered = replace(target, puzzle=replace(target.puzzle, grid=Grid(tuple(rows))))
    report = replace(report, puzzles=(report.puzzles[0], tampered, *report.puzzles[2:]))
    error = failure(plan, report)
    assert error.stage == "integrity"
    mismatches = [i for i in error.issues if i.code == "digest_mismatch"]
    assert [(i.page, i.kind, i.subject) for i in mismatches] == [
        (6, "puzzle", "rockpool"),
        (9, "solutions", "rockpool"),
    ]
    assert mismatches[0].required == plan.pages[5].puzzle.digest


def test_incomplete_plan_and_foreign_report_are_rejected(demo):
    project, _, plan, _ = demo

    def tiny(data):
        data["word_search"]["profiles"].append(
            {"id": "tiny", "width": 4, "height": 4, "directions": ["right"], "max_restarts": 1}
        )
        data["word_search"]["puzzles"][0]["difficulty"] = "tiny"
        data["word_search"]["puzzles"][0]["target_ids"] = ["wave", "sand", "crab", "kelp", "tide"]

    report, failed = built(demo_variant(tiny))
    error = failure(failed, report)
    assert {i.code for i in error.issues} == {"incomplete_plan", "missing_puzzle"}
    other_report, _ = built(demo_variant(puzzles=4))
    assert "identity_mismatch" in [i.code for i in failure(plan, other_report).issues]


def test_unsupported_and_reordered_entries_fail(demo):
    _, report, plan, _ = demo
    pages = list(plan.pages)
    pages[2] = replace(pages[2], kind="table_of_contents")
    error = failure(replace(plan, pages=tuple(pages)), report)
    assert [(i.code, i.page) for i in error.issues] == [("unsupported_page_type", 3)]
    swapped = list(plan.pages)
    swapped[4], swapped[5] = swapped[5], swapped[4]
    codes = [i.code for i in failure(replace(plan, pages=tuple(swapped)), report).issues]
    assert codes.count("plan_order") == 2
    seven = list(plan.pages)
    seven[8] = replace(seven[8], solutions=seven[8].solutions * 4)
    issues = failure(replace(plan, pages=tuple(seven)), report).issues
    assert [i.code for i in issues] == ["unsupported_solution_density"]


def test_text_overflow_fails_instead_of_adding_pages():
    def long_instructions(data):
        data["composition"]["front_matter"][2]["text"] = "x\n" * 999 + "x"

    report, plan = built(demo_variant(long_instructions))
    error = failure(plan, report)
    assert error.stage == "layout"
    (issue,) = error.issues
    assert (issue.code, issue.page, issue.physical_page, issue.kind) == (
        "text_overflow",
        3,
        3,
        "instructions",
    )
    assert issue.region == "body" and issue.actual.endswith("pt tall")


def test_copyright_overflow_and_unbreakable_titles_fail():
    def mutate(data):
        data["composition"]["front_matter"][1]["text"] = "line\n" * 399 + "line"
        data["word_search"]["puzzles"][0]["title"] = "W" * 200

    report, plan = built(demo_variant(mutate))
    issues = failure(plan, report).issues
    assert [(i.code, i.kind, i.region) for i in issues] == [
        ("text_overflow", "copyright_page", "copyright"),
        ("text_overflow", "puzzle", "puzzle_title"),
        ("text_overflow", "solutions", "solution_caption"),
    ]
    assert issues[1].subject == "shoreline"


def test_grid_too_small_fails_without_regrouping_solutions():
    def large(data):
        data["word_search"]["profiles"].append(
            {"id": "huge", "width": 40, "height": 40, "directions": ["right", "down"]}
        )
        data["word_search"]["profiles"].append(
            {"id": "big", "width": 20, "height": 20, "directions": ["right", "down"]}
        )
        data["word_search"]["puzzles"][0]["difficulty"] = "huge"
        for puzzle in data["word_search"]["puzzles"][1:]:
            puzzle["difficulty"] = "big"
        data["composition"]["solutions"]["per_page"] = 6

    report, plan = built(demo_variant(large, puzzles=6))
    assert sum(p.kind is PageKind.SOLUTIONS for p in plan.pages) == 1
    issues = failure(plan, report).issues
    assert {(i.code, i.kind, i.region) for i in issues} == {
        ("grid_too_small", "puzzle", "puzzle_grid"),
        ("grid_too_small", "solutions", "solution_grid"),
    }
    puzzle_issue = next(i for i in issues if i.kind == "puzzle")
    assert puzzle_issue.subject == "p1" and puzzle_issue.required == "at least 9 pt"
    assert len([i for i in issues if i.kind == "solutions"]) == 6


def test_word_list_overflow_is_reported():
    def wide(data):
        data["word_search"]["banks"][0]["entries"].append(
            {"id": "long", "display": " ".join("W" * 40)}
        )
        data["word_search"]["profiles"].append(
            {"id": "strip", "width": 40, "height": 3, "directions": ["right"]}
        )
        data["word_search"]["puzzles"][0].update(target_ids=["long"], difficulty="strip")

    report, plan = built(demo_variant(wide))
    issues = failure(plan, report).issues
    assert [(i.code, i.page, i.region) for i in issues] == [("word_list_overflow", 5, "word_list")]


def test_characters_missing_from_the_bundled_font_fail(demo):
    def symbol(data):
        data["book"]["title"] = "Seaside ✓ Searches"

    report, plan = built(demo_variant(symbol))
    (issue,) = failure(plan, report).issues
    assert (issue.code, issue.page, issue.actual) == ("unsupported_character", 1, "U+2713")


def test_layout_validation_detects_corruption(demo):
    _, report, plan, layout = demo
    pages = list(layout.pages)

    def corrupt(index, **changes):
        changed = list(pages)
        changed[index] = replace(pages[index], **changes)
        return {
            i.code for i in validate_layout(replace(layout, pages=tuple(changed)), plan, report)
        }

    verso = pages[5]
    assert "margin_mismatch" in corrupt(5, frame=layout.pages[4].frame)
    assert "folio_mismatch" in corrupt(5, folio="99")
    assert "blank_not_blank" in corrupt(3, elements=pages[2].elements)
    grid = grids(verso)[0]
    swapped = replace(grid, rows=grids(pages[4])[0].rows)
    others = tuple(e for e in verso.elements if e is not grid)
    assert "puzzle_content" in corrupt(5, elements=(*others, swapped))
    solution = pages[8]
    last_grid = grids(solution)[-1]
    kept = tuple(e for e in solution.elements if e is not last_grid)
    assert "solution_grouping" in corrupt(8, elements=kept)
    folio = next(e for e in verso.elements if e.role == "folio")
    moved = replace(folio, bounds=grid.frame)
    assert "element_collision" in corrupt(5, elements=(*verso.elements, moved))
    tiny = replace(folio, size=6)
    assert "font_too_small" in corrupt(5, elements=(*others, grid, tiny))
    assert "page_count_mismatch" in {
        i.code for i in validate_layout(replace(layout, pages=layout.pages[:-1]), plan, report)
    }
