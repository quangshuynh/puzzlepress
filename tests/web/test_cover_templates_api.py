"""Cover Studio API for templates: gallery, previews, custom templates, import and export."""

import json

import pytest
from fastapi.testclient import TestClient

from puzzlepress.cover_template_store import BUILTIN_ORDER
from puzzlepress.studio.server import create_app
from tests.cover_helpers import cover_project


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


def preview(client, template_id, source):
    return client.post(
        f"/api/projects/book/draft/cover/templates/{template_id}/preview", json={"source": source}
    )


def snapshot(folder):
    return {
        p.relative_to(folder).as_posix(): p.read_bytes() for p in folder.rglob("*") if p.is_file()
    }


def test_gallery_lists_the_eight_builtins_with_their_requirements(studio):
    client, _ = studio
    gallery = client.get("/api/projects/book/cover/templates").json()
    ids = [t["id"] for t in gallery["templates"]]
    assert ids == list(BUILTIN_ORDER) and gallery["problems"] == []
    lead = gallery["templates"][0]
    assert lead["name"] == "Photographic Editorial" and lead["photo"] == "required"
    assert lead["builtin"] and lead["fonts"] and lead["category"] == "photographic"
    assert all(t["description"] and t["palette"] for t in gallery["templates"])


def test_previews_render_every_template_without_saving(studio, tmp_path):
    client, source_dir = studio
    before = snapshot(source_dir)
    source = detail(client)["source"]
    for template_id in BUILTIN_ORDER:
        result = preview(client, template_id, source).json()
        assert result["success"], result
        assert result["buildable"], result["checks"]
        assert result["cover"]["version"] == 3
        assert result["current"]["title"] == source["book"]["title"]
        assert result["replaced"] and result["kept"]
        image = client.get(
            "/api/projects/book/cover/preview",
            params={"size": "thumb", "pdf": result["preview"]["pdf_sha256"]},
        )
        assert image.status_code == 200 and image.content.startswith(b"\x89PNG")
    assert snapshot(source_dir) == before  # Browsing and previewing never write.
    # The applied cover is an ordinary draft the existing draft endpoint renders identically.
    result = preview(client, "bold-garage", source).json()
    drafted = client.post(
        "/api/projects/book/draft/cover", json={"source": {**source, "cover": result["cover"]}}
    ).json()
    assert drafted["success"] and drafted["preview"] == result["preview"]


def test_missing_photo_preview_reports_the_placeholder(studio):
    client, _ = studio
    source = detail(client)["source"]
    source["cover"] = {
        "version": 3,
        "regions": {k: {"color": "#1d2a44"} for k in ("back", "spine", "front")},
        "elements": [],
    }
    result = preview(client, "photographic-editorial", source).json()
    assert result["missing_slots"] == [1]
    assert any(c["code"] == "template_photo_placeholder" for c in result["checks"])
    assert not [e for e in result["cover"]["elements"] if e["type"] == "photo"]


def test_unknown_and_unsafe_template_ids_are_refused(studio):
    client, _ = studio
    source = detail(client)["source"]
    assert preview(client, "nope", source).status_code == 404
    assert client.get("/api/projects/book/cover/templates/..%2Fbook/export").status_code == 404


def test_custom_template_save_rename_duplicate_export_import_and_delete(studio):
    client, source_dir = studio
    source = detail(client)["source"]
    saved = client.post(
        "/api/projects/book/cover/templates",
        json={"source": source, "name": "My Harbour", "description": "From this cover."},
    ).json()
    template = saved["template"]
    assert template["id"] == "my-harbour" and not template["builtin"]
    stored = (source_dir / "cover-templates" / "my-harbour.json").read_text()
    assert source["book"]["title"] not in stored and '"image"' not in stored
    renamed = client.post(
        "/api/projects/book/cover/templates/my-harbour/update",
        json={"identity": template["identity"], "name": "Harbour", "description": ""},
    ).json()["template"]
    stale = client.post(
        "/api/projects/book/cover/templates/my-harbour/update",
        json={"identity": template["identity"], "name": "Stale"},
    )
    assert stale.status_code == 409
    copy = client.post(
        "/api/projects/book/cover/templates/my-harbour/duplicate", json={"name": "Harbour copy"}
    ).json()["template"]
    assert copy["id"] == "harbour-copy"
    exported = client.get("/api/projects/book/cover/templates/my-harbour/export")
    assert exported.headers["content-disposition"].startswith("attachment")
    imported = client.post(
        "/api/projects/book/cover/templates/import", json={"text": exported.text}
    ).json()["template"]
    assert imported["id"] == "my-harbour-2" and imported["name"] == "Harbour"
    assert preview(client, "my-harbour-2", source).json()["success"]
    refused = client.post(
        "/api/projects/book/cover/templates/my-harbour/delete",
        json={"identity": template["identity"]},
    )
    assert refused.status_code == 409
    gallery = client.post(
        "/api/projects/book/cover/templates/my-harbour/delete",
        json={"identity": renamed["identity"]},
    ).json()
    custom = [t["id"] for t in gallery["templates"] if not t["builtin"]]
    assert custom == ["my-harbour-2", "harbour-copy"]  # By name: Harbour, Harbour copy.


def test_builtins_cannot_be_changed_and_imports_are_validated(studio):
    client, _ = studio
    gallery = client.get("/api/projects/book/cover/templates").json()
    builtin = gallery["templates"][1]
    assert (
        client.post(
            "/api/projects/book/cover/templates/bold-garage/delete",
            json={"identity": builtin["identity"]},
        ).status_code
        == 403
    )
    assert (
        client.post(
            "/api/projects/book/cover/templates/bold-garage/update",
            json={"identity": builtin["identity"], "name": "Mine"},
        ).status_code
        == 403
    )
    exported = client.get("/api/projects/book/cover/templates/bold-garage/export").json()
    exported["template_version"] = 9
    bad = client.post(
        "/api/projects/book/cover/templates/import", json={"text": json.dumps(exported)}
    )
    assert bad.status_code == 422 and bad.json()["error"]["code"] == "template_version"
    exported["template_version"] = 1
    exported["design"]["elements"].append({"id": "x", "type": "script", "region": "front"})
    bad = client.post(
        "/api/projects/book/cover/templates/import", json={"text": json.dumps(exported)}
    )
    assert bad.status_code == 422
    huge = client.post("/api/projects/book/cover/templates/import", json={"text": "x" * 300_000})
    assert huge.status_code == 413
    # An imported built-in becomes a custom copy, never a replacement.
    exported["design"]["elements"].pop()
    copy = client.post(
        "/api/projects/book/cover/templates/import", json={"text": json.dumps(exported)}
    ).json()["template"]
    assert copy["id"] == "bold-garage-2" and copy["category"] == "custom"


def test_low_contrast_is_advisory_and_never_blocks(studio):
    client, _ = studio
    source = detail(client)["source"]
    navy = {k: {"color": "#1d2a44"} for k in ("back", "spine", "front")}
    source["cover"] = {
        "version": 3,
        "regions": navy,
        "elements": [
            {
                "id": "note",
                "type": "text",
                "region": "front",
                "box": {"x": 72, "y": 300, "width": 300, "height": 40},
                "text": "Hard to read",
                "color": "#22304d",
            }
        ],
        "type": {"tone": "light"},
    }
    result = client.post("/api/projects/book/draft/cover", json={"source": source}).json()
    low = [c for c in result["checks"] if c["code"] == "low_contrast"]
    assert [c["layer"] for c in low] == ["element:note"]
    assert low[0]["severity"] == "warning" and result["buildable"]
