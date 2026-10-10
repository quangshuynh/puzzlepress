"""Cover preflight: verdicts, staleness, observation-only, tampering and the CLI."""

import hashlib
import json
import subprocess
import sys

import pytest

from puzzlepress import load_project, validate_project
from puzzlepress.cover import build as cover_build
from puzzlepress.cover.assets import import_photo
from puzzlepress.cover.build import build_cover, write_cover
from puzzlepress.cover.preflight import preflight_cover, report_bytes
from puzzlepress.interior import build_interior, print_profile, write_interior
from puzzlepress.yaml_io import dump_project
from tests.cover_helpers import cover_project, photo_bytes
from tests.helpers import demo_variant


def built(root, **options):
    source, output = cover_project(root, **options)
    project = load_project(source).project
    write_cover(build_cover(project, source, output), output, source)
    return source, output


def run(source, output):
    return preflight_cover(load_project(source).project, source, output)


def failed(report):
    return {r.rule.code for r in report.results if r.outcome.value == "failed"}


def rebuild_interior(source, output, profile="paperback-8.5x11"):
    project = load_project(source).project
    write_interior(build_interior(project, print_profile(profile)), output, source)


def edit(source, old, new):
    path = source / "book.yaml"
    text = path.read_text(encoding="utf-8")
    assert old in text
    path.write_text(text.replace(old, new), encoding="utf-8")


def snapshot(*directories):
    return {
        p.relative_to(d).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for d in directories
        for p in sorted(d.rglob("*"))
        if p.is_file()
    }


def test_short_book_is_structurally_valid_but_not_kdp_ready(tmp_path):
    source, output = built(tmp_path)
    report = run(source, output)
    assert (report.state, report.structurally_valid, report.kdp_ready) == ("current", True, False)
    errors = [f.rule.code for f in report.findings if f.severity.value == "error"]
    warnings = [f.rule.code for f in report.findings if f.severity.value == "warning"]
    assert errors == ["kdp_cover_page_count"]
    assert warnings == ["kdp_cover_color_space"]
    data = report.to_dict()
    assert data["ruleset"] == {
        "id": "puzzlepress-kdp-cover",
        "version": 2,
        "kdp_rules_checked": "2026-10-07",
    }
    assert data["spine_text"]["reason"] == "page_count"
    assert data["artifacts"]["matches_render"] is True


def test_29_page_book_with_a_large_photo_is_ready(tmp_path):
    source, output = built(tmp_path, puzzles=16)
    report = run(source, output)
    assert report.kdp_ready and report.state == "current"
    assert report.to_dict()["interior"]["page_count"] == 29


def test_preflight_observes_and_is_deterministic(tmp_path):
    source, output = built(tmp_path)
    before = snapshot(source, output)
    first, second = report_bytes(run(source, output)), report_bytes(run(source, output))
    assert first == second and snapshot(source, output) == before
    text = first.decode("ascii")
    assert str(tmp_path) not in text and str(tmp_path).replace("\\", "/") not in text


def test_missing_cover_and_missing_configuration(tmp_path):
    source, output = cover_project(tmp_path / "a")
    report = run(source, output)
    assert report.state == "missing" and not report.structurally_valid
    assert "cover_artifacts" in failed(report)
    source, output = cover_project(tmp_path / "b", mutate=lambda d: d.pop("cover"))
    report = run(source, output)
    assert report.state == "no_config" and "cover_configured" in failed(report)


@pytest.mark.parametrize(
    ("change", "reason"),
    [
        ("crop", "crop changed"),
        ("design", "cover design changed"),
        ("subtitle", "cover text changed"),
    ],
)
def test_authored_changes_make_the_cover_stale(tmp_path, change, reason):
    source, output = built(tmp_path)
    if change == "crop":
        edit(source, "x: 0.5", "x: 0.25")
    elif change == "design":
        edit(source, "style: editorial", "style: bold")
    else:  # The subtitle is book metadata; the interior is rebuilt for it.
        edit(source, "A small composition demonstration", "A seaside collection")
        rebuild_interior(source, output)
    report = run(source, output)
    assert report.state == "stale" and "cover_current" in failed(report)
    message = next(f.message for f in report.findings if f.rule.code == "cover_current")
    assert reason in message


def test_interior_page_count_and_paper_changes_make_the_cover_stale(tmp_path):
    source, output = built(tmp_path / "pages")
    data = load_project(source).project

    longer = demo_variant(puzzles=6).to_dict()
    longer["output"], longer["cover"], longer["book"] = (
        data.to_dict()["output"],
        data.to_dict()["cover"],
        data.to_dict()["book"],
    )

    (source / "book.yaml").write_text(
        dump_project(validate_project(longer).require_project()), encoding="utf-8"
    )
    rebuild_interior(source, output)
    report = run(source, output)
    message = next(f.message for f in report.findings if f.rule.code == "cover_current")
    assert report.state == "stale" and "interior page count changed (11 -> 14)" in message

    source, output = built(tmp_path / "paper")
    rebuild_interior(source, output, "paperback-8.5x11-cream")
    report = run(source, output)
    message = next(f.message for f in report.findings if f.rule.code == "cover_current")
    assert "paper changed (white -> cream)" in message and "print profile changed" in message


def test_a_stale_interior_blocks_the_cover(tmp_path):
    source, output = built(tmp_path)
    edit(source, "Along the Shoreline", "Shoreline")
    report = run(source, output)
    assert report.state == "stale" and "interior_current" in failed(report)
    assert not report.structurally_valid


def test_a_rebuilt_interior_with_the_same_facts_only_warns(tmp_path):
    source, output = built(tmp_path)
    edit(source, "Along the Shoreline", "Shoreline")
    rebuild_interior(source, output)
    report = run(source, output)
    assert report.state == "current" and report.structurally_valid
    warnings = {f.rule.code for f in report.findings if f.severity.value == "warning"}
    assert "cover_interior_provenance" in warnings


def test_photo_changes(tmp_path):
    source, output = built(tmp_path / "replaced")
    project = load_project(source).project
    (source / project.cover.image.path).write_bytes(photo_bytes(5400, 3600, orientation=3))
    report = run(source, output)
    assert "cover_photo" in failed(report) and not report.structurally_valid
    assert any("asset_digest_mismatch" in f.message for f in report.findings)

    source, output = built(tmp_path / "reselected")
    project = load_project(source).project
    new = import_photo(source, photo_bytes(5400, 3600, orientation=3), "new.jpg")
    edit(source, project.cover.image.sha256, new.info.sha256)
    edit(source, project.cover.image.path, new.path)
    report = run(source, output)
    message = next(f.message for f in report.findings if f.rule.code == "cover_current")
    assert report.state == "stale" and "photograph changed" in message


def test_renderer_version_change_makes_the_cover_stale(tmp_path, monkeypatch):
    source, output = built(tmp_path)
    monkeypatch.setattr(cover_build, "COVER_RENDERER_VERSION", 99)
    report = run(source, output)
    message = next(f.message for f in report.findings if f.rule.code == "cover_current")
    assert "renderer, libraries or fonts changed" in message


def test_tampered_artifacts_are_invalid(tmp_path):
    source, output = built(tmp_path)
    (output / "cover.pdf").write_bytes((output / "cover.pdf").read_bytes() + b"%tamper\n")
    report = run(source, output)
    assert report.state == "invalid"
    assert {"cover_manifest", "cover_matches_render"} <= failed(report)
    outcomes = {r.rule.code: r.outcome.value for r in report.results}
    assert outcomes["kdp_cover_image_resolution"] == "not_evaluated" and not report.kdp_ready
    manifest = json.loads((output / "cover.json").read_text())
    manifest["cover_identity"] = "pp1-cover-sha256-" + "0" * 64
    (output / "cover.json").write_text(json.dumps(manifest))
    assert "cover_manifest" in failed(run(source, output))


def test_low_effective_dpi_is_a_readiness_finding_not_a_build_failure(tmp_path):
    source, output = built(tmp_path, puzzles=16, cover={"crop": {"zoom": 1.5}})
    report = run(source, output)
    assert report.structurally_valid and not report.kdp_ready
    finding = next(f for f in report.findings if f.rule.code == "kdp_cover_image_resolution")
    assert "image_low_effective_dpi" in finding.message
    assert finding.measure.required == 300 and finding.measure.actual < 300


def cli(*args):
    return subprocess.run(
        [sys.executable, "-m", "puzzlepress", "cover", *map(str, args)],
        capture_output=True,
        text=True,
        check=False,
    )


def test_cli_build_preflight_and_inspect(tmp_path):
    source, output = cover_project(tmp_path)
    inspect = cli("inspect", source, "--json")
    assert inspect.returncode == 0, inspect.stderr
    facts = json.loads(inspect.stdout)
    assert facts["geometry"]["spine_width_in"] == pytest.approx(0.024772)
    assert facts["spine_text"]["reason"] == "page_count" and not (output / "cover.pdf").exists()
    built_result = cli("build", source)
    assert built_result.returncode == 0, built_result.stderr
    assert "Full wrap 17.2748 x 11.2500 in" in built_result.stdout
    preflight = cli("preflight", source, "--json")
    assert preflight.returncode == 1  # Structurally valid, not KDP ready (11 pages).
    written = (output / "cover-preflight.json").read_text(encoding="ascii")
    assert preflight.stdout.replace("\r\n", "\n") == written
    report = json.loads(written)
    assert report["structural"]["status"] == "valid" and report["kdp"]["status"] == "not_ready"
    before = snapshot(output)
    again = cli("preflight", source, "--no-write")
    assert again.returncode == 1 and "KDP readiness: NOT READY" in again.stdout
    assert snapshot(output) == before


def test_cli_failures_write_nothing(tmp_path):
    source, output = cover_project(tmp_path, build_interior=False)
    result = cli("build", source, "--json")
    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert payload["stage"] == "interior"
    assert payload["diagnostics"][0]["code"] == "interior_missing"
    assert not output.exists() or not (output / "cover.pdf").exists()


def test_cli_import_copies_the_photo_and_prints_its_reference(tmp_path):
    source, _ = cover_project(tmp_path, build_interior=False)
    photo = tmp_path / "Dawn Harbour.JPG"
    photo.write_bytes(photo_bytes(800, 600, private=True))
    result = cli("import", source, photo, "--json")
    assert result.returncode == 0, result.stderr
    data = json.loads(result.stdout)
    assert data["path"].startswith("cover-assets/dawn-harbour-") and not data["reused"]
    assert (source / data["path"]).read_bytes() == photo.read_bytes()
    text = cli("import", source, photo)
    assert "Already present" in text.stdout and data["sha256"] in text.stdout
    bad = tmp_path / "notes.jpg"
    bad.write_text("not a photo")
    assert cli("import", source, bad).returncode == 1


def test_cover_demo_fixture_is_valid_and_its_photo_matches_its_pin():
    from tests.helpers import ROOT

    project = load_project(ROOT / "books" / "cover-demo").project
    assert project.cover is not None and project.cover.layout.value == "full_wrap"
    photo = ROOT / "books" / "cover-demo" / project.cover.image.path
    assert hashlib.sha256(photo.read_bytes()).hexdigest() == project.cover.image.sha256
