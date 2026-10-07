"""Real PDFs: structure, fonts, determinism, post-build inspection and safe output."""

import hashlib
import io
import json
import os
from dataclasses import replace

import pytest
from pypdf import PdfReader, PdfWriter
from pypdf.annotations import FreeText
from reportlab.pdfgen.canvas import Canvas

from puzzlepress import load_project
from puzzlepress.interior import InteriorError, build_interior, write_interior
from puzzlepress.interior.inspection import inspect_pdf
from puzzlepress.interior.render import render_pdf
from puzzlepress.interior.spec import PAPERBACK_LETTER
from tests.helpers import DEMO, demo_variant

SPEC = PAPERBACK_LETTER


@pytest.fixture(scope="module")
def demo_build():
    return build_interior(load_project(DEMO).project, SPEC)


def reader(data):
    return PdfReader(io.BytesIO(data), strict=True)


def test_pdf_pages_boxes_order_and_blank_page(demo_build):
    pdf = reader(demo_build.pdf)
    assert len(pdf.pages) == 11 == demo_build.manifest["page_count"]
    for page in pdf.pages:
        assert [float(v) for v in page.mediabox] == [0, 0, 612, 792]
        assert [float(v) for v in page.trimbox] == [0, 0, 612, 792]
        assert "/Annots" not in page and page.get("/Rotate", 0) == 0
    text = [page.extract_text() for page in pdf.pages]
    assert "Seaside Word Searches" in text[0] and "How to Play" in text[2]
    assert text[3] == ""
    titles = ["Along the Shoreline", "In the Rock Pool", "By the Harbour", "Over the Dunes"]
    for offset, title in enumerate(titles):
        assert title in text[4 + offset] and str(offset + 1) in text[4 + offset].split()
    assert "Solutions" in text[8] and "Notes" in text[10]
    assert text[8].index("Along the Shoreline") < text[8].index("In the Rock Pool")


def test_pdf_has_embedded_fonts_and_no_outline_forms_or_marks(demo_build):
    pdf = reader(demo_build.pdf)
    assert not pdf.outline and "/AcroForm" not in pdf.root_object
    fonts = pdf.pages[4]["/Resources"]["/Font"].get_object()
    assert fonts
    for font in fonts.values():
        font = font.get_object()
        assert font["/Subtype"] == "/TrueType"
        assert str(font["/BaseFont"]).split("+")[1].startswith("BitstreamVeraSans")
        assert "/FontFile2" in font["/FontDescriptor"]
    metadata = pdf.metadata
    assert metadata["/CreationDate"] == "D:20000101000000+00'00'"
    assert (metadata["/Title"], metadata["/Author"]) == ("", "")
    assert inspect_pdf(demo_build.pdf, demo_build.layout) == ()


def test_identical_inputs_produce_identical_bytes(demo_build):
    again = build_interior(load_project(DEMO).project, SPEC)
    assert again.pdf == demo_build.pdf and again.manifest == demo_build.manifest
    assert render_pdf(demo_build.layout) == demo_build.pdf
    manifest = demo_build.manifest
    assert manifest["pdf"]["sha256"] == hashlib.sha256(demo_build.pdf).hexdigest()
    assert manifest["interior_identity"].startswith("pp1-interior-sha256-")
    assert manifest["identity"] == demo_build.plan.identity
    assert manifest["plan_digest"] == demo_build.layout.plan_digest
    assert manifest["trim"] == {"name": "8.5x11", "width_in": 8.5, "height_in": 11, "bleed": False}
    assert [f["face"] for f in manifest["fonts"]] == ["regular", "bold", "italic"]
    assert "time" not in json.dumps(manifest).lower()


def test_semantic_change_changes_bytes_and_identity(demo_build):
    def retitle(data):
        data["book"]["title"] = "Harbour Word Searches"

    other = build_interior(demo_variant(retitle), SPEC)
    assert other.pdf != demo_build.pdf
    assert other.manifest["interior_identity"] != demo_build.manifest["interior_identity"]


@pytest.mark.parametrize("per_page", [1, 2, 4, 6])
def test_each_solution_density_builds_a_verified_pdf(per_page):
    def mutate(data):
        data["composition"]["solutions"]["per_page"] = per_page

    build = build_interior(demo_variant(mutate, puzzles=12), SPEC)
    assert len(reader(build.pdf).pages) == len(build.plan.pages)


def test_inspection_rejects_broken_pdfs(demo_build):
    layout = demo_build.layout
    assert [i.code for i in inspect_pdf(b"", layout)] == ["pdf_empty"]
    assert [i.code for i in inspect_pdf(b"%PDF-1.4 broken", layout)] == ["pdf_unreadable"]
    short = replace(layout, pages=layout.pages[:-1])
    assert [i.code for i in inspect_pdf(demo_build.pdf, short)] == ["pdf_page_count"]

    writer = PdfWriter(clone_from=io.BytesIO(demo_build.pdf))
    writer.add_annotation(5, FreeText(text="note", rect=(50, 50, 200, 100)))
    annotated = io.BytesIO()
    writer.write(annotated)
    codes = [(i.code, i.physical_page) for i in inspect_pdf(annotated.getvalue(), layout)]
    assert ("pdf_annotations", 6) in codes

    buffer = io.BytesIO()
    canvas = Canvas(buffer, pagesize=(612, 792))
    canvas.drawString(100, 100, "1")  # Standard Helvetica is never embedded.
    canvas.setTrimBox((0, 0, 612, 792))
    canvas.showPage()
    canvas.save()
    one = replace(layout, pages=layout.pages[4:5])
    assert "font_not_embedded" in [i.code for i in inspect_pdf(buffer.getvalue(), one)]

    blank = replace(layout, pages=(layout.pages[3],))
    codes = [i.code for i in inspect_pdf(buffer.getvalue(), blank)]
    assert "pdf_blank_page" in codes


def test_failed_build_raises_before_rendering():
    def overflow(data):
        data["composition"]["front_matter"][2]["text"] = "x\n" * 999 + "x"

    with pytest.raises(InteriorError) as caught:
        build_interior(demo_variant(overflow), SPEC)
    assert caught.value.stage == "layout"


def test_write_creates_replaces_and_verifies_outputs(demo_build, tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    output = tmp_path / "build" / "demo"
    written = write_interior(demo_build, output, source)
    assert written.pdf.read_bytes() == demo_build.pdf
    assert json.loads(written.manifest.read_text("utf-8")) == demo_build.manifest
    assert sorted(p.name for p in output.iterdir()) == ["interior.json", "interior.pdf"]
    again = write_interior(demo_build, output, source)  # Owned output is replaced.
    assert again.pdf.read_bytes() == demo_build.pdf
    assert sorted(p.name for p in output.iterdir()) == ["interior.json", "interior.pdf"]


def output_error(build, output, source):
    with pytest.raises(InteriorError) as caught:
        write_interior(build, output, source)
    assert caught.value.stage == "output"
    return caught.value.issues[0].code


def test_output_must_stay_disjoint_from_source(demo_build, tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    assert output_error(demo_build, source / "build", source) == "source_overlap"
    assert output_error(demo_build, source, source) == "source_overlap"
    assert output_error(demo_build, tmp_path, source) == "source_overlap"
    blocker = tmp_path / "file"
    blocker.write_text("x")
    assert output_error(demo_build, blocker, source) == "not_directory"
    assert not (source / "build").exists()


def test_unowned_or_foreign_outputs_are_never_replaced(demo_build, tmp_path):
    source = tmp_path / "source"
    source.mkdir()
    output = tmp_path / "out"
    output.mkdir()
    (output / "interior.pdf").write_bytes(b"user file")
    assert output_error(demo_build, output, source) == "output_collision"
    assert (output / "interior.pdf").read_bytes() == b"user file"
    (output / "interior.json").write_text(json.dumps({"book_id": "another-book"}))
    assert output_error(demo_build, output, source) == "output_collision"
    (output / "interior.json").write_text("{not json")
    assert output_error(demo_build, output, source) == "output_collision"
    assert (output / "interior.pdf").read_bytes() == b"user file"


def test_interrupted_write_leaves_previous_interior_and_no_temporaries(
    demo_build, tmp_path, monkeypatch
):
    source = tmp_path / "source"
    source.mkdir()
    output = tmp_path / "out"
    write_interior(demo_build, output, source)
    previous = (output / "interior.pdf").read_bytes()

    def fail(*args):
        raise OSError("disk full")

    monkeypatch.setattr(os, "replace", fail)
    changed = replace(demo_build, pdf=b"%PDF-new", manifest={**demo_build.manifest, "x": 1})
    assert output_error(changed, output, source) == "write_failed"
    assert (output / "interior.pdf").read_bytes() == previous
    assert sorted(p.name for p in output.iterdir()) == ["interior.json", "interior.pdf"]
