"""The automotive production book, end to end: content, plan, interior, cover facts, publishing.

One interior build per module run keeps this bounded. Everything is written to
temporary directories; books/automotive is only read. The cover check uses a
SYNTHETIC stand-in photograph in a temporary copy: the real book has no
authorized photograph yet and must not get one from tests.
"""

import hashlib
import os
import re
import subprocess
import sys
from collections import Counter

import pytest

from puzzlepress import build_identity, load_project, validate_project
from puzzlepress.batch import derive_puzzle_seed, generate_batch
from puzzlepress.cover.assets import import_photo
from puzzlepress.cover.build import build_cover
from puzzlepress.cover.geometry import cover_geometry
from puzzlepress.interior import build_interior, write_interior
from puzzlepress.interior.spec import KDP_COVER, PAPERBACK_LETTER, Paper, inches
from puzzlepress.planning import comparison_document, evaluate_plan, read_planning
from puzzlepress.preflight import Severity, preflight_interior, read_interior_artifacts
from puzzlepress.publication import PageKind
from puzzlepress.publishing import evaluate_readiness, validate_metadata
from puzzlepress.wordsearch import verify_word_search
from puzzlepress.yaml_io import dump_project
from tests.cover_helpers import photo_bytes
from tests.helpers import ROOT

BOOK = ROOT / "books" / "automotive"
THEMES = {"engines": 10, "maintenance": 10, "tools": 8, "systems": 10, "motorsport": 8,
          "history": 6, "driving": 8}  # fmt: skip
LEVELS = {"warm-up": (13, 3), "standard": (15, 4), "challenge": (17, 8)}


@pytest.fixture(scope="module")
def project():  # type: ignore[no-untyped-def]
    return load_project(BOOK).project


@pytest.fixture(scope="module")
def built(project, tmp_path_factory):  # type: ignore[no-untyped-def]
    build = build_interior(project, PAPERBACK_LETTER)
    out = tmp_path_factory.mktemp("automotive") / "out"
    write_interior(build, out, BOOK)
    return build, out


# ------------------------------------------------------------------- content


def test_sixty_identifiable_puzzles_in_seven_themes_and_three_levels(project) -> None:  # type: ignore[no-untyped-def]
    content = project.word_search
    puzzles = content.puzzles
    assert len(puzzles) == 60 and len({p.id for p in puzzles}) == 60
    assert len({p.title for p in puzzles}) == 60
    themes = Counter(p.id.rsplit("-", 1)[0] for p in puzzles)
    assert dict(themes) == THEMES
    for p in puzzles:
        assert re.fullmatch(r"[a-z]+-\d\d", p.id)
        assert p.bank in (p.id.rsplit("-", 1)[0], p.id.rsplit("-", 1)[0] + "-challenge")
    # Gradual progression: 20 warm-up, 20 standard, 20 challenge, never stepping back.
    assert [p.difficulty for p in puzzles] == ["warm-up"] * 20 + ["standard"] * 20 + [
        "challenge"
    ] * 20
    profiles = {p.id: p.config for p in content.profiles}
    for level, (side, directions) in LEVELS.items():
        config = profiles[level]
        assert (config.size.width, config.size.height, len(config.directions)) == (
            side, side, directions
        )  # fmt: skip
    counts = {lvl: {len(p.target_ids) for p in puzzles if p.difficulty == lvl} for lvl in LEVELS}
    assert counts == {"warm-up": {10, 11}, "standard": {13, 14}, "challenge": {16}}
    assert max(len(b.entries) for b in content.banks) <= 100


def test_every_word_is_placed_verified_and_screened_clean(project) -> None:  # type: ignore[no-untyped-def]
    report = generate_batch(project)
    assert report.success and report.clean and report.findings == ()
    assert len(report.content.similarities) == 60 * 59 // 2
    assert project.word_search.quality.prohibited_words  # Screening is enabled.
    for result in report.puzzles:
        assert result.seed == derive_puzzle_seed(project.build.seed, result.id)
        assert result.puzzle is not None and verify_word_search(result.puzzle).valid
        definition = next(p for p in project.word_search.puzzles if p.id == result.id)
        assert len(result.puzzle.solution.placements) == len(definition.target_ids)
        quality = result.quality
        assert quality is not None and quality.prohibited_screening_enabled
        assert not quality.accidental_targets.occurrences and not quality.prohibited.occurrences
    # No normalized word is used in more than two puzzles; almost none repeat.
    forms = Counter(
        e.display.replace(" ", "")
        for p in project.word_search.puzzles
        for e in project.word_search.entries_for(p)
    )
    assert max(forms.values()) == 2 and len(forms) == 787 and sum(forms.values()) == 793


def test_word_lists_print_in_alphabetical_order(project) -> None:  # type: ignore[no-untyped-def]
    for p in project.word_search.puzzles:
        forms = [e.display.replace(" ", "") for e in project.word_search.entries_for(p)]
        assert forms == sorted(forms), p.id


def test_the_book_matches_its_unapproved_plan(project) -> None:  # type: ignore[no-untyped-def]
    plan = read_planning(BOOK).document
    assert plan is not None
    doc = comparison_document(evaluate_plan(project, plan))
    assert doc["matches_plan"] is True
    assert doc["planning"]["approved"] is False and doc["planning"]["state"] == "needs_research"


# ------------------------------------------------------------------- plan and interior


def test_page_order_numbering_and_solution_references(built) -> None:  # type: ignore[no-untyped-def]
    build, _ = built
    plan = build.plan
    pages = plan.pages
    assert len(pages) == 95 and plan.complete
    assert [p.kind for p in pages[:4]] == [
        PageKind.TITLE_PAGE, PageKind.COPYRIGHT_PAGE, PageKind.INSTRUCTIONS, PageKind.BLANK
    ]  # fmt: skip
    puzzles = [p for p in pages if p.kind is PageKind.PUZZLE]
    assert [p.index for p in puzzles] == list(range(5, 65))
    assert all(p.side == "recto" if p.index % 2 else p.side == "verso" for p in pages)
    # Puzzle N is printed as page N; solutions follow on 61..90; the closing page is 91.
    assert [p.number.label for p in puzzles] == [str(n) for n in range(1, 61)]
    solutions = [p for p in pages if p.kind is PageKind.SOLUTIONS]
    assert [p.index for p in solutions] == list(range(65, 95)) and len(solutions) == 30
    assert [p.number.label for p in solutions] == [str(n) for n in range(61, 91)]
    assert pages[-1].kind is PageKind.ABOUT and pages[-1].number.label == "91"
    by_id = {p.puzzle.id: p for p in puzzles if p.puzzle}
    for page in solutions:
        assert len(page.solutions) == 2
        for item in page.solutions:
            assert by_id[item.puzzle.id].index == item.puzzle_page
            assert by_id[item.puzzle.id].solution_page == page.index
    assert [i.puzzle.id for p in solutions for i in p.solutions] == [
        p.puzzle.id for p in puzzles if p.puzzle
    ]
    assert not any(p.number.displayed for p in pages[:4])


def test_instructions_state_what_the_book_actually_contains(built, project) -> None:  # type: ignore[no-untyped-def]
    build, _ = built
    text = next(m.text for m in project.composition.front_matter if m.kind.value == "instructions")
    pages = [p for p in build.plan.pages if p.kind is PageKind.PUZZLE]
    for level, first, last in (("Warm-up", 1, 20), ("Standard", 21, 40), ("Challenge", 41, 60)):
        assert f"{level}, pages {first} to {last}:" in text
        side = LEVELS[level.lower()][0]
        assert f"{side} by {side} grids" in text
        chosen = pages[first - 1 : last]
        assert {p.puzzle.id for p in chosen} == {
            q.id for q in project.word_search.puzzles if q.difficulty == level.lower()
        }
    first_solution = next(p for p in build.plan.pages if p.kind is PageKind.SOLUTIONS)
    assert f"Solutions begin on page {first_solution.number.label}, two to a page." in text
    assert "10 or 11 words" in text and "13 or 14 words" in text and "16 words" in text


def test_interior_is_print_safe_and_preflights_valid_and_kdp_ready(project, built) -> None:  # type: ignore[no-untyped-def]
    build, out = built
    assert build.facts is not None and build.facts.page_count == 95
    assert all(font.embedded for page in build.facts.pages for font in page.fonts)
    report = preflight_interior(project, read_interior_artifacts(out), build).report
    assert report.page_count == 95
    assert report.structurally_valid and report.kdp_ready
    assert [f.rule.code for f in report.findings] == ["kdp_full_font_embedding"]
    assert report.source_identity == build_identity(project)


def test_interior_bytes_are_identical_across_processes(built, tmp_path) -> None:  # type: ignore[no-untyped-def]
    build, _ = built
    code = (
        "import hashlib, sys\n"
        "from puzzlepress import load_project\n"
        "from puzzlepress.interior import build_interior\n"
        "from puzzlepress.interior.spec import PAPERBACK_LETTER\n"
        "p = load_project(sys.argv[1]).project\n"
        "print(hashlib.sha256(build_interior(p, PAPERBACK_LETTER).pdf).hexdigest())\n"
    )
    env = {**os.environ, "PYTHONHASHSEED": "31337"}
    result = subprocess.run(
        [sys.executable, "-c", code, str(BOOK)],
        capture_output=True, text=True, cwd=tmp_path, env=env, check=True,
    )  # fmt: skip
    assert result.stdout.strip() == hashlib.sha256(build.pdf).hexdigest()


# ------------------------------------------------------------------- cover facts


def test_spine_geometry_comes_from_the_real_page_count(built) -> None:  # type: ignore[no-untyped-def]
    build, _ = built
    pages = len(build.layout.pages)
    trim = PAPERBACK_LETTER.trim
    white = cover_geometry(pages, trim.width, trim.height, Paper.WHITE)
    assert white.spine_width == pytest.approx(inches(95 * 0.002252))
    assert white.spine_text_allowed  # 95 pages reach the 80-page rule...
    assert pages >= KDP_COVER.spine_text_min_pages
    cream = cover_geometry(pages, trim.width, trim.height, Paper.CREAM)
    assert cream.spine_width == pytest.approx(inches(95 * 0.0025))


def test_spine_text_is_omitted_when_the_real_spine_is_too_narrow(project, built, tmp_path) -> None:  # type: ignore[no-untyped-def]
    build, _ = built
    source, out = tmp_path / "book", tmp_path / "out"
    source.mkdir()
    # SYNTHETIC stand-in photograph, in a temporary copy only.
    photo = import_photo(source, photo_bytes(5400, 3600), "synthetic.jpg")
    data = project.to_dict()
    data["output"] = {"directory": "../out"}
    data["cover"] = {"version": 1, "image": {"path": photo.path, "sha256": photo.info.sha256}}
    copy = validate_project(data).require_project()
    assert build_identity(copy) == build_identity(project)  # Cover and output are not identity.
    (source / "book.yaml").write_text(dump_project(copy), encoding="utf-8")
    write_interior(build, out, source)
    cover = build_cover(copy, source, out)
    spine = cover.manifest["spine_text"]
    assert spine["allowed_by_page_count"] is True
    # ...but 0.214 in of spine leaves 6.4 pt inside KDP's clearance: no text is forced.
    assert spine["rendered"] is False and spine["reason"] == "spine_too_narrow"


# ------------------------------------------------------------------- publishing


def test_publishing_stays_blocked_on_the_authors_decisions(project, built) -> None:  # type: ignore[no-untyped-def]
    build, out = built
    metadata = validate_metadata(project)
    blocking = {f.rule.code for f in metadata.findings if f.severity is Severity.ERROR}
    assert blocking == {
        "audience_explicit", "author_present", "isbn_decided", "low_content_decided",
        "ai_disclosure_complete", "attestations",
    }  # fmt: skip
    publishing = project.publishing
    assert publishing.ai_disclosure.to_dict() == {
        "text": "unknown", "images": "unknown", "translations": "unknown"
    }  # fmt: skip
    assert publishing.isbn.mode.value == "undecided" and publishing.isbn.value is None
    assert set(publishing.attestations.to_dict().values()) == {None}
    assert project.book.author is None and project.cover is None
    report = evaluate_readiness(project, BOOK, out)
    assert report.interior_state == "current"
    assert report.cover_state == "no_config"
    assert not report.package_ready
