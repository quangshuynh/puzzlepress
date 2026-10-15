"""Publishing readiness: artifact integrity, staleness, preflight consumption, verdicts."""

import hashlib
import json

import pytest

from puzzlepress import load_project
from puzzlepress.cover.preflight import preflight_cover
from puzzlepress.cover.preflight import report_bytes as cover_report_bytes
from puzzlepress.interior import build_interior, print_profile, write_interior
from puzzlepress.preflight import preflight_interior, read_interior_artifacts
from puzzlepress.preflight import report_bytes as interior_report_bytes
from puzzlepress.publishing.model import Outcome
from puzzlepress.publishing.readiness import evaluate_readiness, readiness_bytes
from tests.publishing_helpers import publishing_project, reconfirm


def evaluate(source, output):
    return evaluate_readiness(load_project(source).project, source, output)


def edit(source, old, new):
    path = source / "book.yaml"
    text = path.read_text(encoding="utf-8")
    assert old in text, old
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


def errors(report):
    return sorted({f.rule.code for f in report.findings if f.severity.value == "error"})


def messages(report, code):
    return [f.message for f in report.findings if f.rule.code == code]


def outcome(report, code):
    return next(r.outcome for r in report.results if r.rule.code == code)


def snapshot(*directories):
    return {
        p.as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for d in directories
        for p in sorted(d.rglob("*"))
        if p.is_file()
    }


@pytest.fixture
def ready(tmp_path):
    return publishing_project(tmp_path)


def test_current_interior_and_cover_with_complete_metadata_is_ready(ready):
    source, output = ready
    report = evaluate(source, output)
    assert report.package_ready
    assert report.verdicts() == {
        "metadata": "valid",
        "disclosure": "complete",
        "attestations": "complete",
        "interior": {"state": "current", "structural": "valid", "kdp": "ready"},
        "cover": {"state": "current", "structural": "valid", "kdp": "ready"},
        "artifacts": "current",
        "package": "ready",
    }
    assert "Ready for manual KDP submission" in report.statement()
    assert "Amazon KDP reviews and decides" in report.statement()
    # Preflight warnings are carried, not escalated or dropped.
    warnings = {(f.rule.code, f.related) for f in report.findings if f.severity.value == "warning"}
    assert ("interior_warnings", "kdp_full_font_embedding") in warnings
    assert ("cover_warnings", "kdp_cover_color_space") in warnings
    config = report.print_configuration()
    assert config["page_count"] == 29 and config["paper"] == "white" and config["ink"] == "black"
    assert config["cover"]["spine_width_in"] == round(29 * 0.002252, 4)


def test_readiness_observes_and_writes_nothing(ready):
    source, output = ready
    before = snapshot(source, output)
    first = readiness_bytes(evaluate(source, output))
    assert readiness_bytes(evaluate(source, output)) == first
    assert snapshot(source, output) == before
    text = first.decode("ascii")
    assert str(source) not in text and str(output) not in text and ":\\\\" not in text


def test_interior_preflight_verdicts_are_the_authoritative_ones(ready):
    source, output = ready
    report = evaluate(source, output)
    project = load_project(source).project
    fresh = preflight_interior(project, read_interior_artifacts(output)).report
    assert report.interior_report_bytes() == interior_report_bytes(fresh)
    cover = preflight_cover(project, source, output)
    assert report.cover_report_bytes() == cover_report_bytes(cover)


def test_missing_interior_leaves_its_checks_unevaluated(tmp_path):
    source, output = publishing_project(tmp_path, cover=False)
    (output / "interior.pdf").unlink()
    (output / "interior.json").unlink()
    report = evaluate(source, output)
    assert "interior_present" in errors(report)
    assert outcome(report, "interior_structural") is Outcome.NOT_EVALUATED
    assert report.verdicts()["interior"]["state"] == "missing"
    assert report.verdicts()["artifacts"] == "missing" and not report.package_ready


def test_missing_cover_blocks(tmp_path):
    source, output = publishing_project(tmp_path, cover=False)
    report = evaluate(source, output)
    assert errors(report) == ["cover_present"]
    assert report.verdicts()["cover"] == {
        "state": "missing",
        "structural": "missing",
        "kdp": "missing",
    }
    assert outcome(report, "cover_text_matches") is Outcome.NOT_EVALUATED


def test_stale_interior_names_the_reason_and_stales_the_cover(ready):
    source, output = ready
    edit(source, "title: Puzzle 1", "title: Puzzle One")
    report = evaluate(source, output)
    assert report.verdicts()["interior"]["state"] == "stale"
    assert report.verdicts()["artifacts"] == "stale"
    stale = messages(report, "interior_structural")
    assert any(m.startswith("Interior is out of date: The project source changed") for m in stale)
    assert report.verdicts()["cover"]["state"] == "stale"
    assert not report.package_ready


def test_stale_cover_after_a_crop_change(ready):
    source, output = ready
    edit(source, "zoom: 1.0", "zoom: 1.2")
    report = evaluate(source, output)
    assert report.verdicts()["interior"]["state"] == "current"
    assert report.verdicts()["cover"]["state"] == "stale"
    assert any("crop changed" in m for m in messages(report, "cover_structural"))
    assert not report.package_ready


def test_paper_change_stales_the_cover_with_a_specific_message(ready):
    source, output = ready
    project = load_project(source).project
    write_interior(build_interior(project, print_profile("paperback-8.5x11-cream")), output, source)
    report = evaluate(source, output)
    assert report.verdicts()["interior"] == {
        "state": "current",
        "structural": "valid",
        "kdp": "ready",
    }
    assert report.verdicts()["cover"]["state"] == "stale"
    assert "Cover is out of date because the interior paper changed (white -> cream)." in messages(
        report, "cover_matches_interior"
    )
    assert report.print_configuration()["paper"] == "cream"
    assert report.print_configuration()["cover"] is None  # No current cover to describe.


def test_page_count_change_stales_the_cover(tmp_path):
    source, output = publishing_project(tmp_path, puzzles=16)
    project = load_project(source).project
    data = project.to_dict()
    data["word_search"]["puzzles"] = data["word_search"]["puzzles"][:14]
    from puzzlepress import validate_project
    from puzzlepress.yaml_io import dump_project

    smaller = validate_project(data).require_project()
    (source / "book.yaml").write_text(dump_project(smaller), encoding="utf-8")
    write_interior(build_interior(smaller, print_profile("paperback-8.5x11")), output, source)
    report = evaluate(source, output)
    assert any(
        "interior page count changed (29 -> 26)" in m
        for m in messages(report, "cover_matches_interior")
    )


def test_cover_text_must_match_book_details(ready):
    source, output = ready
    edit(source, "author: PuzzlePress Examples", "author: Another Name")
    report = evaluate(source, output)
    findings = [f for f in report.findings if f.rule.code == "cover_text_matches"]
    assert [f.field for f in findings] == ["book.author"]
    assert "'PuzzlePress Examples'" in findings[0].message


def test_forged_interior_manifest_is_mismatched(ready):
    source, output = ready
    path = output / "interior.json"
    manifest = json.loads(path.read_text(encoding="utf-8"))
    manifest["page_count"] = 30
    path.write_text(json.dumps(manifest), encoding="utf-8")
    report = evaluate(source, output)
    assert report.verdicts()["interior"]["state"] == "invalid"
    assert report.verdicts()["artifacts"] == "mismatched"
    assert outcome(report, "interior_kdp") is Outcome.NOT_EVALUATED
    assert not report.package_ready


@pytest.mark.parametrize("name", ["interior.pdf", "cover.pdf"])
def test_tampered_pdfs_are_detected(ready, name):
    source, output = ready
    path = output / name
    path.write_bytes(path.read_bytes() + b"\n% tampered\n")
    report = evaluate(source, output)
    kind = name.split(".")[0]
    assert report.verdicts()[kind]["structural"] == "invalid"
    assert report.verdicts()["artifacts"] in ("mismatched", "stale")
    assert not report.package_ready


def test_missing_and_changed_photographs(ready):
    source, output = ready
    photo = next((source / "cover-assets").iterdir())
    original = photo.read_bytes()
    photo.unlink()
    assert "cover_structural" in errors(evaluate(source, output))
    photo.write_bytes(original[:-10] + b"0123456789")
    report = evaluate(source, output)
    assert any("asset_digest_mismatch" in m for m in messages(report, "cover_structural"))


def test_saved_reports_are_compared_never_trusted(ready):
    source, output = ready
    assert len(messages(evaluate(source, output), "saved_reports")) == 2
    project = load_project(source).project
    good = interior_report_bytes(
        preflight_interior(project, read_interior_artifacts(output)).report
    )
    (output / "preflight.json").write_bytes(good)
    (output / "cover-preflight.json").write_bytes(
        cover_report_bytes(preflight_cover(project, source, output))
    )
    assert messages(evaluate(source, output), "saved_reports") == []
    # A saved report from another ruleset (or a forged "ready") is reported, not used.
    forged = json.loads(good)
    forged["ruleset"]["version"] = 99
    forged["kdp"]["status"] = "ready"
    (output / "preflight.json").write_text(json.dumps(forged), encoding="utf-8")
    report = evaluate(source, output)
    assert any("does not match a fresh preflight" in m for m in messages(report, "saved_reports"))
    assert report.package_ready  # A warning: the fresh evaluation is what counts.


def test_a_stale_confirmation_blocks_the_package_and_nothing_else(ready):
    """Reviewed content -> confirmation identity -> readiness, never the artifacts."""
    source, output = ready
    before = evaluate(source, output)
    assert before.package_ready
    edit(source, "- seaside puzzles", "- harbour puzzles")
    report = evaluate(source, output)
    assert errors(report) == ["attestations"] and not report.package_ready
    verdicts = report.verdicts()
    assert verdicts["metadata"] == "valid" and verdicts["attestations"] == "incomplete"
    assert verdicts["interior"]["state"] == verdicts["cover"]["state"] == "current"
    for key in ("source", "interior", "cover"):
        assert report.identities()[key] == before.identities()[key], key
    assert report.identities()["publishing"] != before.identities()["publishing"]
    (message,) = messages(report, "attestations")
    assert message.startswith("Review again: The title, author and other book details")
    stale = {c["name"]: c["state"] for c in report.to_dict()["confirmations"]}
    assert stale["metadata"] == "stale" and stale["rights"] == "confirmed"
    reconfirm(source, "metadata")
    assert evaluate(source, output).package_ready


def test_incomplete_attestation_blocks_only_that_verdict(tmp_path):
    source, output = publishing_project(
        tmp_path, attestations={"rights": True, "ai_disclosure": True, "metadata": False}
    )
    report = evaluate(source, output)
    assert errors(report) == ["attestations"]
    assert report.verdicts()["attestations"] == "incomplete"
    assert report.verdicts()["interior"]["kdp"] == "ready" and not report.package_ready


def test_short_interior_is_valid_but_not_kdp_ready(tmp_path):
    source, output = publishing_project(tmp_path, puzzles=None)
    report = evaluate(source, output)
    assert report.verdicts()["interior"] == {
        "state": "current",
        "structural": "valid",
        "kdp": "not_ready",
    }
    related = {f.related for f in report.findings if f.rule.code == "interior_kdp"}
    assert related == {"kdp_minimum_page_count"}


def test_output_overlapping_source_is_refused(ready):
    source, _ = ready
    report = evaluate_readiness(load_project(source).project, source, source / "nested")
    assert errors(report)[0] == "output_directory"
    assert report.verdicts()["artifacts"] == "unavailable"


def test_composition_demo_remains_a_negative_example(tmp_path):
    from tests.helpers import DEMO

    loaded = load_project(DEMO)
    write_interior(
        build_interior(loaded.project, print_profile("paperback-8.5x11")), tmp_path, DEMO
    )
    report = evaluate_readiness(loaded.project, DEMO, tmp_path)
    assert report.verdicts()["metadata"] == "missing"
    assert report.verdicts()["interior"] == {
        "state": "current",
        "structural": "valid",
        "kdp": "not_ready",
    }
    assert {"publishing_configured", "interior_kdp", "cover_present"} <= set(errors(report))
    assert not report.package_ready


def _restyle_cover(source, output, **cover):
    """Rewrite the cover as version 2 with `cover` changes, reconfirm, and rebuild it."""
    from puzzlepress.cover.build import build_cover, write_cover
    from puzzlepress.validation import validate_project
    from puzzlepress.yaml_io import dump_project

    data = load_project(source).project.to_dict()
    data["cover"] = {**data["cover"], "version": 2, **cover}
    project = validate_project(data).require_project()
    (source / "book.yaml").write_text(dump_project(project), encoding="utf-8")
    reconfirm(source, "rights", "ai_disclosure")
    project = load_project(source).project
    write_cover(build_cover(project, source, output), output, source)


def test_hidden_cover_title_keeps_the_book_title_and_warns(ready):
    source, output = ready
    title = load_project(source).project.book.title
    _restyle_cover(source, output, text={"title": {"visible": False}})
    project = load_project(source).project
    assert project.book.title == title
    report = evaluate(source, output)
    omitted = [f for f in report.findings if f.rule.code == "cover_text_omitted"]
    assert len(omitted) == 1 and omitted[0].severity.value == "warning"
    assert repr(title) in omitted[0].message
    assert not [f for f in report.findings if f.rule.code == "cover_text_matches"]
    assert report.package_ready


def test_cover_display_text_must_match_the_book_details(ready):
    source, output = ready
    _restyle_cover(source, output, text={"title": {"text": "A Different Title"}})
    report = evaluate(source, output)
    findings = [f for f in report.findings if f.rule.code == "cover_text_matches"]
    assert [f.field for f in findings] == ["cover.text.title.text"]
    assert not report.package_ready


def test_cover_display_text_may_differ_in_line_breaks_and_case(ready):
    source, output = ready
    title = load_project(source).project.book.title
    words = title.upper().split(" ")
    _restyle_cover(
        source, output, text={"title": {"text": " ".join(words[:1]) + "\n" + " ".join(words[1:])}}
    )
    report = evaluate(source, output)
    assert not [f for f in report.findings if f.rule.code.startswith("cover_text")]
    assert report.package_ready


def _apply_template(source, output, template_id, back_text=None):
    """Apply a built-in template as Studio does, save, reconfirm and rebuild the cover."""
    from dataclasses import replace

    from puzzlepress.cover.build import build_cover, write_cover
    from puzzlepress.cover.geometry import cover_geometry
    from puzzlepress.cover_template import apply_template
    from puzzlepress.cover_template_store import find_template
    from puzzlepress.interior.spec import Paper, inches
    from puzzlepress.validation import validate_project
    from puzzlepress.yaml_io import dump_project

    trim = (inches(8.5), inches(11))
    project = load_project(source).project
    spine = cover_geometry(29, *trim, Paper.WHITE).spine_width
    cover = apply_template(find_template(None, template_id), project, spine, trim).cover
    data = replace(project, cover=cover).to_dict()
    if back_text is not None:
        data["cover"]["back_text"] = back_text
    project = validate_project(data).require_project()
    (source / "book.yaml").write_text(dump_project(project), encoding="utf-8")
    reconfirm(source, "rights", "ai_disclosure")
    project = load_project(source).project
    write_cover(build_cover(project, source, output), output, source)


@pytest.mark.parametrize(
    "template_id",
    [
        "photographic-editorial",
        "bold-garage",
        "motorsport-energy",
        "vintage-motoring",
        "modern-minimal",
        "technical-blueprint",
        "classic-puzzle-collection",
        "premium-editorial",
    ],
)
def test_a_template_cover_prints_the_book_details_without_false_mismatches(ready, template_id):
    source, output = ready
    before = load_project(source).project.book
    _apply_template(source, output, template_id)
    project = load_project(source).project
    assert project.book == before and project.cover.version == 3
    report = evaluate(source, output)
    assert not [f for f in report.findings if f.rule.code.startswith("cover_text")]
    assert report.package_ready


def test_formatted_back_text_reads_as_its_plain_words(ready):
    source, output = ready
    rich = {
        "rich": 1,
        "blocks": [
            {"type": "heading", "runs": [{"text": "Sixteen puzzles"}]},
            {"runs": [{"text": "Grids from the "}, {"text": "harbour", "italic": True}]},
        ],
    }
    _apply_template(source, output, "photographic-editorial", back_text=rich)
    project = load_project(source).project
    assert project.cover.back_text == "Sixteen puzzles\nGrids from the harbour"
    report = evaluate(source, output)
    assert not [f for f in report.findings if f.rule.code.startswith("cover_text")]
    assert report.package_ready
