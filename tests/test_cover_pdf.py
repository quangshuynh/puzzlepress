"""Real cover PDFs: structure, privacy, determinism, identity, interior facts, writes."""

import hashlib
import io
import json
import os
import subprocess
import sys
from dataclasses import replace

import pytest
from pypdf import PdfReader, PdfWriter
from pypdf.annotations import FreeText

from puzzlepress import load_project
from puzzlepress.cover import build as cover_build
from puzzlepress.cover.assets import decode_photo
from puzzlepress.cover.build import (
    InteriorFacts,
    build_cover,
    read_interior_facts,
    render_cover,
    write_cover,
)
from puzzlepress.cover.inspection import inspect_cover_pdf, jpeg_segments, read_cover_facts
from puzzlepress.cover.issues import CoverError
from puzzlepress.cover.render import render_cover_pdf
from puzzlepress.cover_config import CoverLayoutKind, Crop, Legibility
from puzzlepress.interior.spec import Paper, inches
from tests.cover_helpers import LEAKS, cover_project, photo_bytes
from tests.helpers import ROOT


@pytest.fixture(scope="module")
def demo(tmp_path_factory):
    source, output = cover_project(
        tmp_path_factory.mktemp("cover"), data=photo_bytes(5400, 3600, private=True)
    )
    project = load_project(source).project
    return source, output, project, build_cover(project, source, output)


def facts(pages=300, paper=Paper.CREAM):
    profile = "paperback-8.5x11-cream" if paper is Paper.CREAM else "paperback-8.5x11"
    return InteriorFacts(
        "composition-demo",
        "pp1-interior-sha256-" + "1" * 64,
        "pp1-sha256-" + "2" * 64,
        "3" * 64,
        pages,
        {"profile_id": profile, "profile_version": 1, "ink": "black"},
        inches(8.5),
        inches(11),
        paper,
    )


def test_cover_pdf_structure(demo):
    _, _, _, build = demo
    reader = PdfReader(io.BytesIO(build.pdf), strict=True)
    assert len(reader.pages) == 1
    page = reader.pages[0]
    g = build.layout.geometry
    width = 2 * 9 + 2 * 612 + 11 * 0.002252 * 72  # composition-demo: 11 white pages.
    assert [float(v) for v in page.mediabox] == pytest.approx([0, 0, width, 810], abs=0.01)
    assert [float(v) for v in page.trimbox] == pytest.approx([9, 9, width - 9, 801], abs=0.01)
    assert [float(v) for v in page.bleedbox] == pytest.approx([0, 0, width, 810], abs=0.01)
    assert g.media.width == pytest.approx(width)
    assert "/Annots" not in page and page.get("/Rotate", 0) == 0
    assert not reader.outline and "/AcroForm" not in reader.root_object
    observed = read_cover_facts(build.pdf)
    assert not isinstance(observed, type(None)) and not hasattr(observed, "code")
    assert len(observed.images) == 1 and observed.images[0].filters == ("/DCTDecode",)
    assert observed.images[0].segments[0] == "APP0" and "APP1" not in observed.images[0].segments
    assert not observed.operators & {"S", "s", "B", "b"}
    for font in observed.base.pages[0].fonts:
        assert font.embedded and font.subset
    text = page.extract_text()
    assert "Seaside Word" in text and "Quiet seaside puzzles." in text
    assert reader.metadata["/Title"] == "" and reader.metadata["/Author"] == ""


def test_thin_book_prints_no_spine_text_and_explains_why(demo):
    layout = demo[3].layout
    assert layout.spine.reason == "page_count" and not any(t.rotated for t in layout.texts)
    assert demo[3].manifest["spine_text"]["reason"] == "page_count"


def test_private_photo_metadata_never_reaches_the_pdf(demo):
    source, _, project, build = demo
    original = (source / project.cover.image.path).read_bytes()
    assert all(marker in original for marker in (b"LEAKCAM", b"LEAKCOMMENT"))
    assert not any(marker in build.pdf for marker in LEAKS)
    assert b"Exif" not in build.pdf and b"xmpmeta" not in build.pdf


def test_manifest_records_facts_without_paths_or_time(demo):
    source, _, _, build = demo
    m = build.manifest
    assert m["cover_identity"].startswith("pp1-cover-sha256-")
    assert m["pdf"]["sha256"] == hashlib.sha256(build.pdf).hexdigest()
    assert m["interior"]["page_count"] == 11 and m["interior"]["paper"] == "white"
    assert m["geometry"]["spine_width_in"] == pytest.approx(0.024772)
    assert m["photo"]["sha256"] == m["cover"]["image"]["sha256"]
    assert "path" not in m["cover"]["image"]
    assert m["provenance"]["photo_path"].startswith("cover-assets/")
    assert m["embedded_photo"]["pixels"] == list(build.image_size)
    text = json.dumps(m)
    assert str(source) not in text and str(source).replace("\\", "/") not in text
    assert "time" not in text.lower() and "date" not in text.lower()


def test_rebuild_is_byte_identical(demo):
    source, output, project, build = demo
    again = build_cover(project, source, output)
    assert again.pdf == build.pdf and again.manifest == build.manifest


def test_rebuild_matches_in_another_process_cwd_and_hash_seed(demo, tmp_path):
    source, output, _, build = demo
    script = (
        "import hashlib, sys; from pathlib import Path\n"
        "from puzzlepress import load_project\n"
        "from puzzlepress.cover.build import build_cover\n"
        "s = Path(sys.argv[1]); p = load_project(s).project\n"
        "print(hashlib.sha256(build_cover(p, s, Path(sys.argv[2])).pdf).hexdigest())\n"
    )
    env = {**os.environ, "PYTHONHASHSEED": "12345", "PYTHONPATH": str(ROOT / "src")}
    result = subprocess.run(
        [sys.executable, "-c", script, str(source), str(output)],
        cwd=tmp_path,
        env=env,
        capture_output=True,
        text=True,
        check=True,
    )
    assert result.stdout.strip() == hashlib.sha256(build.pdf).hexdigest()


def test_identity_tracks_every_output_affecting_input(demo, monkeypatch):
    _, _, project, build = demo
    photo = decode_photo(photo_bytes(5400, 3600, private=True))
    base = render_cover(project, facts(), photo)
    identity = base.manifest["cover_identity"]
    moved = replace(project, cover=replace(project.cover, crop=Crop(0.3, 0.5, 1.0)))
    assert render_cover(moved, facts(), photo).manifest["cover_identity"] != identity
    assert render_cover(project, facts(pages=302), photo).manifest["cover_identity"] != identity
    white = render_cover(project, facts(paper=Paper.WHITE), photo)
    assert white.manifest["cover_identity"] != identity
    other = decode_photo(photo_bytes(5400, 3600))
    swapped = replace(
        project,
        cover=replace(project.cover, image=replace(project.cover.image, sha256=other.info.sha256)),
    )
    assert render_cover(swapped, facts(), other).manifest["cover_identity"] != identity
    rebuilt = replace(facts(), interior_identity="pp1-interior-sha256-" + "9" * 64)
    # A rebuilt interior with the same physical facts keeps the cover identity.
    assert render_cover(project, rebuilt, photo).manifest["cover_identity"] == identity
    monkeypatch.setattr(cover_build, "COVER_RENDERER_VERSION", 2)
    assert render_cover(project, facts(), photo).manifest["cover_identity"] != identity


def test_wide_spine_renders_rotated_spine_text(demo):
    _, _, project, _ = demo
    photo = decode_photo(photo_bytes(5400, 3600, private=True))
    build = render_cover(project, facts(), photo)
    assert build.layout.spine.rendered and build.layout.spine.size == 14
    reader = PdfReader(io.BytesIO(build.pdf), strict=True)
    assert [float(v) for v in reader.pages[0].mediabox] == pytest.approx([0, 0, 1296, 810])


def test_exif_rotated_photo_prints_upright(demo):
    pypdfium2 = pytest.importorskip("pypdfium2")
    _, _, project, _ = demo
    data = photo_bytes(3600, 5400, orientation=6)  # Stored sideways, displayed portrait.
    photo = decode_photo(data)
    cover = replace(
        project.cover,
        image=replace(project.cover.image, sha256=photo.info.sha256),
        layout=CoverLayoutKind.FRONT_PHOTO,
        legibility=Legibility.NONE,
    )
    build = render_cover(replace(project, cover=cover), facts(), photo)
    image = pypdfium2.PdfDocument(build.pdf)[0].render(scale=0.25).to_pil().convert("RGB")
    front = build.layout.geometry.front
    scale = image.size[1] / build.layout.geometry.media.height

    def sample(fx, fy):  # Fractions across the front panel, y from the top.
        x = (front.x + fx * front.width) * scale
        y = image.size[1] - (front.y + (1 - fy) * front.height) * scale
        return image.getpixel((round(x), round(y)))

    red, green = sample(0.2, 0.3), sample(0.8, 0.3)
    blue, white = sample(0.2, 0.8), sample(0.8, 0.8)
    assert red[0] > 180 and red[1] < 80 and green[1] > 160 and green[0] < 80
    assert blue[2] > 180 and blue[0] < 80 and min(white) > 220


def test_cover_requires_a_current_verified_interior(tmp_path):
    source, output = cover_project(tmp_path / "missing", build_interior=False)
    project = load_project(source).project
    with pytest.raises(CoverError) as error:
        build_cover(project, source, output)
    assert (error.value.stage, error.value.issues[0].code) == ("interior", "interior_missing")

    source, output = cover_project(tmp_path / "stale")
    text = (source / "book.yaml").read_text(encoding="utf-8")
    (source / "book.yaml").write_text(text.replace("Along the Shoreline", "Shoreline"), "utf-8")
    with pytest.raises(CoverError) as error:
        build_cover(load_project(source).project, source, output)
    assert error.value.issues[0].code == "interior_stale"

    source, output = cover_project(tmp_path / "tampered")
    (output / "interior.pdf").write_bytes((output / "interior.pdf").read_bytes() + b"\n")
    with pytest.raises(CoverError) as error:
        read_interior_facts(output, load_project(source).project)
    assert error.value.issues[0].code == "interior_mismatch"


def test_interior_facts_come_from_the_pdf_and_profile(tmp_path):
    source, output = cover_project(tmp_path, profile="paperback-8.5x11-cream")
    interior = read_interior_facts(output, load_project(source).project)
    assert (interior.page_count, interior.paper) == (11, Paper.CREAM)
    assert interior.physical()["profile_id"] == "paperback-8.5x11-cream"
    assert interior.pdf_sha256 == hashlib.sha256((output / "interior.pdf").read_bytes()).hexdigest()


def test_photo_problems_fail_before_rendering(tmp_path):
    source, output = cover_project(tmp_path)
    project = load_project(source).project
    path = source / project.cover.image.path
    path.write_bytes(photo_bytes(10, 10))
    with pytest.raises(CoverError) as error:
        build_cover(project, source, output)
    assert (error.value.stage, error.value.issues[0].code) == ("asset", "asset_digest_mismatch")
    path.unlink()
    with pytest.raises(CoverError) as error:
        build_cover(project, source, output)
    assert error.value.issues[0].code == "image_missing"


def test_write_cover_places_files_beside_this_books_interior(tmp_path):
    source, output = cover_project(tmp_path)
    project = load_project(source).project
    build = build_cover(project, source, output)
    written = write_cover(build, output, source)
    assert written.pdf.read_bytes() == build.pdf
    assert (
        json.loads(written.manifest.read_text())["cover_identity"]
        == build.manifest["cover_identity"]
    )
    assert write_cover(build, output, source).pdf == written.pdf  # Replaces its own cover.
    assert not [p for p in output.iterdir() if p.name.startswith(".cover-")]
    with pytest.raises(CoverError) as error:
        write_cover(build, source, source)
    assert error.value.issues[0].code == "source_overlap"


def test_write_cover_refuses_foreign_or_unowned_files(tmp_path):
    source, output = cover_project(tmp_path)
    build = build_cover(load_project(source).project, source, output)
    (output / "cover.json").write_text(json.dumps({"book_id": "another-book"}))
    with pytest.raises(CoverError) as error:
        write_cover(build, output, source)
    assert error.value.issues[0].code == "output_collision"
    (output / "cover.json").unlink()
    (output / "cover.pdf").write_bytes(b"someone else's cover")
    with pytest.raises(CoverError):
        write_cover(build, output, source)
    assert (output / "cover.pdf").read_bytes() == b"someone else's cover"
    (output / "cover.pdf").unlink()
    (output / "interior.json").unlink()
    with pytest.raises(CoverError) as error:
        write_cover(build, output, source)
    assert error.value.issues[0].code == "output_missing"
    assert not (output / "cover.pdf").exists()


def test_inspection_catches_tampered_pdfs(demo):
    _, _, _, build = demo
    layout, size = build.layout, build.image_size

    def codes(data):
        return {issue.code for issue in inspect_cover_pdf(data, layout, build.image_sizes)}

    assert codes(build.pdf) == set()
    writer = PdfWriter(clone_from=io.BytesIO(build.pdf))
    writer.add_annotation(0, FreeText(text="note", rect=(10, 10, 50, 50)))
    writer.pages[0].rotate(90)
    writer.add_outline_item("x", 0)
    buffer = io.BytesIO()
    writer.write(buffer)
    assert {"pdf_annotations", "pdf_rotation", "pdf_outline"} <= codes(buffer.getvalue())
    assert codes(b"not a pdf") == {"pdf_unreadable"}
    leaky = photo_bytes(*size, private=True)
    assert "APP1" in jpeg_segments(leaky)
    assert "pdf_metadata_leak" in codes(render_cover_pdf(layout, [(leaky, size)]))
    assert "pdf_image" in codes(render_cover_pdf(layout, [(photo_bytes(64, 64), (64, 64))]))


def test_canonical_fixture_unchanged_by_cover_tests():
    data = (ROOT / "books" / "composition-demo" / "book.yaml").read_bytes()
    assert b"cover:" not in data


def test_draft_reads_report_a_stale_interior_without_trusting_a_damaged_one(tmp_path):
    source, output = cover_project(tmp_path)
    text = (source / "book.yaml").read_text(encoding="utf-8")
    (source / "book.yaml").write_text(text.replace("Along the Shoreline", "Shoreline"), "utf-8")
    project = load_project(source).project
    relaxed = read_interior_facts(output, project, require_current=False)
    assert relaxed.page_count == 11 and "predates the current source" in (relaxed.stale or "")
    (output / "interior.pdf").write_bytes(b"%PDF-1.4 damaged")
    with pytest.raises(CoverError) as error:
        read_interior_facts(output, project, require_current=False)
    assert error.value.issues[0].code == "interior_mismatch"
