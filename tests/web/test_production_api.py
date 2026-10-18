"""Studio API for region covers, assets, interior drafts, reviews, proofs and rebuilds."""

import pytest
from fastapi.testclient import TestClient

from puzzlepress.studio import production as production_module
from puzzlepress.studio.server import create_app
from tests.cover_helpers import cover_project, photo_bytes


def _output(data):
    data["output"] = {"directory": "../../build/book"}


@pytest.fixture
def studio(tmp_path):
    books = tmp_path / "books"
    source, _ = cover_project(books, mutate=_output, build_interior=False)
    client = TestClient(create_app(books, tmp_path / "frontend"))
    return client, source


def detail(client):
    return client.get("/api/projects/book").json()


def build_all(client):
    revision = detail(client)["revision"]
    result = client.post("/api/projects/book/rebuild", json={"revision": revision}).json()
    assert result["rebuild"]["success"], result
    return result


def save(client, source):
    revision = detail(client)["revision"]
    response = client.post(
        "/api/projects/book/draft/save", json={"source": source, "revision": revision}
    )
    assert response.status_code == 200, response.json()
    return response.json()


# ------------------------------------------------------------------ cover


def test_convert_is_verified_and_presets_are_offered(studio):
    client, _ = studio
    build_all(client)
    source = detail(client)["source"]
    converted = client.post(
        "/api/projects/book/draft/cover/convert", json={"source": source}
    ).json()
    assert converted["success"] and converted["identical"] is True
    assert (
        converted["cover"]["version"] == 3 and converted["cover"]["elements"][0]["type"] == "photo"
    )
    assert detail(client)["source"]["cover"]["version"] == 1  # Nothing was saved.
    designed = {**source, "cover": converted["cover"]}
    result = client.post("/api/projects/book/draft/cover", json={"source": designed}).json()
    assert result["success"] and result["layout"]["elements"][0]["layer"] == "element:photo"
    assert set(result["layout"]["regions"]) == {"back", "spine", "front", "wrap"}
    again = client.post("/api/projects/book/draft/cover/convert", json={"source": designed})
    assert again.status_code == 422 and again.json()["error"]["code"] == "already_designed"
    presets = client.post("/api/projects/book/draft/cover/presets", json={"source": source}).json()
    assert [p["id"] for p in presets["presets"]][:2] == [
        "front-photo-solid-back",
        "full-wrap-photo",
    ]


# ------------------------------------------------------------------ assets


def upload(client, data, name):
    response = client.post(
        "/api/projects/book/cover/assets",
        params={"name": name},
        content=data,
        headers={"content-type": "image/jpeg"},
    )
    assert response.status_code == 200, response.json()
    return response.json()["asset"]


def test_asset_library_protects_saved_and_draft_uses(studio):
    client, _ = studio
    spare = upload(client, photo_bytes(600, 400), "spare.jpg")
    project = detail(client)
    listing = client.post("/api/projects/book/assets/list", json={}).json()
    used = next(a for a in listing["assets"] if a["in_use"])
    response = client.post(
        "/api/projects/book/assets/trash",
        json={"path": used["path"], "sha256": used["sha256"], "revision": project["revision"]},
    )
    assert response.status_code == 409 and response.json()["error"]["code"] == "asset_in_use"
    assert response.json()["error"]["uses"][0]["label"] == "Cover photograph"
    draft = project["source"]
    draft = {
        **draft,
        "cover": {**draft["cover"], "image": {"path": spare["path"], "sha256": spare["sha256"]}},
    }
    response = client.post(
        "/api/projects/book/assets/trash",
        json={
            "path": spare["path"],
            "sha256": spare["sha256"],
            "revision": project["revision"],
            "source": draft,
        },
    )
    assert response.status_code == 409
    assert response.json()["error"]["uses"][0]["source"] == "draft"
    response = client.post(
        "/api/projects/book/assets/trash",
        json={"path": spare["path"], "sha256": spare["sha256"], "revision": "sha256-" + "0" * 64},
    )
    assert response.status_code == 409 and response.json()["error"]["code"] == "source_changed"
    moved = client.post(
        "/api/projects/book/assets/trash",
        json={"path": spare["path"], "sha256": spare["sha256"], "revision": project["revision"]},
    ).json()
    assert moved["trashed"]["reference"] == spare["path"]
    assert [t["restores_to"] for t in moved["trash"]] == [spare["path"]]
    trashed = moved["trash"][0]["trashed"]
    restored = client.post("/api/projects/book/assets/restore", json={"trashed": trashed}).json()
    assert restored["restored"] == spare["path"] and restored["trash"] == []


def test_asset_requests_never_take_filesystem_paths(studio):
    client, source = studio
    project = detail(client)
    for path in ("../book.yaml", "cover-assets/../book.yaml", str(source / "book.yaml")):
        response = client.post(
            "/api/projects/book/assets/trash",
            json={"path": path, "sha256": "0" * 64, "revision": project["revision"]},
        )
        assert response.status_code in (404, 422)
    assert (source / "book.yaml").exists()
    response = client.post(
        "/api/projects/book/assets/purge", json={"trashed": "../book.yaml", "sha256": "0" * 64}
    )
    assert response.status_code == 404


# ------------------------------------------------------------------ interior drafts


def source_per_page(source):
    return source["composition"]["solutions"].get("per_page", 4)


def test_interior_design_catalogue_export_and_import(studio):
    client, source = studio
    catalogue = client.get("/api/interior/designs").json()
    assert [t["id"] for t in catalogue["themes"]][:2] == ["classic", "racing_orange"]
    assert {layout["id"] for layout in catalogue["layouts"]} >= {"classic", "bold_header"}
    project = detail(client)["source"]
    design = {"version": 2, "theme": "racing_orange", "layout": "bold_header"}
    styled = {**project, "interior": design}
    result = client.post("/api/projects/book/draft/interior", json={"source": styled}).json()
    assert result["success"] and result["design"]["look"]["theme"] == "racing_orange"
    exported = client.post(
        "/api/projects/book/draft/interior/export",
        json={"source": styled, "name": "Automotive Racing"},
    )
    assert exported.status_code == 200
    assert "automotive-racing.puzzlepress-design.json" in exported.headers["content-disposition"]
    imported = client.post(
        "/api/projects/book/draft/interior/import",
        json={"source": project, "text": exported.text},
    ).json()
    assert imported == {"success": True, "name": "Automotive Racing", "interior": design}
    refused = client.post(
        "/api/projects/book/draft/interior/import", json={"source": project, "text": "{}"}
    ).json()
    assert not refused["success"] and refused["issues"][0]["code"] == "format"
    no_style = client.post(
        "/api/projects/book/draft/interior/export", json={"source": project, "name": "X"}
    )
    assert no_style.status_code == 422
    assert detail(client)["source"] == project  # Nothing is saved by any of these.


def test_interior_draft_reports_unreadable_answer_layouts(studio):
    client, _ = studio
    project = detail(client)["source"]
    project["composition"]["solutions"]["per_page"] = 4
    for profile in project["word_search"]["profiles"]:
        profile["width"] = profile["height"] = 26
    result = client.post("/api/projects/book/draft/interior", json={"source": project}).json()
    assert not result["success"]
    (issue,) = result["diagnostics"]
    assert issue["code"] == "solution_layout_unreadable" and "Choose 1 " in issue["message"]
    fits = {c["per_page"]: c for c in result["answers"]["choices"]}
    assert not fits[4]["fits"] and fits[1]["fits"] and fits[1]["grid"] == [26, 26]
    assert result["answers"]["per_page"] == 4  # The author's choice is reported, not changed.


def test_saved_design_persists_and_keeps_other_sections(studio):
    client, source = studio
    project = detail(client)["source"]
    styled = {
        **project,
        "interior": {"version": 2, "theme": "ink_saver", "layout": "clean_minimal"},
    }
    styled["composition"]["solutions"]["per_page"] = 4
    save(client, styled)
    reloaded = detail(client)["source"]
    assert reloaded["interior"] == styled["interior"]
    assert reloaded["composition"]["solutions"]["per_page"] == 4
    for key in ("book", "word_search", "cover"):
        assert reloaded[key] == project[key]
    assert "theme: ink_saver" in (source / "book.yaml").read_text(encoding="utf-8")


def test_interior_draft_renders_sample_pages_without_writing(studio):
    client, source = studio
    project = detail(client)["source"]
    styled = {**project, "interior": {"version": 1, "preset": "high_contrast"}}
    result = client.post("/api/projects/book/draft/interior", json={"source": styled}).json()
    assert result["success"] and result["design"]["preset"] == "high_contrast"
    kinds = {p["kind"] for p in result["pages"]}
    assert {"title_page", "puzzle", "solutions"} <= kinds
    roles = {role for p in result["pages"] for role in p["roles"]}
    assert {"title", "puzzle", "answers"} <= roles
    assert result["answers"]["per_page"] == source_per_page(project)
    assert {c["per_page"] for c in result["answers"]["choices"]} == {1, 2, 4, 6, 8}
    image = client.get(
        "/api/projects/book/draft/interior/pages/1",
        params={"size": "thumb", "pdf": result["pdf_sha256"]},
    )
    assert image.status_code == 200 and image.headers["content-type"] == "image/png"
    assert not (source.parent.parent / "build" / "book" / "interior.pdf").exists()
    stale = client.get(
        "/api/projects/book/draft/interior/pages/1", params={"size": "thumb", "pdf": "0" * 64}
    )
    assert stale.status_code == 409


# ------------------------------------------------------------------ reviews and proofs


def test_reviews_bind_to_saved_content(studio):
    client, _ = studio
    status = client.get("/api/projects/book/reviews").json()
    first = status["report"]["puzzles"][0]
    assert first["state"] == "not_reviewed" and status["revision"] is None
    payload = {
        "source_revision": status["source_revision"],
        "revision": None,
        "puzzle": first["puzzle"],
        "status": "reviewed",
        "identity": first["identity"],
        "note": "Terms checked.",
    }
    result = client.post("/api/projects/book/reviews/record", json=payload).json()
    assert result["report"]["puzzles"][0]["state"] == "reviewed"
    wrong = client.post(
        "/api/projects/book/reviews/record",
        json={
            **payload,
            "revision": result["revision"],
            "identity": "pp1-puzzle-review-sha256-" + "0" * 64,
        },
    )
    assert wrong.status_code == 409 and wrong.json()["error"]["code"] == "content_changed"
    conflict = client.post("/api/projects/book/reviews/record", json=payload)
    assert conflict.status_code == 409  # reviews.yaml exists now: the null revision is stale.
    source = detail(client)["source"]
    source["word_search"]["puzzles"][0]["title"] = "Edited title"
    save(client, source)
    after = client.get("/api/projects/book/reviews").json()
    assert after["report"]["puzzles"][0]["state"] == "stale"


def test_proofs_need_current_artifacts(studio):
    client, _ = studio
    empty = client.get("/api/projects/book/proofs").json()
    assert empty["artifacts"] is None and empty["physical_proof"] is None
    build_all(client)
    proofs = client.get("/api/projects/book/proofs").json()
    record = {
        "id": "proof-1",
        "kind": "physical_proof",
        "status": "received",
        "decision": "undecided",
        "artifacts": proofs["artifacts"],
    }
    saved = client.post(
        "/api/projects/book/proofs/record", json={"revision": None, "record": record}
    ).json()
    assert saved["physical_proof"]["current"] is True
    stale = {
        **record,
        "id": "proof-2",
        "artifacts": {**proofs["artifacts"], "interior_pdf": "0" * 64},
    }
    response = client.post(
        "/api/projects/book/proofs/record", json={"revision": saved["revision"], "record": stale}
    )
    assert response.status_code == 409 and response.json()["error"]["code"] == "artifacts_changed"


# ------------------------------------------------------------------ production


def test_production_overview_and_rebuild(studio):
    client, _ = studio
    before = client.get("/api/projects/book/production").json()
    assert before["assessment"]["outdated"] is True
    assert [s["action"] for s in before["assessment"]["steps"]] == ["build_interior", "build_cover"]
    after = build_all(client)
    assert after["assessment"]["outdated"] is False
    assert [r["status"] for r in after["rebuild"]["results"]] == ["succeeded", "succeeded"]
    assert after["proofs"]["revision"] is None  # No proofs.yaml yet: records start from null.
    items = {i["code"]: i["status"] for i in after["items"]}
    assert (
        items["interior_current"] == "completed" and items["print_previewer"] == "external_pending"
    )
    stale = client.post("/api/projects/book/rebuild", json={"revision": "sha256-" + "0" * 64})
    assert stale.status_code == 409


def test_rebuild_stops_when_the_source_changes(studio, monkeypatch):
    client, source = studio
    revision = detail(client)["revision"]
    original = production_module.rebuild

    def edit_then_run(project, source_dir, directory, spec, actions, before_write):
        path = source_dir / "book.yaml"
        path.write_text(path.read_text(encoding="utf-8") + "\n", encoding="utf-8")
        return original(project, source_dir, directory, spec, actions, before_write)

    monkeypatch.setattr(production_module, "rebuild", edit_then_run)
    result = client.post("/api/projects/book/rebuild", json={"revision": revision}).json()
    assert result["rebuild"]["code"] == "source_changed" and result["rebuild"]["results"] == []
    assert not (source.parent.parent / "build" / "book" / "interior.pdf").exists()
