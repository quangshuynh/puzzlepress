"""Interior design studio: answer layouts, page layouts, themes, spreads and design files."""

import io
import itertools
import json
import re
from dataclasses import replace

import pytest
from pypdf import PdfReader

from puzzlepress.composition import DEFAULT_SOLUTIONS_PER_PAGE, SOLUTIONS_PER_PAGE
from puzzlepress.errors import ProjectError
from puzzlepress.identity import build_identity
from puzzlepress.interior import build_interior, write_interior
from puzzlepress.interior.build import answer_layouts, sample_interior
from puzzlepress.interior.design import (
    CLASSIC,
    LAYOUTS,
    THEMES,
    design_catalogue,
    print_gray,
    resolve_design,
)
from puzzlepress.interior.engine import layout_interior
from puzzlepress.interior.issues import InteriorError
from puzzlepress.interior.model import LetterGrid, Panel, Polygon, Rule, TextLine
from puzzlepress.interior.spec import PAPERBACK_LETTER
from puzzlepress.interior.validation import validate_layout
from puzzlepress.interior_design_file import DesignFileError, export_design, import_design
from puzzlepress.interior_style import PageLayout, Theme
from puzzlepress.interior_style_validation import validate_interior_style
from puzzlepress.preflight import preflight_interior, read_interior_artifacts
from puzzlepress.publication import SPREAD_BLANK_REASON, PageKind, Side, build_publication
from puzzlepress.publication_verification import verify_publication_plan
from puzzlepress.validation import validate_project
from tests.helpers import demo_variant

THEMES_BY_PUZZLE = ["Engines"] * 4 + ["Tools"] * 4 + ["Racing"] * 6
RACING = {"version": 2, "theme": "racing_orange", "layout": "bold_header"}


def book(
    style=None,
    per_page=None,
    puzzles=10,
    size=None,
    layout=None,
    dividers=None,
    start="any",
    omit_per_page=False,
):
    def mutate(data):
        for puzzle, theme in zip(data["word_search"]["puzzles"], THEMES_BY_PUZZLE, strict=False):
            puzzle["theme"] = theme
        solutions = data["composition"]["solutions"]
        if omit_per_page:
            solutions.pop("per_page", None)
        elif per_page is not None:
            solutions["per_page"] = per_page
        data["composition"]["puzzles"]["start"] = start
        if layout is not None:
            data["composition"]["puzzles"]["layout"] = layout
        if dividers is not None:
            data["composition"]["puzzles"]["dividers"] = dividers
        if size is not None:
            for profile in data["word_search"]["profiles"]:
                profile["width"] = profile["height"] = size
        if style is not None:
            data["interior"] = style

    return demo_variant(mutate, puzzles=puzzles)


def build(project):
    return build_interior(project, PAPERBACK_LETTER)


def page_elements(built, kind=None):
    for page in built.layout.pages:
        if kind is None or page.kind == kind:
            yield page, page.elements


def solution_pages(built):
    return [p for p in built.layout.pages if p.kind == "solutions"]


def grid_centers(page):
    grids = [e for e in page.elements if isinstance(e, LetterGrid)]
    return [(round(g.frame.x + g.frame.width / 2), round(g.frame.top)) for g in grids]


# ------------------------------------------------------------------ answer layouts


def test_default_is_four_solutions_on_every_printed_page():
    assert DEFAULT_SOLUTIONS_PER_PAGE == 4 and SOLUTIONS_PER_PAGE == (1, 2, 4, 6, 8)
    project = book(omit_per_page=True, puzzles=10)
    assert project.composition.solutions.per_page == 4
    built = build(project)
    groups = [len(p.solutions) for p in built.plan.pages if p.kind is PageKind.SOLUTIONS]
    assert groups == [4, 4, 2]  # Continues onto further pages; the last holds fewer.
    full = solution_pages(built)[1]
    centers = grid_centers(full)
    # 2 x 2: two columns and two rows, filled left to right, then down.
    assert len({x for x, _ in centers}) == 2 and len({y for _, y in centers}) == 2
    assert centers[0][1] == centers[1][1] > centers[2][1] == centers[3][1]
    assert centers[0][0] == centers[2][0] < centers[1][0] == centers[3][0]


def test_solutions_keep_puzzle_order_titles_page_references_and_paths():
    project = book(
        {"version": 2, "solution_pages": {"page_label": "page {page}"}}, per_page=4, puzzles=11
    )
    built = build(project)
    ordered = [item for p in built.plan.pages for item in p.solutions]
    assert [i.puzzle.id for i in ordered] == [d.id for d in project.word_search.puzzles]
    results = {r.id: r.puzzle for r in built.report.puzzles}
    drawn = []
    for plan_page, page in zip(built.plan.pages, built.layout.pages, strict=True):
        if plan_page.kind is not PageKind.SOLUTIONS:
            continue
        captions = [e.text for e in page.elements if getattr(e, "role", "") == "solution_caption"]
        refs = [e.text for e in page.elements if getattr(e, "role", "") == "solution_page_ref"]
        grids = [e for e in page.elements if isinstance(e, LetterGrid)]
        for item, caption, ref, grid in zip(
            plan_page.solutions, captions, refs, grids, strict=True
        ):
            puzzle_page = built.plan.pages[item.puzzle_page - 1]
            assert puzzle_page.kind is PageKind.PUZZLE and puzzle_page.puzzle == item.puzzle
            assert caption == item.puzzle.title
            assert ref == f"page {puzzle_page.number.label}"
            placements = results[item.puzzle.id].solution.placements
            assert [m.target_id for m in grid.marks] == [p.target_id for p in placements]
            for mark in grid.marks:  # Every path stays inside its own grid frame.
                for x, y in (mark.start, mark.end):
                    assert grid.frame.x < x < grid.frame.right
                    assert grid.frame.y < y < grid.frame.top
            drawn.append(item.puzzle.id)
    assert drawn == [d.id for d in project.word_search.puzzles]
    assert validate_layout(built.layout, built.plan, built.report) == ()


@pytest.mark.parametrize(
    ("per_page", "size", "columns", "rows"),
    [(1, None, 1, 1), (2, None, 1, 2), (4, None, 2, 2), (6, None, 2, 3), (8, 10, 2, 4)],
)
def test_each_answer_preset_builds_its_arrangement(per_page, size, columns, rows):
    project = book(per_page=per_page, puzzles=per_page + 1, size=size)
    built = build(project)
    first = solution_pages(built)[0]
    centers = grid_centers(first)
    assert len(centers) == per_page
    assert len({x for x, _ in centers}) == columns and len({y for _, y in centers}) == rows
    last = solution_pages(built)[-1]
    assert len(grid_centers(last)) == 1  # A final page with fewer solutions.
    assert validate_layout(built.layout, built.plan, built.report) == ()
    reader = PdfReader(io.BytesIO(built.pdf))
    assert len(reader.pages) == len(built.plan.pages) == built.manifest["page_count"]


@pytest.mark.parametrize("value", [3, 5, 10, 0, "4", True])
def test_unsupported_counts_are_refused_with_the_choices(value):
    data = book().to_dict()
    data["composition"]["solutions"]["per_page"] = value
    issues = validate_project(data).issues
    (issue,) = [i for i in issues if i.path == "composition.solutions.per_page"]
    assert issue.code == "choice" and "1, 2, 4, 6, 8" in issue.message


def test_unreadable_density_names_a_viable_choice_and_never_changes_the_count():
    project = book(per_page=8, puzzles=9, size=15)  # 15 x 15 at 8 a page: below 7 pt.
    with pytest.raises(InteriorError) as error:
        build(project)
    (issue,) = [i for i in error.value.issues if i.code == "solution_layout_unreadable"]
    assert issue.region == "composition.solutions.per_page"
    assert re.search(r"Choose \d solutions a page or fewer\.", issue.message)
    assert project.composition.solutions.per_page == 8
    report, plan = build_publication(project)
    fits = {f.per_page: f for f in answer_layouts(project, PAPERBACK_LETTER, (report, plan))}
    assert not fits[8].fits and fits[4].fits and fits[4].letter_size >= 7
    recommended = int(re.search(r"Choose (\d)", issue.message).group(1))
    assert fits[recommended].fits and all(not fits[n].fits for n in fits if n > recommended)


def test_answer_fits_agree_with_the_built_letters():
    project = book(per_page=4, puzzles=5)
    built = build(project)
    report, plan = built.report, built.plan
    fit = {f.per_page: f for f in answer_layouts(project, PAPERBACK_LETTER, (report, plan))}[4]
    letters = [
        e.letter_size
        for page in solution_pages(built)
        for e in page.elements
        if isinstance(e, LetterGrid)
    ]
    assert fit.letter_size == pytest.approx(min(letters))
    assert fit.columns == 2 and fit.rows == 2


def test_cramped_but_legal_solutions_are_a_preflight_warning(tmp_path):
    built = build(book(RACING, per_page=8, puzzles=9, size=10))
    assert "dense_solution_page" in [w.code for w in built.layout.warnings]


# ------------------------------------------------------------------ styles and themes


def test_version_two_classic_draws_the_original_interior():
    plain = build(book())
    classic = build(book({"version": 2, "theme": "classic", "layout": "classic"}))
    assert classic.pdf == plain.pdf
    assert classic.manifest["style"]["design"]["look"]["theme"] == "classic"
    assert (
        "look" not in build(book({"version": 1, "preset": "classic"})).manifest["style"]["design"]
    )


def test_styles_never_change_identity_plan_or_seeds():
    plain, styled = book(), book(RACING)
    assert build_identity(plain) == build_identity(styled)
    a, b = build(plain), build(styled)
    assert a.manifest["plan_digest"] == b.manifest["plan_digest"]
    assert [r.seed for r in a.report.puzzles] == [r.seed for r in b.report.puzzles]
    assert a.manifest["interior_identity"] != b.manifest["interior_identity"]


@pytest.mark.parametrize("layout", [layout.value for layout in PageLayout])
def test_each_page_layout_changes_the_pdf_and_stays_valid(layout):
    base = build(book({"version": 2}))
    built = build(book({"version": 2, "layout": layout}))
    assert validate_layout(built.layout, built.plan, built.report) == ()
    if layout == "classic":
        assert built.pdf == base.pdf
    else:
        assert built.pdf != base.pdf


def test_layouts_place_titles_words_and_grids_as_described():
    bold = build(book({"version": 2, "layout": "bold_header"}))
    page = next(p for p in bold.layout.pages if p.kind == "puzzle")
    banner = next(e for e in page.elements if isinstance(e, Panel))
    title = next(e for e in page.elements if getattr(e, "role", "") == "puzzle_title")
    assert banner.role == "puzzle_title_banner" and banner.box.contains(title.bounds, 0.01)
    assert title.gray == 1.0  # Paper-white type on the dark banner.
    assert any(isinstance(e, Rule) and e.role == "word_rule" for e in page.elements)
    minimal = build(book({"version": 2, "layout": "clean_minimal"}))
    page = next(p for p in minimal.layout.pages if p.kind == "puzzle")
    title = next(e for e in page.elements if getattr(e, "role", "") == "puzzle_title")
    assert title.anchor.value == "start" and title.face.value == "regular"
    large = build(book({"version": 2, "layout": "large_readability"}))
    page = next(p for p in large.layout.pages if p.kind == "puzzle")
    words = [e for e in page.elements if getattr(e, "role", "") == "word_list"]
    assert {w.size for w in words} == {15.0} and {w.face.value for w in words} == {"bold"}
    above = build(book({"version": 2, "puzzle_pages": {"word_position": "above"}}))
    page = next(p for p in above.layout.pages if p.kind == "puzzle")
    grid = next(e for e in page.elements if isinstance(e, LetterGrid))
    words = [e for e in page.elements if getattr(e, "role", "") == "word_list"]
    assert all(w.bounds.y > grid.bounds.top for w in words)


def test_puzzle_number_and_answer_reference_follow_the_plan():
    style = {
        "version": 2,
        "puzzle_pages": {"puzzle_number": True, "answer_reference": "Solution on page {page}"},
    }
    built = build(book(style, per_page=4, puzzles=9))
    for plan_page, page in zip(built.plan.pages, built.layout.pages, strict=True):
        if plan_page.kind is not PageKind.PUZZLE:
            continue
        texts = {e.role: e.text for e in page.elements if isinstance(e, TextLine)}
        assert texts["puzzle_title_number"] == str(plan_page.puzzle.ordinal)
        target = built.plan.pages[plan_page.solution_page - 1]
        assert target.kind is PageKind.SOLUTIONS and plan_page.puzzle in [
            s.puzzle for s in target.solutions
        ]
        assert texts["answer_reference"] == f"Solution on page {target.number.label}"
    # Repaginating the answers moves every reference with them.
    other = build(book(style, per_page=1, puzzles=9))
    refs = [
        e.text
        for p in other.layout.pages
        for e in p.elements
        if getattr(e, "role", "") == "answer_reference"
    ]
    assert len(set(refs)) == 9


@pytest.mark.parametrize("theme", [theme.value for theme in Theme])
def test_themes_apply_consistently_and_print_in_gray(theme):
    dividers = {"start": "any", "themes": []}
    built = build(book({"version": 2, "theme": theme}, dividers=dividers))
    assert validate_layout(built.layout, built.plan, built.report) == ()
    look = resolve_design(
        built.layout.design and validate_interior_style({"version": 2, "theme": theme}, True)[0]
    ).look
    for page in built.layout.pages:
        for element in page.elements:
            for gray in (
                getattr(element, "gray", 0.0),
                getattr(element, "fill_gray", None),
                getattr(element, "stroke_gray", None),
            ):
                assert gray is None or 0.0 <= gray <= 1.0
    kinds = {"puzzle", "solutions", "divider"}
    decorated = {
        page.kind
        for page in built.layout.pages
        if any(isinstance(e, Polygon) or e.role == "page_frame" for e in page.elements)
    }
    if look.motif != "none" or look.background == "frame":
        assert decorated == kinds  # Every themed page kind, never title or matter pages.
    else:
        assert decorated == set()
    if look.banner != "none":
        first = solution_pages(built)[0]
        assert any(e.role.startswith("heading") for e in first.elements)
    # Black ink only: DeviceGray operators, never RGB or CMYK colour.
    reader = PdfReader(io.BytesIO(built.pdf))
    for pdf_page in reader.pages:
        content = pdf_page.get_contents().get_data()
        assert not re.search(rb"\s(rg|RG|k|K)\s", content)


def test_ink_saver_uses_outlines_without_fills_or_decoration():
    built = build(book({"version": 2, "theme": "ink_saver", "layout": "bold_header"}))
    panels = [e for _, els in page_elements(built) for e in els if isinstance(e, Panel)]
    assert panels and all(p.fill_gray is None for p in panels)
    assert not [e for _, els in page_elements(built) for e in els if isinstance(e, Polygon)]
    assert validate_layout(built.layout, built.plan, built.report) == ()


def test_accent_colours_print_as_their_luminance_and_light_text_warns():
    assert print_gray("#000000") == 0.0 and print_gray("#ffffff") == 1.0
    assert print_gray("#e8590c") == pytest.approx(0.482, abs=1e-3)
    style = {"version": 2, "theme": "racing_orange", "colors": {"accent": "#ffcc00"}}
    built = build(book(style))
    theme = [
        e
        for _, els in page_elements(built, "puzzle")
        for e in els
        if getattr(e, "role", "") == "theme"
    ]
    assert {t.gray for t in theme} == {print_gray("#ffcc00")}
    assert "light_text" in [w.code for w in built.layout.warnings]


@pytest.mark.parametrize(
    ("theme", "layout"), list(itertools.product(list(Theme), list(PageLayout)))
)
def test_every_theme_and_layout_lays_out_without_overlap(theme, layout):
    style = {
        "version": 2,
        "theme": theme.value,
        "layout": layout.value,
        "puzzle_pages": {"puzzle_number": True, "answer_reference": "Answer: page {page}"},
    }
    report, plan = build_publication(book(style, per_page=4, puzzles=6))
    design = resolve_design(validate_interior_style(style, True)[0])
    layout_result = layout_interior(plan, report, PAPERBACK_LETTER, design)
    assert validate_layout(layout_result, plan, report) == ()
    for page in layout_result.pages:
        shapes = [e for e in page.elements if isinstance(e, Polygon)]
        for shape in shapes:
            assert page.frame.content.contains(shape.bounds, 0.01)


def test_decoration_overlapping_content_is_refused():
    built = build(book(RACING))
    page = next(p for p in built.layout.pages if p.kind == "puzzle")
    grid = next(e for e in page.elements if isinstance(e, LetterGrid))
    intruder = Polygon("motif", ((0, 0), (1, 0), (1, 1)), 0.5, grid.bounds)
    pages = list(built.layout.pages)
    pages[page.number - 1] = replace(page, elements=(*page.elements, intruder))
    issues = validate_layout(replace(built.layout, pages=tuple(pages)), built.plan, built.report)
    assert "decoration_overlap" in [i.code for i in issues]
    frame = Panel("page_frame", grid.bounds.expanded(-5), None, 0.0, 1.0)
    pages[page.number - 1] = replace(page, elements=(frame, *page.elements))
    issues = validate_layout(replace(built.layout, pages=tuple(pages)), built.plan, built.report)
    assert {"frame_crosses_content", "panel_over_grid"} <= {i.code for i in issues}


def test_identical_design_inputs_build_identical_pdfs_and_manifests():
    first, second = (
        build(book(RACING, per_page=6, layout="spread")),
        build(book(RACING, per_page=6, layout="spread")),
    )
    assert first.pdf == second.pdf and first.manifest == second.manifest


# ------------------------------------------------------------------ schema


def test_version_two_schema_and_version_one_boundaries():
    style, issues = validate_interior_style(
        {
            "version": 2,
            "theme": "classic_garage",
            "layout": "large_readability",
            "colors": {"accent": "#112233"},
            "motif": "stripes",
            "density": "compact",
            "puzzle_pages": {"word_columns": 1, "grid_width": 80},
            "solution_pages": {"page_label": "p. {page}"},
        },
        True,
    )
    assert issues == () and style.to_dict()["colors"] == {"accent": "#112233"}
    assert validate_interior_style(style.to_dict(), True)[0] == style
    bad = [
        ({"version": 1, "theme": "racing_orange"}, ("interior.theme", "requires_version_2")),
        (
            {"version": 1, "puzzle_pages": {"word_columns": 1}},
            ("interior.puzzle_pages.word_columns", "range"),
        ),
        ({"version": 2, "preset": "classic"}, ("interior.preset", "not_applicable")),
        ({"version": 2, "theme": "neon"}, ("interior.theme", "choice")),
        ({"version": 2, "colors": {"accent": "orange"}}, ("interior.colors.accent", "color")),
        ({"version": 2, "motif": "flames"}, ("interior.motif", "choice")),
        (
            {"version": 2, "puzzle_pages": {"grid_width": 40}},
            ("interior.puzzle_pages.grid_width", "range"),
        ),
        (
            {"version": 2, "puzzle_pages": {"answer_reference": "See answers"}},
            ("interior.puzzle_pages.answer_reference", "placeholder"),
        ),
        (
            {"version": 2, "solution_pages": {"page_label": "{page} {page}"}},
            ("interior.solution_pages.page_label", "placeholder"),
        ),
        (
            {"version": 2, "solution_pages": {"page_label": "{title} {page}"}},
            ("interior.solution_pages.page_label", "placeholder"),
        ),
    ]
    for value, expected in bad:
        _, found = validate_interior_style(value, True)
        assert expected in [(i.path, i.code) for i in found], value


def test_catalogue_lists_every_theme_and_layout_from_python():
    catalogue = design_catalogue()
    assert [t["id"] for t in catalogue["themes"]] == [t.value for t in THEMES]
    assert [layout["id"] for layout in catalogue["layouts"]] == [x.value for x in LAYOUTS]
    racing = next(t for t in catalogue["themes"] if t["id"] == "racing_orange")
    assert racing["look"]["accent_gray"] == print_gray("#e8590c")
    assert json.dumps(catalogue)  # Plain JSON for Studio.


def test_absent_style_is_the_classic_design():
    assert resolve_design(None) == CLASSIC and CLASSIC.look is None


# ------------------------------------------------------------------ spreads


def test_spread_puts_each_word_list_on_a_left_page_facing_its_grid():
    project = book(RACING, layout="spread", puzzles=5)
    built = build(project)
    plan = built.plan
    assert verify_publication_plan(plan, project, built.report).valid
    words = [p for p in plan.pages if p.kind is PageKind.PUZZLE_WORDS]
    grids = [p for p in plan.pages if p.kind is PageKind.PUZZLE]
    assert len(words) == len(grids) == 5
    for word_page in words:
        grid_page = plan.pages[word_page.index]
        assert word_page.side is Side.VERSO and grid_page.side is Side.RECTO
        assert grid_page.kind is PageKind.PUZZLE and grid_page.puzzle == word_page.puzzle
    for item in (s for p in plan.pages for s in p.solutions):
        assert plan.pages[item.puzzle_page - 1].kind is PageKind.PUZZLE
    blanks = [p for p in plan.pages if p.blank_reason == SPREAD_BLANK_REASON]
    for blank in blanks:
        assert blank.side is Side.RECTO and plan.pages[blank.index].kind is PageKind.PUZZLE_WORDS
    assert plan.statistics.puzzle_pages == 10 and plan.statistics.puzzles == 5
    for plan_page, page in zip(plan.pages, built.layout.pages, strict=True):
        has_grid = any(isinstance(e, LetterGrid) for e in page.elements)
        has_words = any(getattr(e, "role", "") == "word_list" for e in page.elements)
        if plan_page.kind is PageKind.PUZZLE_WORDS:
            assert has_words and not has_grid
        elif plan_page.kind is PageKind.PUZZLE:
            assert has_grid and not has_words


def test_spread_with_dividers_aligns_and_verifies():
    dividers = {"start": "recto", "themes": []}
    project = book(layout="spread", dividers=dividers, start="recto", puzzles=10)
    built = build(project)
    assert verify_publication_plan(built.plan, project, built.report).valid
    for page in built.plan.pages:
        if page.kind is PageKind.PUZZLE_WORDS:
            assert page.side is Side.VERSO


def test_spread_recto_start_without_dividers_is_refused():
    data = book().to_dict()
    data["composition"]["puzzles"] = {"start": "recto", "layout": "spread"}
    issues = validate_project(data).issues
    assert ("composition.puzzles.start", "spread_starts_verso") in [
        (i.path, i.code) for i in issues
    ]


def test_spread_is_recorded_only_when_chosen():
    single, spread = book(), book(layout="spread")
    assert "layout" not in single.composition.to_dict()["puzzles"]
    assert spread.composition.to_dict()["puzzles"]["layout"] == "spread"
    assert build_identity(single) != build_identity(spread)
    explicit = book(layout="single")
    assert build_identity(explicit) == build_identity(single)


def test_corrupted_spreads_fail_verification():
    project = book(layout="spread", puzzles=3)
    report, plan = build_publication(project)
    pages = list(plan.pages)
    word = next(i for i, p in enumerate(pages) if p.kind is PageKind.PUZZLE_WORDS)
    pages[word], pages[word + 1] = (
        replace(pages[word + 1], index=pages[word].index),
        replace(pages[word], index=pages[word + 1].index),
    )
    broken = replace(plan, pages=tuple(pages))
    codes = {i.code for i in verify_publication_plan(broken, project, report).issues}
    assert "spread" in codes
    single = book(puzzles=3)
    report2, _ = build_publication(single)
    assert not verify_publication_plan(plan, single, report2).valid


# ------------------------------------------------------------------ previews


def test_sample_pages_cover_spread_answers_and_final_answer_page():
    project = book(RACING, per_page=4, puzzles=9, dividers={"start": "any", "themes": []})
    sample = sample_interior(project, PAPERBACK_LETTER)
    roles = {role: page for page in sample.pages for role in page.roles}
    assert {"title", "puzzle", "spread_left", "spread_right", "answers", "answers_last"} <= set(
        roles
    )
    assert "divider" in roles
    assert roles["spread_left"].physical_page % 2 == 0
    assert roles["spread_right"].physical_page == roles["spread_left"].physical_page + 1
    assert roles["answers"].kind == roles["answers_last"].kind == "solutions"
    reader = PdfReader(io.BytesIO(sample.pdf))
    assert len(reader.pages) == len(sample.pages)
    full = build(project)
    assert sample.page_count == len(full.layout.pages)


# ------------------------------------------------------------------ staleness


def failed(project, artifacts):
    """Failed rule codes mapped to their findings."""
    report = preflight_interior(project, artifacts).report
    codes = {r.rule.code for r in report.results if r.outcome.value == "failed"}
    return {code: [f for f in report.findings if f.rule.code == code] for code in codes}


def test_design_and_answer_changes_make_the_built_interior_stale(tmp_path):
    project = book(RACING, per_page=4)
    out = tmp_path / "out"
    write_interior(build(project), out, tmp_path / "src")
    artifacts = read_interior_artifacts(out)
    assert "source_current" not in failed(project, artifacts)
    restyled = failed(book({**RACING, "theme": "ink_saver"}, per_page=4), artifacts)
    (finding,) = restyled["source_current"]
    assert finding.region == "style" and "interior style changed" in finding.message
    repaginated = failed(book(RACING, per_page=2), artifacts)
    assert repaginated["source_current"][0].region == "identity"
    assert "plan_current" in repaginated


def test_design_legibility_is_a_preflight_warning(tmp_path):
    project = book(RACING, per_page=8, puzzles=9, size=10)
    out = tmp_path / "out"
    write_interior(build(project), out, tmp_path / "src")
    report = preflight_interior(project, read_interior_artifacts(out)).report
    result = next(r for r in report.results if r.rule.code == "design_legibility")
    assert result.outcome.value == "failed" and result.rule.severity.value == "warning"
    findings = [f for f in report.findings if f.rule.code == "design_legibility"]
    assert findings and {f.subject for f in findings} == {"dense_solution_page"}
    assert report.structurally_valid


# ------------------------------------------------------------------ design files


def test_design_files_round_trip_without_photos_or_book_details():
    style, _ = validate_interior_style(
        {**RACING, "colors": {"accent": "#cc3300"}, "puzzle_pages": {"puzzle_number": True}},
        True,
    )
    data = export_design(style, "Automotive Racing")
    document = json.loads(data)
    assert document["format"] == "puzzlepress-interior-design" and document["name"] == (
        "Automotive Racing"
    )
    assert set(document) == {"format", "format_version", "name", "interior"}
    name, imported = import_design(data, None, True)
    assert name == "Automotive Racing" and imported == style
    assert export_design(imported, "Automotive Racing") == data


def test_design_files_keep_the_receiving_books_photos(tmp_path):
    photo = {"image": {"path": "cover-assets/a.jpg", "sha256": "a" * 64}}
    current, issues = validate_interior_style(
        {"version": 2, "dividers": {"photos": [{"theme": "Tools", **photo}]}}, True
    )
    assert not issues
    exported = export_design(current, "Mine")
    assert "photos" not in exported.decode()
    _, merged = import_design(
        export_design(validate_interior_style(RACING, True)[0], "R"), current, True
    )
    assert merged.dividers.photos == current.dividers.photos and merged.theme is Theme.RACING_ORANGE


@pytest.mark.parametrize(
    ("data", "code"),
    [
        (b"not json", "json"),
        (b"[]", "format"),
        (
            b'{"format": "x", "format_version": 1, "name": "n", "interior": {}}',
            "unsupported_version",
        ),
        (
            b'{"format": "puzzlepress-interior-design", "format_version": 1, "name": "", '
            b'"interior": {"version": 2}}',
            "text",
        ),
        (
            b'{"format": "puzzlepress-interior-design", "format_version": 1, "name": "n", '
            b'"interior": {"version": 2, "theme": "lava"}}',
            "choice",
        ),
        (
            b'{"format": "puzzlepress-interior-design", "format_version": 1, "name": "n", '
            b'"interior": {"version": 2, "title_page": {"photo": {}}}}',
            "photos_not_portable",
        ),
        (b"{" + b" " * 70000 + b"}", "too_large"),
    ],
    ids=["json", "format", "version", "name", "theme", "photos", "size"],
)
def test_bad_design_files_are_refused(data, code):
    with pytest.raises(DesignFileError) as error:
        import_design(data, None, True)
    assert code in [i.code for i in error.value.issues]


def test_saving_a_design_keeps_every_other_section(tmp_path):
    from puzzlepress.yaml_io import dump_project, parse_project

    project = book()
    styled = validate_project({**project.to_dict(), "interior": RACING}).require_project()
    reloaded = parse_project(dump_project(styled))
    assert reloaded == styled and reloaded.interior.theme is Theme.RACING_ORANGE
    assert replace(reloaded, interior=None) == project


def test_style_without_composition_is_refused():
    data = book().to_dict()
    del data["composition"]
    data["interior"] = RACING
    with pytest.raises(ProjectError):
        validate_project(data).require_project()
