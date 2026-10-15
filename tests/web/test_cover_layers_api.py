"""Cover Studio API for version 2: layers, fonts, thumbnails, specimens and readiness."""

import io

import pytest
from fastapi.testclient import TestClient
from PIL import Image

from puzzlepress.studio.server import create_app
from tests.cover_helpers import cover_project, photo_bytes
from tests.font_helpers import ITALIC, bundled, cff_signature, with_fs_type


def _output(data):
    data["output"] = {"directory": "../../build/book"}


@pytest.fixture
def studio(tmp_path):
    books = tmp_path / "books"
    source, _ = cover_project(books, mutate=_output, build_interior=False)
    client = TestClient(create_app(books, tmp_path / "frontend"))
    revision = client.get("/api/projects/book").json()["revision"]
    assert client.post("/api/projects/book/interior/build", json={"revision": revision}).json()
    return client, source


def detail(client):
    return client.get("/api/projects/book").json()


def draft(client, source):
    return client.post("/api/projects/book/draft/cover", json={"source": source}).json()


def upload_font(client, data, name="Display.ttf", kind="font/ttf"):
    return client.post(
        "/api/projects/book/cover/fonts",
        params={"name": name},
        content=data,
        headers={"content-type": kind},
    )


def with_cover(source, **changes):
    cover = {**source["cover"], "version": 2, **changes}
    return {**source, "cover": cover}


def test_draft_reports_layers_library_and_display(studio):
    client, _ = studio
    source = detail(client)["source"]
    result = draft(client, with_cover(source, text={"title": {"visible": False}}))
    assert result["success"] and result["buildable"]
    layers = {text["layer"] for text in result["layout"]["texts"]}
    assert "title" not in layers and {"subtitle", "author", "back_text", "imprint"} <= layers
    assert result["display"]["title"] is None
    assert any(c["code"] == "cover_text_omitted" for c in result["checks"])
    photos = result["library"]["photos"]
    assert photos and photos[0]["dpi"]["minimum"] == 300
    assert {"effective", "max", "sufficient"} <= set(photos[0]["dpi"])
    assert {f["key"] for f in result["library"]["bundled_fonts"]} >= {"serif", "sans-bold"}
    # The book's title is untouched by a hidden cover title.
    assert detail(client)["source"]["book"]["title"] == source["book"]["title"]


def test_out_of_safe_area_drafts_preview_but_are_not_buildable(studio):
    client, _ = studio
    source = detail(client)["source"]
    result = draft(client, with_cover(source, text={"title": {"offset": {"x": 0, "y": 300}}}))
    assert result["success"] is True and result["buildable"] is False
    blocking = [c for c in result["checks"] if c["code"] == "unsafe_front_text"]
    assert blocking and blocking[0]["layer"] == "title"


def test_display_text_that_differs_from_the_book_is_flagged(studio):
    client, _ = studio
    source = detail(client)["source"]
    result = draft(client, with_cover(source, text={"title": {"text": "Another Name"}}))
    assert [c["severity"] for c in result["checks"] if c["code"] == "cover_text_differs"] == [
        "error"
    ]
    same = draft(
        client, with_cover(source, text={"title": {"text": source["book"]["title"].upper()}})
    )
    assert not [c for c in same["checks"] if c["code"] == "cover_text_differs"]


def test_font_import_listing_specimen_and_use(studio):
    client, source_dir = studio
    response = upload_font(client, bundled(ITALIC))
    assert response.status_code == 200, response.text
    font = response.json()["font"]
    assert font["path"].startswith("cover-assets/fonts/display-") and not font["reused"]
    assert font["embedding"] == "installable"
    assert (source_dir / font["path"]).read_bytes() == bundled(ITALIC)
    listed = client.get("/api/projects/book/cover/fonts").json()["fonts"]
    assert [f["path"] for f in listed] == [font["path"]]
    specimen = client.get("/api/projects/book/cover/fonts/specimen", params={"font": font["path"]})
    assert specimen.status_code == 200 and specimen.content.startswith(b"\x89PNG")
    bundled_specimen = client.get(
        "/api/projects/book/cover/fonts/specimen", params={"font": "bundled:serif"}
    )
    assert bundled_specimen.status_code == 200
    source = detail(client)["source"]
    styled = with_cover(
        source,
        fonts=[{"id": "display", "path": font["path"], "sha256": font["sha256"]}],
        text={"subtitle": {"font": "display", "size": 24}},
    )
    result = draft(client, styled)
    assert result["success"], result
    subtitle = [t for t in result["layout"]["texts"] if t["layer"] == "subtitle"]
    assert subtitle and all(t["face"].startswith("PuzzlePressFont-") for t in subtitle)
    assert any(c["code"] == "cover_font_license" for c in result["checks"])
    library = result["library"]["fonts"]
    assert library[0]["missing"] == []
    saved = client.post(
        "/api/projects/book/draft/save",
        json={"source": styled, "revision": detail(client)["revision"]},
    )
    assert saved.status_code == 200, saved.text
    built = client.post(
        "/api/projects/book/cover/build", json={"revision": detail(client)["revision"]}
    )
    assert built.json()["build"]["success"] is True


@pytest.mark.parametrize(
    ("make", "code"),
    [
        (lambda: with_fs_type(0x0002), "font_embedding_restricted"),
        (cff_signature, "font_unsupported_outlines"),
        (lambda: b"junk", "font_corrupt"),
    ],
    ids=["restricted", "cff", "junk"],
)
def test_bad_fonts_are_refused_and_never_written(studio, make, code):
    client, source_dir = studio
    response = upload_font(client, make())
    assert response.status_code == 422 and response.json()["error"]["code"] == code
    fonts = source_dir / "cover-assets" / "fonts"
    assert not fonts.exists() or not [p for p in fonts.iterdir() if not p.name.startswith(".")]


def test_font_upload_requires_a_font_content_type(studio):
    client, _ = studio
    for kind in ("application/octet-stream", "image/png", "text/plain"):
        response = upload_font(client, bundled(), kind=kind)
        assert response.status_code == 403
    assert upload_font(client, bundled(), name="x.otf", kind="font/otf").status_code in (200, 422)


def test_photo_thumbnails_are_small_previews_of_project_files_only(studio):
    client, source_dir = studio
    path = detail(client)["source"]["cover"]["image"]["path"]
    response = client.get("/api/projects/book/cover/assets/thumbnail", params={"path": path})
    assert response.status_code == 200 and response.headers["content-type"] == "image/jpeg"
    image = Image.open(io.BytesIO(response.content))
    assert max(image.size) <= 360
    for bad in ("../book.yaml", "cover-assets/../book.yaml", "cover-assets/missing-1.jpg"):
        refused = client.get("/api/projects/book/cover/assets/thumbnail", params={"path": bad})
        assert refused.status_code in (404, 422)
    other = photo_bytes(800, 600)
    imported = client.post(
        "/api/projects/book/cover/assets",
        params={"name": "small.jpg"},
        content=other,
        headers={"content-type": "image/jpeg"},
    ).json()["asset"]
    result = draft(client, detail(client)["source"])
    small = next(p for p in result["library"]["photos"] if p["path"] == imported["path"])
    assert small["dpi"]["sufficient"] is False and small["dpi"]["max"] < 300
