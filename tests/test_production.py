"""Artifact assessment, dependency-aware rebuilds and the publishing overview."""

import shutil

import pytest

from puzzlepress import load_project
from puzzlepress.cover.build import build_cover, write_cover
from puzzlepress.interior.spec import PAPERBACK_LETTER
from puzzlepress.production.artifacts import assess
from puzzlepress.production.guidance import overview
from puzzlepress.production.rebuild import SourceChanged, rebuild
from puzzlepress.publishing import evaluate_readiness
from puzzlepress.validation import validate_project
from puzzlepress.yaml_io import dump_project
from tests.cover_helpers import cover_project
from tests.helpers import ROOT


def _save(source, data):
    project = validate_project(data).require_project()
    (source / "book.yaml").write_text(dump_project(project), encoding="utf-8")
    return project


def _state(source, output):
    project = load_project(source).project
    return project, assess(project, evaluate_readiness(project, source, output), source, output)


def _actions(assessment):
    return [(s.action, s.conditional) for s in assessment.steps]


def _run(source, output, assessment):
    project = load_project(source).project
    return rebuild(
        project, source, output, PAPERBACK_LETTER, tuple(s.action for s in assessment.steps)
    )


@pytest.fixture
def built(tmp_path):
    source, output = cover_project(tmp_path)
    project = load_project(source).project
    write_cover(build_cover(project, source, output), output, source)
    _, assessment = _state(source, output)
    rebuild(
        load_project(source).project,
        source,
        output,
        PAPERBACK_LETTER,
        tuple(s.action for s in assessment.steps),
    )
    return source, output


def test_missing_artifacts_plan_interior_then_cover(tmp_path):
    source, output = cover_project(tmp_path, build_interior=False)
    _, assessment = _state(source, output)
    assert assessment.state("interior").state == "missing"
    assert _actions(assessment) == [("build_interior", False), ("build_cover", False)]
    results = _run(source, output, assessment)
    assert [r.status for r in results] == ["succeeded", "succeeded"]
    _, after = _state(source, output)
    assert after.steps == () and after.state("cover").state == "current"
    assert after.state("interior_preflight").state == "current"
    assert after.state("cover_preflight").state == "current"


def test_cover_change_rebuilds_only_the_cover(built):
    source, output = built
    interior_before = (output / "interior.pdf").read_bytes()
    project = load_project(source).project
    data = project.to_dict()
    data["cover"]["type"]["style"] = "bold"
    _save(source, data)
    _, assessment = _state(source, output)
    assert _actions(assessment) == [("build_cover", False)]
    assert "cover design changed" in assessment.state("cover").reasons[0]
    assert not any(r.startswith("[") for r in assessment.state("cover").reasons)
    assert [r.status for r in _run(source, output, assessment)] == ["succeeded"]
    assert (output / "interior.pdf").read_bytes() == interior_before


def test_metadata_and_review_changes_rebuild_nothing(built):
    source, output = built
    data = load_project(source).project.to_dict()
    data["publishing"] = {"version": 2}
    _save(source, data)
    (source / "reviews.yaml").write_text("review_version: 1\npuzzles: []\n", encoding="utf-8")
    _, assessment = _state(source, output)
    assert assessment.steps == ()


def test_interior_change_rechecks_the_cover_conditionally(built):
    source, output = built
    data = load_project(source).project.to_dict()
    data["word_search"]["puzzles"][0]["title"] = "Along the Shore"
    _save(source, data)
    _, assessment = _state(source, output)
    assert _actions(assessment) == [("build_interior", False), ("build_cover", True)]
    results = _run(source, output, assessment)
    assert [(r.action, r.status) for r in results] == [
        ("build_interior", "succeeded"),
        ("build_cover", "unchanged"),  # Same page count and paper: the cover still fits.
    ]


def test_page_count_change_rebuilds_the_cover(built):
    source, output = built
    data = load_project(source).project.to_dict()
    data["composition"]["back_matter"] = [
        {"kind": "notes", "title": "Notes"},
        {"kind": "about", "title": "About", "text": "Hello."},
    ]
    _save(source, data)
    _, assessment = _state(source, output)
    results = _run(source, output, assessment)
    assert [(r.action, r.status) for r in results] == [
        ("build_interior", "succeeded"),
        ("build_cover", "succeeded"),
    ]
    _, after = _state(source, output)
    assert after.steps == ()


def test_failed_cover_keeps_the_previous_cover(built):
    source, output = built
    cover_before = (output / "cover.pdf").read_bytes()
    project = load_project(source).project
    data = project.to_dict()
    data["cover"]["crop"]["x"] = 0.2
    _save(source, data)
    (source / project.cover.image.path).unlink()
    _, assessment = _state(source, output)
    results = _run(source, output, assessment)
    assert results[0].status == "failed" and results[0].stage == "asset"
    assert (output / "cover.pdf").read_bytes() == cover_before


def test_partial_failure_skips_later_steps(tmp_path):
    source, output = cover_project(tmp_path, build_interior=False)
    project = load_project(source).project
    data = project.to_dict()
    data["word_search"]["puzzles"][0]["target_ids"] = ["shell"] * 1  # Still valid.
    _save(source, data)
    (source / project.cover.image.path).unlink()
    _, assessment = _state(source, output)
    results = _run(source, output, assessment)
    assert [r.status for r in results] == ["succeeded", "failed"]


def test_source_change_during_a_rebuild_stops_before_writing(tmp_path):
    source, output = cover_project(tmp_path, build_interior=False)
    _, assessment = _state(source, output)

    def changed():
        raise SourceChanged

    with pytest.raises(SourceChanged):
        rebuild(
            load_project(source).project,
            source,
            output,
            PAPERBACK_LETTER,
            tuple(s.action for s in assessment.steps),
            before_write=changed,
        )
    assert not (output / "interior.pdf").exists()


def test_rebuild_never_writes_outside_the_build_directory(built, tmp_path):
    source, output = built
    release = tmp_path / "releases" / "review-1"
    shutil.copytree(output, release)
    before = {p.name: p.read_bytes() for p in release.iterdir()}
    data = load_project(source).project.to_dict()
    data["word_search"]["puzzles"][0]["title"] = "Changed"
    _save(source, data)
    _, assessment = _state(source, output)
    _run(source, output, assessment)
    assert {p.name: p.read_bytes() for p in release.iterdir()} == before


# ------------------------------------------------------------------ guidance


def _publishing_demo(tmp_path):
    source = tmp_path / "publishing-demo"
    shutil.copytree(ROOT / "books" / "publishing-demo", source)
    project = load_project(source).project
    data = project.to_dict()
    data["output"] = {"directory": "../out"}
    project = _save(source, data)
    output = tmp_path / "out"
    _, assessment = _state(source, output)
    rebuild(project, source, output, PAPERBACK_LETTER, tuple(s.action for s in assessment.steps))
    return source, output


def test_overview_keeps_engine_checks_human_decisions_and_external_steps_apart(tmp_path):
    source, output = _publishing_demo(tmp_path)
    data = overview(load_project(source).project, source, output)
    items = {i["code"]: i for i in data["items"]}
    assert items["interior_current"]["status"] == "completed"
    assert items["cover_preflight"]["basis"] == "kdp_modeled"
    assert items["ai_disclosure"]["status"] == "awaiting_review"
    assert (
        items["ai_disclosure"]["basis"] == "author_judgment"
        and items["ai_disclosure"]["blocks_export"]
    )
    assert items["rights"]["status"] == "awaiting_review"
    assert items["human_review"]["status"] == "awaiting_review"
    assert items["human_review"]["blocks_export"] is False
    assert items["print_previewer"]["status"] == "external_pending"
    assert items["physical_proof"]["basis"] == "external"
    assert items["planning_approval"]["status"] == "not_applicable"
    stages = {s["code"]: s["reached"] for s in data["stages"]}
    assert stages["built"] is True and stages["exported"] is False
    assert stages["proof_reviewed"] is False and stages["published"] is None
    assert "Amazon KDP reviews and decides" in data["statement"]
    assert len(data["proofing"]) == 10


def test_overview_never_selects_answers(tmp_path):
    source, output = _publishing_demo(tmp_path)
    before = (source / "book.yaml").read_bytes()
    overview(load_project(source).project, source, output)
    assert (source / "book.yaml").read_bytes() == before
    assert not (source / "reviews.yaml").exists() and not (source / "proofs.yaml").exists()


def test_review_policy_is_an_internal_gate(tmp_path):
    source, output = _publishing_demo(tmp_path)
    (source / "reviews.yaml").write_text(
        "review_version: 1\npolicy: {require_all: true}\npuzzles: []\n", encoding="utf-8"
    )
    items = {i["code"]: i for i in overview(load_project(source).project, source, output)["items"]}
    assert items["human_review"]["status"] == "blocking"
    assert items["human_review"]["blocks_export"] is False
    assert "not a KDP requirement" not in items["human_review"]["why"]
    assert "KDP does not require them" in items["human_review"]["why"]


def test_stale_preflight_says_out_of_date_not_broken(tmp_path):
    source, output = _publishing_demo(tmp_path)
    data = load_project(source).project.to_dict()
    data["word_search"]["puzzles"][0]["title"] = "Renamed Puzzle"
    _save(source, data)
    items = {i["code"]: i for i in overview(load_project(source).project, source, output)["items"]}
    assert items["interior_current"]["status"] == "blocking"
    assert items["interior_preflight"]["status"] == "blocking"
    assert "out of date" in items["interior_preflight"]["detail"]
