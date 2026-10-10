"""Inspection shortcuts are exact: they skip repeated pypdf work, never a judgment."""

import io
from dataclasses import replace

import pytest
from PIL import Image
from pypdf import PdfReader
from reportlab.pdfgen.canvas import Canvas

from puzzlepress import load_project
from puzzlepress.interior import build_interior, write_interior
from puzzlepress.interior.inspection import read_pdf_facts
from puzzlepress.interior.spec import PAPERBACK_LETTER
from puzzlepress.preflight import engine, preflight_interior, read_interior_artifacts, report_bytes
from tests.helpers import DEMO


def _pdf() -> bytes:
    buffer = io.BytesIO()
    canvas = Canvas(buffer, pagesize=(612, 792), invariant=1)
    image = Image.new("RGB", (8, 8), (90, 40, 10))
    canvas.drawString(72, 700, "No images here")
    canvas.showPage()
    canvas.drawInlineImage(image, 72, 600, width=40, height=40)
    canvas.showPage()
    canvas.drawImage(_reader(image), 72, 600, width=40, height=40)
    canvas.showPage()
    canvas.drawString(72, 700, "BI BIKE CABIN")  # The bytes BI without an image.
    canvas.showPage()
    canvas.save()
    return buffer.getvalue()


def _reader(image: Image.Image):  # type: ignore[no-untyped-def]
    from reportlab.lib.utils import ImageReader

    return ImageReader(image)


def test_image_counts_equal_pypdfs_own() -> None:
    data = _pdf()
    facts = read_pdf_facts(data)
    assert not isinstance(facts, Exception) and hasattr(facts, "pages")
    expected = [len(page.images) for page in PdfReader(io.BytesIO(data)).pages]
    assert [page.images for page in facts.pages] == expected == [0, 1, 1, 0]


@pytest.fixture(scope="module")
def demo():  # type: ignore[no-untyped-def]
    project = load_project(DEMO).project
    return project, build_interior(project, PAPERBACK_LETTER)


def test_a_build_carries_the_facts_of_its_own_bytes(demo) -> None:  # type: ignore[no-untyped-def]
    _, build = demo
    assert build.facts == read_pdf_facts(build.pdf)


def test_preflight_reuses_facts_only_for_identical_bytes(  # type: ignore[no-untyped-def]
    demo, tmp_path, monkeypatch
) -> None:
    project, build = demo
    write_interior(build, tmp_path / "out", DEMO)
    artifacts = read_interior_artifacts(tmp_path / "out")
    reference = report_bytes(
        preflight_interior(project, artifacts, replace(build, facts=None)).report
    )
    calls: list[int] = []
    real = engine.read_pdf_facts

    def counted(data: bytes):  # type: ignore[no-untyped-def]
        calls.append(len(data))
        return real(data)

    monkeypatch.setattr(engine, "read_pdf_facts", counted)
    reused = report_bytes(preflight_interior(project, artifacts, build).report)
    assert calls == [] and reused == reference
    # Different bytes are always read afresh.
    assert artifacts.pdf is not None
    changed = replace(artifacts, pdf=artifacts.pdf + b"\n%")
    preflight_interior(project, changed, build)
    assert calls == [len(changed.pdf)]
