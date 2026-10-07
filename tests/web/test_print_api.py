"""Print API: interior build, preflight status, stale detection and safe page previews."""

import hashlib
import io
import threading
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from puzzlepress import dump_project, load_project
from puzzlepress.studio.preview import PageRasterizer
from puzzlepress.studio.printing import PrintService
from puzzlepress.studio.server import create_app
from puzzlepress.studio.service import ProjectStore, StudioError, StudioService
from tests.helpers import DEMO, demo_variant


@pytest.fixture
def studio(tmp_path, garden):
    books = tmp_path / "books"
    for key, project in (("demo", load_project(DEMO).project), ("legacy", garden)):
        (books / key).mkdir(parents=True)
        (books / key / "book.yaml").write_text(dump_project(project), encoding="utf-8")
    client = TestClient(create_app(books, tmp_path / "frontend"))
    output = tmp_path / "build" / "composition-demo"  # ../../build/composition-demo
    return client, books, output


def build(client, key="demo"):
    revision = client.get(f"/api/projects/{key}").json()["revision"]
    return client.post(f"/api/projects/{key}/interior/build", json={"revision": revision})


def page(client, number, size="page", pdf=None, key="demo"):
    return client.get(
        f"/api/projects/{key}/interior/pages/{number}", params={"size": size, "pdf": pdf}
    )


def test_missing_then_build_then_current_status(studio):
    client, books, output = studio
    before = (books / "demo" / "book.yaml").read_bytes()
    missing = client.get("/api/projects/demo/interior")
    assert missing.status_code == 200
    assert missing.json()["state"] == "missing" and missing.json()["report"] is None
    assert not output.exists()
    response = build(client)
    assert response.status_code == 200
    data = response.json()
    assert data["build"] == {"success": True} and data["state"] == "current"
    report = data["report"]
    assert report["structural"]["status"] == "valid" and report["kdp"]["status"] == "not_ready"
    assert [f["rule"] for f in report["findings"] if f["severity"] == "error"] == [
        "kdp_minimum_page_count"
    ]
    assert sorted(p.name for p in output.iterdir()) == [
        "interior.json",
        "interior.pdf",
        "preflight.json",
    ]
    preview = data["preview"]
    pdf = (output / "interior.pdf").read_bytes()
    assert preview["pdf_sha256"] == hashlib.sha256(pdf).hexdigest()
    assert preview["page_count"] == 11 and preview["scales"]["page"] == 2.0
    pages = preview["pages"]
    assert [p["kind"] for p in pages[:5]] == [
        "title_page",
        "copyright_page",
        "instructions",
        "blank",
        "puzzle",
    ]
    assert pages[4]["description"].startswith("Puzzle 1: Along the Shoreline")
    geometry = preview["geometry"]
    recto, verso = geometry[4], geometry[5]
    assert recto["trim"] == {"x": 0, "y": 0, "width": 612, "height": 792}
    assert recto["live"] == {"x": 54, "y": 45, "width": 522, "height": 702}
    assert verso["live"]["x"] == 36  # Mirrored: binding on the right of a verso page.
    assert recto["kdp_safe"] == {"x": 27, "y": 18, "width": 567, "height": 756}
    assert verso["kdp_safe"]["x"] == 18
    assert geometry[3]["elements"] == [] and recto["elements"]
    again = client.get("/api/projects/demo/interior").json()
    assert again["report"] == report  # Same artifacts and revision: same verdict.
    assert (books / "demo" / "book.yaml").read_bytes() == before


def test_build_requires_the_saved_revision_and_a_composition(studio):
    client, _, output = studio
    stale = client.post("/api/projects/demo/interior/build", json={"revision": "sha256-x"})
    assert stale.status_code == 409 and stale.json()["error"]["code"] == "source_changed"
    assert not output.exists()
    legacy = client.get("/api/projects/legacy/interior")
    assert legacy.status_code == 422 and legacy.json()["error"]["code"] == "no_composition"
    unknown = client.get("/api/projects/nope/interior")
    assert unknown.status_code == 404


def test_failed_build_reports_diagnostics_and_writes_nothing(studio):
    client, books, output = studio

    def overflow(data):
        data["composition"]["front_matter"][2]["text"] = "x\n" * 999 + "x"

    (books / "demo" / "book.yaml").write_text(
        dump_project(demo_variant(overflow)), encoding="utf-8"
    )
    data = build(client).json()
    assert data["build"]["success"] is False and data["build"]["stage"] == "layout"
    assert data["build"]["diagnostics"][0]["code"] == "text_overflow"
    assert data["state"] == "missing" and not output.exists()


def test_source_change_after_build_marks_the_interior_stale(studio):
    client, books, _ = studio
    build(client)

    def retitled(data):
        data["book"]["title"] = "Changed after build"

    (books / "demo" / "book.yaml").write_text(
        dump_project(demo_variant(retitled)), encoding="utf-8"
    )
    data = client.get("/api/projects/demo/interior").json()
    assert data["state"] == "stale"
    assert data["report"]["structural"]["status"] == "invalid"
    assert "source_current" in {f["rule"] for f in data["report"]["findings"]}
    preview = data["preview"]
    assert preview["geometry"] is None and "description" not in preview["pages"][0]


def test_manifest_pdf_mismatch_is_invalid_not_stale(studio):
    client, _, output = studio
    build(client)
    (output / "interior.pdf").write_bytes((output / "interior.pdf").read_bytes() + b"%x\n")
    data = client.get("/api/projects/demo/interior").json()
    assert data["state"] == "invalid"
    assert "manifest_pdf_digest" in {f["rule"] for f in data["report"]["findings"]}


def test_page_previews_are_real_rasters_of_the_pdf(studio):
    client, _, output = studio
    digest = build(client).json()["preview"]["pdf_sha256"]
    first = page(client, 1, pdf=digest)
    assert first.status_code == 200 and first.headers["content-type"] == "image/png"
    assert "immutable" in first.headers["cache-control"]
    image = Image.open(io.BytesIO(first.content))
    assert image.size == (1224, 1584)
    assert Image.open(io.BytesIO(page(client, 11, "thumb", digest).content)).size == (306, 396)
    detail = Image.open(io.BytesIO(page(client, 5, "detail", digest).content))
    assert detail.size == (2448, 3168)
    blank = Image.open(io.BytesIO(page(client, 4, "thumb", digest).content)).convert("L")
    assert blank.getextrema() == (255, 255)  # The intentional blank is truly blank.
    # Ink falls inside the authoritative live area: 0.75 in inside, 0.5 in outside.
    puzzle = Image.open(io.BytesIO(page(client, 5, pdf=digest).content)).convert("L")
    dark = puzzle.point(lambda v: 255 if v < 200 else 0).getbbox()
    assert dark is not None
    left, top, right, bottom = dark
    assert left >= 0.75 * 144 - 2 and right <= (8.5 - 0.5) * 144 + 2
    assert top >= 0.625 * 144 - 2 and bottom <= (11 - 0.625) * 144 + 2
    assert client.get("/api/projects/demo/interior").headers["cache-control"] == "no-store"


@pytest.mark.parametrize(
    ("number", "size", "pdf", "status"),
    [
        (0, "page", None, 404),
        (12, "page", None, 404),
        (-1, "page", None, 404),
        (1, "huge", None, 404),
        (1, "../interior.json", None, 404),
        (1, "page", "0" * 64, 409),
        (1, "page", "../../book.yaml", 422),
        (1, "page", "", 422),
    ],
)
def test_preview_requests_are_bounded(studio, number, size, pdf, status):
    client, _, _ = studio
    digest = build(client).json()["preview"]["pdf_sha256"]
    response = page(client, number, size, pdf if pdf is not None else digest)
    assert response.status_code == status


@pytest.mark.parametrize(
    "path",
    [
        "/api/projects/../interior/pages/1?size=page&pdf=" + "0" * 64,
        "/api/projects/%2e%2e/interior/pages/1?size=page&pdf=" + "0" * 64,
        "/api/projects/demo/interior/pages/..%2finterior.json?size=page&pdf=" + "0" * 64,
        "/api/projects/demo/interior/pages/1.png?size=page&pdf=" + "0" * 64,
        "/api/projects/..%5c..%5cbooks/interior",
        "/api/projects/demo%2f..%2f..%2fbuild/interior",
    ],
)
def test_traversal_never_reaches_files(studio, path):
    client, _, _ = studio
    build(client)
    response = client.get(path)
    assert response.status_code in (404, 422)
    assert not response.headers["content-type"].startswith("image/")


def test_preview_missing_interior_and_unknown_project(studio):
    client, _, _ = studio
    assert page(client, 1, pdf="0" * 64).json()["error"]["code"] == "interior_missing"
    assert page(client, 1, pdf="0" * 64, key="nope").status_code == 404


def test_cache_is_keyed_by_pdf_digest(studio, tmp_path):
    client, _, output = studio
    digest = build(client).json()["preview"]["pdf_sha256"]
    rasterizer = PageRasterizer()
    pdf = (output / "interior.pdf").read_bytes()
    first = rasterizer.png(pdf, digest, 5, "thumb")
    assert rasterizer.png(pdf, digest, 5, "thumb") == first and rasterizer.renders == 1
    other = (output / "interior.pdf").read_bytes() + b"%x\n"
    other_digest = hashlib.sha256(other).hexdigest()
    rasterizer.png(other, other_digest, 5, "thumb")
    assert rasterizer.renders == 2  # A new digest is never served the old image.
    tiny = PageRasterizer(budget=1)
    tiny.png(pdf, digest, 1, "thumb")
    tiny.png(pdf, digest, 2, "thumb")
    assert len(tiny._cache) == 1
    # A rebuilt interior with new bytes makes old preview URLs stale, never wrong.
    Path(output / "interior.pdf").write_bytes(other)
    assert page(client, 1, "thumb", digest).json()["error"]["code"] == "preview_stale"


def test_status_waits_for_a_running_request_instead_of_failing(studio):
    client, books, _ = studio
    build(client)
    service = StudioService(ProjectStore(books.resolve()))
    printing = PrintService(service)
    results: list[str] = []
    with service.exclusive():
        # A draft request still fails fast with the existing 409 contract...
        with pytest.raises(StudioError) as busy:
            service.plan_project(load_project(DEMO).project)
        assert busy.value.code == "generation_busy"
        # ...while a print status read queues behind the running request.
        thread = threading.Thread(target=lambda: results.append(printing.status("demo")["state"]))
        thread.start()
        thread.join(timeout=0.5)
        assert thread.is_alive() and results == []
    thread.join(timeout=60)
    assert results == ["current"]
