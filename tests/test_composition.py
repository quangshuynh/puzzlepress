"""Composition schema, publication planning and independent plan verification."""

import copy
import json
from dataclasses import replace
from pathlib import Path

import pytest

from puzzlepress import (
    build_identity,
    canonical_build_inputs,
    dump_project,
    load_project,
    parse_project,
    validate_project,
)
from puzzlepress.batch import derive_puzzle_seed, generate_batch
from puzzlepress.composition import NumberingScheme, SolutionPlacement
from puzzlepress.errors import ProjectError, ValidationIssue
from puzzlepress.publication import (
    BLANK_REASON,
    NumberStyle,
    PageKind,
    PageNumber,
    PlanPage,
    Section,
    Side,
    build_publication,
    plan_publication,
    roman,
)
from puzzlepress.publication_verification import verify_publication_plan

ROOT = Path(__file__).resolve().parents[1]
DEMO = ROOT / "books" / "composition-demo"
MINIMAL = {"solutions": {"placement": "end", "title": "Solutions"}}


@pytest.fixture
def demo():
    return load_project(DEMO).project


def composed(base, composition=None):
    data = base.to_dict()
    data["composition"] = copy.deepcopy(MINIMAL if composition is None else composition)
    return data


def project_with(base, composition):
    return validate_project(composed(base, composition)).require_project()


def issues(data):
    return {(i.path, i.code) for i in validate_project(data).issues}


def plan(project):
    report, result = build_publication(project)
    assert verify_publication_plan(result, project, report).valid
    return result


def summary(result):
    return [
        (p.index, p.side.value, p.kind.value, p.number.label, p.number.displayed)
        for p in result.pages
    ]


def test_demo_round_trips_and_plans_reading_order(demo):
    assert parse_project(dump_project(demo)) == demo
    assert demo.composition.page_numbers.scheme is NumberingScheme.ROMAN_FRONT_MATTER
    result = plan(demo)
    assert summary(result) == [
        (1, "recto", "title_page", "i", False),
        (2, "verso", "copyright_page", "ii", False),
        (3, "recto", "instructions", "iii", False),
        (4, "verso", "blank", "iv", False),
        (5, "recto", "puzzle", "1", True),
        (6, "verso", "puzzle", "2", True),
        (7, "recto", "puzzle", "3", True),
        (8, "verso", "puzzle", "4", True),
        (9, "recto", "solutions", "5", True),
        (10, "verso", "solutions", "6", True),
        (11, "recto", "notes", "7", True),
    ]
    blank = result.pages[3]
    assert (blank.section, blank.blank_reason, blank.blank_before) == (
        Section.FRONT_MATTER,
        BLANK_REASON,
        Section.PUZZLES,
    )
    title = result.pages[0].matter
    assert (title.title, title.subtitle, title.author) == (
        "Seaside Word Searches",
        "A small composition demonstration",
        "PuzzlePress Examples",
    )
    assert result.pages[2].matter.text.splitlines()[0].startswith("Find each listed word")
    assert result.pages[8].heading == "Solutions" and result.pages[9].heading is None
    assert [s.puzzle.id for s in result.pages[8].solutions] == ["shoreline", "rockpool"]
    assert [(p.puzzle.id, p.solution_page) for p in result.pages[4:8]] == [
        ("shoreline", 9),
        ("rockpool", 9),
        ("harbour", 10),
        ("dunes", 10),
    ]
    assert result.pages[9].solutions[0].puzzle_page == 7
    stats = result.statistics
    assert (stats.logical_pages, stats.blank_pages, stats.puzzles, stats.solutions) == (11, 1, 4, 4)
    assert (stats.front_matter_pages, stats.solution_pages, stats.back_matter_pages) == (3, 2, 1)
    assert (stats.first_puzzle_page, stats.first_solution_page) == (5, 9)
    assert result.complete and not result.diagnostics


def test_legacy_projects_keep_identity_and_have_no_composition(garden, source):
    legacy = parse_project(source)
    assert legacy.composition is None and garden.composition is None
    assert "composition" not in garden.to_dict()
    assert b"composition" not in canonical_build_inputs(garden)
    assert build_identity(garden) == (
        "pp1-sha256-85966304262a0b3af4ffee5c742099e5635e1c4d52c817fa20334681101a6f84"
    )
    with pytest.raises(ProjectError) as error:
        build_publication(garden)
    assert [(i.path, i.code) for i in error.value.issues] == [("composition", "required")]


def test_defaults_are_explicit_after_normalization(garden):
    project = project_with(garden, MINIMAL)
    assert project.composition.to_dict() == {
        "front_matter": [],
        "puzzles": {"start": "any"},
        "solutions": {"placement": "end", "title": "Solutions", "per_page": 1, "start": "any"},
        "back_matter": [],
        "page_numbers": {
            "scheme": "continuous",
            "show_front_matter": False,
            "show_solutions": True,
            "show_back_matter": True,
        },
    }
    explicit = project_with(garden, project.composition.to_dict())
    assert build_identity(explicit) == build_identity(project)
    omitted = project_with(garden, {"solutions": {"placement": "omit"}})
    assert omitted.composition.to_dict()["solutions"] == {"placement": "omit"}
    assert parse_project(dump_project(omitted)) == omitted


def test_composition_participates_in_identity(garden):
    base = project_with(garden, MINIMAL)
    material = json.loads(canonical_build_inputs(base))
    assert material["composition_version"] == 1
    assert build_identity(base) != build_identity(garden)
    variants = [
        {**MINIMAL, "front_matter": [{"kind": "title_page"}]},
        {**MINIMAL, "puzzles": {"start": "recto"}},
        {"solutions": {"placement": "end", "title": "Answers"}},
        {"solutions": {"placement": "end", "title": "Solutions", "per_page": 2}},
        {"solutions": {"placement": "omit"}},
        {**MINIMAL, "back_matter": [{"kind": "notes", "title": "Notes"}]},
        {**MINIMAL, "page_numbers": {"show_solutions": False}},
    ]
    identities = {build_identity(project_with(garden, v)) for v in variants}
    assert len(identities) == len(variants) and build_identity(base) not in identities


@pytest.mark.parametrize(
    ("change", "expected"),
    [
        (lambda c: c.update(front_matter=[{"kind": "notes", "title": "N"}]), "kind"),
        (lambda c: c.update(front_matter=[{"kind": "title_page"}] * 2), "duplicate_kind"),
        (
            lambda c: c.update(
                front_matter=[
                    {"kind": "instructions", "title": "T", "text": "x"},
                    {"kind": "title_page"},
                ]
            ),
            "order",
        ),
        (lambda c: c.update(front_matter=[{"kind": "copyright_page"}]), "text"),
        (lambda c: c.update(front_matter=[{"kind": "copyright_page", "text": "  "}]), "text"),
        (lambda c: c.update(front_matter=[{"kind": "copyright_page", "text": "x" * 2001}]), "text"),
        (lambda c: c.update(front_matter=[{"kind": "copyright_page", "text": "a\tb"}]), "text"),
        (
            lambda c: c.update(
                front_matter=[{"kind": "instructions", "title": "A\nB", "text": "x"}]
            ),
            "text",
        ),
        (lambda c: c.update(front_matter=[{"kind": "title_page", "text": "x"}]), "unknown_field"),
        (lambda c: c.update(front_matter=["title_page"]), "type"),
        (lambda c: c.update(back_matter=[{"kind": "title_page"}]), "kind"),
        (lambda c: c.update(back_matter={"kind": "notes"}), "count"),
        (lambda c: c.update(extra=True), "unknown_field"),
        (lambda c: c.pop("solutions"), "required"),
        (lambda c: c["solutions"].update(placement="middle"), "choice"),
        (lambda c: c["solutions"].pop("title"), "text"),
        (lambda c: c["solutions"].update(per_page=3), "choice"),
        (lambda c: c["solutions"].update(per_page=True), "choice"),
        (lambda c: c["solutions"].update(start="verso"), "choice"),
        (lambda c: c.update(solutions={"placement": "omit", "per_page": 2}), "not_applicable"),
        (lambda c: c.update(puzzles={"start": "left"}), "choice"),
        (lambda c: c.update(puzzles=["flowers"]), "type"),
        (
            lambda c: c.update(page_numbers={"scheme": "roman_front_matter"}),
            "requires_front_matter",
        ),
        (lambda c: c.update(page_numbers={"show_solutions": "yes"}), "type"),
        (lambda c: c.update(page_numbers={"scheme": "roman"}), "choice"),
    ],
)
def test_invalid_composition_is_reported_not_repaired(garden, change, expected):
    composition = copy.deepcopy(MINIMAL)
    change(composition)
    found = issues(composed(garden, composition))
    assert expected in {code for _, code in found}
    assert all(path.startswith("composition") for path, _ in found)


def test_independent_errors_are_collected_and_puzzles_are_required(garden, source):
    composition = {
        "front_matter": [{"kind": "copyright_page"}, {"kind": "blank"}],
        "solutions": {"placement": "end", "title": "Solutions", "per_page": 5},
        "page_numbers": {"show_back_matter": 1},
    }
    found = issues(composed(garden, composition))
    assert {
        ("composition.front_matter.0.text", "text"),
        ("composition.front_matter.1.kind", "kind"),
        ("composition.solutions.per_page", "choice"),
        ("composition.page_numbers.show_back_matter", "type"),
    } <= found
    legacy = parse_project(source).to_dict()
    legacy["composition"] = MINIMAL
    assert ("composition", "requires_puzzles") in issues(legacy)
    legacy["composition"] = None
    assert ("composition", "type") in issues(legacy)


@pytest.mark.parametrize(("front", "blanks"), [(0, 0), (1, 1), (2, 0), (3, 1)])
def test_recto_starts_insert_only_needed_blanks(garden, front, blanks):
    matter = [
        {"kind": "title_page"},
        {"kind": "copyright_page", "text": "Notice."},
        {"kind": "instructions", "title": "How", "text": "Find words."},
    ][:front]
    composition = {
        "front_matter": matter,
        "puzzles": {"start": "recto"},
        "solutions": {"placement": "end", "title": "Solutions", "start": "recto"},
    }
    result = plan(project_with(garden, composition))
    puzzles = [p for p in result.pages if p.kind is PageKind.PUZZLE]
    solutions = [p for p in result.pages if p.kind is PageKind.SOLUTIONS]
    assert puzzles[0].side is Side.RECTO and solutions[0].side is Side.RECTO
    # Two recto-started puzzles end on verso, so solutions need no extra blank.
    assert result.statistics.blank_pages == blanks
    if blanks:
        blank = result.pages[front]
        assert (blank.kind, blank.section, blank.blank_before) == (
            PageKind.BLANK,
            Section.FRONT_MATTER,
            Section.PUZZLES,
        )
        assert not blank.number.displayed and blank.number.label == str(blank.index)


def test_recto_solutions_blank_belongs_to_preceding_section(garden):
    composition = {
        "front_matter": [{"kind": "title_page"}],
        "solutions": {"placement": "end", "title": "Solutions", "start": "recto"},
    }
    result = plan(project_with(garden, composition))
    assert [p.kind.value for p in result.pages] == [
        "title_page",
        "puzzle",
        "puzzle",
        "blank",
        "solutions",
        "solutions",
    ]
    blank = result.pages[3]
    assert (blank.section, blank.blank_before, blank.side) == (
        Section.PUZZLES,
        Section.SOLUTIONS,
        Side.VERSO,
    )


def test_any_start_never_inserts_blanks(demo):
    data = demo.to_dict()
    data["composition"]["puzzles"]["start"] = "any"
    data["composition"]["solutions"]["start"] = "any"
    result = plan(validate_project(data).require_project())
    assert result.statistics.blank_pages == 0
    assert [p.side for p in result.pages[:2]] == [Side.RECTO, Side.VERSO]


@pytest.mark.parametrize(
    ("per_page", "groups"), [(1, [1, 1, 1, 1]), (2, [2, 2]), (4, [4]), (6, [4])]
)
def test_solution_grouping_and_coverage(demo, per_page, groups):
    data = demo.to_dict()
    data["composition"]["solutions"]["per_page"] = per_page
    result = plan(validate_project(data).require_project())
    pages = [p for p in result.pages if p.kind is PageKind.SOLUTIONS]
    assert [len(p.solutions) for p in pages] == groups
    assert [s.puzzle.id for p in pages for s in p.solutions] == [
        "shoreline",
        "rockpool",
        "harbour",
        "dunes",
    ]
    puzzles = {p.puzzle.id: p for p in result.pages if p.puzzle}
    for page in pages:
        for item in page.solutions:
            assert item.puzzle == puzzles[item.puzzle.id].puzzle
            assert puzzles[item.puzzle.id].solution_page == page.index


def test_omitted_solutions_and_continuous_numbering(demo):
    data = demo.to_dict()
    data["composition"]["solutions"] = {"placement": "omit"}
    data["composition"]["page_numbers"] = {"scheme": "continuous", "show_front_matter": True}
    project = validate_project(data).require_project()
    assert project.composition.solutions.placement is SolutionPlacement.OMIT
    result = plan(project)
    assert not any(p.kind is PageKind.SOLUTIONS or p.solution_page for p in result.pages)
    assert result.statistics.solutions == 0 and result.statistics.first_solution_page is None
    assert [p.number.label for p in result.pages] == [str(i) for i in range(1, 10)]
    assert all(p.number.style is NumberStyle.ARABIC for p in result.pages)
    assert [p.number.displayed for p in result.pages[:5]] == [True, True, True, False, True]


def test_publication_order_follows_authored_puzzles_and_keeps_bindings(demo):
    original = plan(demo)
    data = demo.to_dict()
    data["word_search"]["puzzles"].reverse()
    reordered = plan(validate_project(data).require_project())
    before = {p.puzzle.id: p.puzzle for p in original.pages if p.puzzle}
    after = [p.puzzle for p in reordered.pages if p.puzzle]
    assert [r.id for r in after] == ["dunes", "harbour", "rockpool", "shoreline"]
    assert [r.ordinal for r in after] == [1, 2, 3, 4]
    for ref in after:
        assert (ref.seed, ref.digest) == (before[ref.id].seed, before[ref.id].digest)
        assert ref.seed == derive_puzzle_seed(demo.build.seed, ref.id)


def test_plans_are_deterministic_and_reject_unrelated_reports(demo, garden):
    report, first = build_publication(demo)
    assert first == build_publication(demo)[1] == plan_publication(demo, report)
    assert json.dumps(first.to_dict(), sort_keys=True) == json.dumps(
        plan_publication(demo, generate_batch(demo)).to_dict(), sort_keys=True
    )
    payload = first.to_dict()
    assert payload["pages"][4]["puzzle"]["seed"] == str(first.pages[4].puzzle.seed)
    assert payload["pages"][4]["puzzle"]["digest"].startswith("sha256-")
    with pytest.raises(ValueError):
        plan_publication(demo, generate_batch(project_with(garden, MINIMAL)))


def test_generation_failure_is_diagnosed_not_omitted(demo):
    data = demo.to_dict()
    data["word_search"]["profiles"].append(
        {"id": "tiny", "width": 4, "height": 4, "directions": ["right"], "max_restarts": 1}
    )
    data["word_search"]["puzzles"][1]["difficulty"] = "tiny"
    data["word_search"]["puzzles"][1]["target_ids"] = ["crab", "kelp", "tide", "wave", "sand"]
    project = validate_project(data).require_project()
    report, result = build_publication(project)
    assert not report.success and not result.complete
    assert [(d.path, d.code) for d in result.diagnostics] == [
        ("word_search.puzzles.1", "generation_failed")
    ]
    failed = [p for p in result.pages if p.puzzle and p.puzzle.id == "rockpool"][0]
    assert failed.puzzle.digest is None and failed.solution_page is not None
    assert result.statistics.puzzles == 4 and result.statistics.solutions == 4
    assert verify_publication_plan(result, project, report).valid


def corrupt_pages(result, mutate):
    pages = list(result.pages)
    mutate(pages)
    return replace(result, pages=tuple(pages))


def page_at(pages, kind, n=0):
    return [i for i, p in enumerate(pages) if p.kind is kind][n]


CORRUPTIONS = {
    "swapped puzzles": lambda pages: pages.__setitem__(
        slice(4, 6), [replace(pages[5], index=5), replace(pages[4], index=6)]
    ),
    "dropped solution": lambda pages: pages.__setitem__(
        8, replace(pages[8], solutions=pages[8].solutions[:1])
    ),
    "foreign digest": lambda pages: pages.__setitem__(
        9,
        replace(
            pages[9],
            solutions=(
                replace(
                    pages[9].solutions[0],
                    puzzle=replace(pages[9].solutions[0].puzzle, digest="sha256-0"),
                ),
                pages[9].solutions[1],
            ),
        ),
    ),
    "wrong puzzle digest": lambda pages: pages.__setitem__(
        4, replace(pages[4], puzzle=replace(pages[4].puzzle, digest=None))
    ),
    "wrong seed": lambda pages: pages.__setitem__(
        4, replace(pages[4], puzzle=replace(pages[4].puzzle, seed=1))
    ),
    "unjustified blank": lambda pages: pages.__setitem__(
        1,
        replace(
            pages[1],
            kind=PageKind.BLANK,
            matter=None,
            blank_reason=BLANK_REASON,
            blank_before=Section.PUZZLES,
        ),
    ),
    "missing blank": lambda pages: pages.__setitem__(
        slice(None), [replace(p, index=i) for i, p in enumerate(pages[:3] + pages[4:], 1)]
    ),
    "blank reason": lambda pages: pages.__setitem__(3, replace(pages[3], blank_reason="spacing")),
    "number value": lambda pages: pages.__setitem__(
        6, replace(pages[6], number=replace(pages[6].number, value=9))
    ),
    "number style": lambda pages: pages.__setitem__(
        4, replace(pages[4], number=PageNumber(5, NumberStyle.ROMAN, True))
    ),
    "hidden puzzle number": lambda pages: pages.__setitem__(
        5, replace(pages[5], number=replace(pages[5].number, displayed=False))
    ),
    "shown blank number": lambda pages: pages.__setitem__(
        3, replace(pages[3], number=replace(pages[3].number, displayed=True))
    ),
    "second heading": lambda pages: pages.__setitem__(9, replace(pages[9], heading="Solutions")),
    "cross reference": lambda pages: pages.__setitem__(4, replace(pages[4], solution_page=10)),
    "solution page ref": lambda pages: pages.__setitem__(
        8,
        replace(
            pages[8],
            solutions=(replace(pages[8].solutions[0], puzzle_page=6), pages[8].solutions[1]),
        ),
    ),
    "matter text": lambda pages: pages.__setitem__(
        1, replace(pages[1], matter=replace(pages[1].matter, text="Invented legal text."))
    ),
    "section order": lambda pages: pages.__setitem__(
        10, replace(pages[10], section=Section.FRONT_MATTER)
    ),
    "gap": lambda pages: pages.__setitem__(10, replace(pages[10], index=12)),
    "puzzle in solutions": lambda pages: pages.__setitem__(
        5, replace(pages[5], section=Section.SOLUTIONS)
    ),
}


@pytest.mark.parametrize("name", sorted(CORRUPTIONS))
def test_verifier_rejects_corrupted_pages(demo, name):
    report, result = build_publication(demo)
    assert verify_publication_plan(result, demo, report).valid
    corrupted = corrupt_pages(result, CORRUPTIONS[name])
    assert corrupted != result
    assert not verify_publication_plan(corrupted, demo, report).valid


def test_verifier_rejects_corrupted_plan_metadata_and_other_sources(demo):
    report, result = build_publication(demo)
    for corrupted in (
        replace(result, identity="pp1-sha256-0"),
        replace(result, plan_version=2),
        replace(result, statistics=replace(result.statistics, logical_pages=12)),
        replace(result, statistics=replace(result.statistics, blank_pages=0)),
        replace(
            result,
            diagnostics=(ValidationIssue("word_search.puzzles.0", "generation_failed", "x"),),
        ),
        replace(result, pages=()),
    ):
        assert not verify_publication_plan(corrupted, demo, report).valid
    data = demo.to_dict()
    data["build"]["seed"] = 7
    other = validate_project(data).require_project()
    assert not verify_publication_plan(result, other, generate_batch(other)).valid
    reordered = demo.to_dict()
    reordered["composition"]["solutions"]["per_page"] = 4
    changed = validate_project(reordered).require_project()
    assert not verify_publication_plan(
        replace(result, identity=build_identity(changed)), changed, generate_batch(changed)
    ).valid


def test_roman_numbers():
    assert [roman(n) for n in (1, 4, 9, 14, 40, 90, 400, 1994, 3999)] == [
        "i",
        "iv",
        "ix",
        "xiv",
        "xl",
        "xc",
        "cd",
        "mcmxciv",
        "mmmcmxcix",
    ]
    for bad in (0, 4000):
        with pytest.raises(ValueError):
            roman(bad)
    page = PlanPage(2, Section.PUZZLES, PageKind.PUZZLE, PageNumber(1, NumberStyle.ARABIC, True))
    assert page.side is Side.VERSO


def test_matter_issue_paths_use_source_positions(garden):
    composition = {
        "front_matter": [{"kind": "bogus"}, {"kind": "title_page"}, {"kind": "title_page"}],
        "solutions": {"placement": "omit"},
    }
    assert issues(composed(garden, composition)) == {
        ("composition.front_matter.0.kind", "kind"),
        ("composition.front_matter.1", "order"),
        ("composition.front_matter.2", "order"),
        ("composition.front_matter.2.kind", "duplicate_kind"),
    }
    data = composed(garden)
    data["composition"] = "title_page"
    assert issues(data) == {("composition", "type")}
