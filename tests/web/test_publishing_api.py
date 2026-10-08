"""Publishing API: status, draft metadata checks, saves, revision-checked export."""

import hashlib

import pytest
from fastapi.testclient import TestClient

from puzzlepress import load_project
from puzzlepress.publishing import evaluate_readiness
from puzzlepress.studio.server import create_app
from tests.cover_helpers import cover_project
from tests.publishing_helpers import complete_section


def _output(data):
    data["output"] = {"directory": "../../build/book"}
    data["book"]["imprint"] = None


@pytest.fixture
def studio(tmp_path):
    books = tmp_path / "books"
    source, _ = cover_project(books, mutate=_output, build_interior=False, puzzles=16)
    client = TestClient(create_app(books, tmp_path / "frontend"))
    return client, source, tmp_path / "build" / "book"


def detail(client):
    return client.get("/api/projects/book").json()


def save(client, source):
    return client.post(
        "/api/projects/book/draft/save",
        json={"source": source, "revision": detail(client)["revision"]},
    )


def build_all(client):
    revision = detail(client)["revision"]
    assert client.post("/api/projects/book/interior/build", json={"revision": revision}).json()[
        "build"
    ]["success"]
    assert client.post("/api/projects/book/cover/build", json={"revision": revision}).json()[
        "build"
    ]["success"]


def status(client):
    response = client.get("/api/projects/book/publishing")
    assert response.status_code == 200
    return response.json()


def export(client, revision=None, archive=False):
    return client.post(
        "/api/projects/book/publishing/export",
        json={"revision": revision or detail(client)["revision"], "archive": archive},
    )


def test_status_without_metadata_or_files_is_specific(studio):
    client, _, output = studio
    data = status(client)
    verdicts = data["readiness"]["verdicts"]
    assert verdicts["metadata"] == "missing" and verdicts["package"] == "not_ready"
    assert verdicts["interior"]["state"] == "missing" and verdicts["cover"]["state"] == "missing"
    codes = {f["code"] for f in data["readiness"]["findings"] if f["severity"] == "error"}
    assert codes == {"publishing_configured", "interior_present", "cover_present"}
    areas = {f["code"]: f["area"] for f in data["readiness"]["findings"]}
    assert areas["interior_present"] == "print" and areas["cover_present"] == "cover"
    assert data["package"]["export"]["state"] == "none"
    assert data["package"]["location"] == "../../build/book/publishing"
    assert data["cover_preview"] is None
    assert "Nothing on this list has been done in KDP" in data["checklist"]
    assert not output.exists()


def test_draft_metadata_checks_are_python_authoritative_and_write_nothing(studio):
    client, source, _ = studio
    project = detail(client)["source"]
    before = (source / "book.yaml").read_bytes()
    project["publishing"] = complete_section(keywords=["a"] * 2 + ["b"] * 7)
    data = client.post("/api/projects/book/draft/publishing", json={"source": project}).json()
    findings = data["metadata"]["findings"]
    assert {f["code"] for f in findings} >= {"keywords_count", "keywords_format"}
    assert any(f["field"] == "publishing.keywords.1" for f in findings)
    assert (source / "book.yaml").read_bytes() == before
    project["publishing"]["version"] = 2
    invalid = client.post("/api/projects/book/draft/publishing", json={"source": project})
    assert invalid.status_code == 422
    assert invalid.json()["error"]["issues"][0]["path"] == "publishing.version"


def test_saving_metadata_keeps_the_interior_current(studio):
    client, _, _ = studio
    build_all(client)
    project = detail(client)["source"]
    project["publishing"] = complete_section()
    assert save(client, project).status_code == 200
    data = status(client)
    verdicts = data["readiness"]["verdicts"]
    assert verdicts["interior"]["state"] == "current" and verdicts["cover"]["state"] == "current"
    assert verdicts["package"] == "ready"
    assert data["package"]["identity"].startswith("pp1-package-sha256-")
    assert data["cover_preview"]["pdf_sha256"]
    image = client.get(
        "/api/projects/book/cover/preview",
        params={"pdf": data["cover_preview"]["pdf_sha256"], "size": "preview"},
    )
    assert image.status_code == 200


def test_export_from_saved_revision_and_staleness(studio):
    client, source, output = studio
    build_all(client)
    project = detail(client)["source"]
    project["publishing"] = complete_section()
    save(client, project)
    stale = export(client, revision="sha256-" + "0" * 64)
    assert stale.status_code == 409 and stale.json()["error"]["code"] == "source_changed"
    assert not (output / "publishing").exists()
    data = export(client, archive=True).json()
    assert data["export"]["success"] and data["export"]["archive"]
    assert data["package"]["export"]["state"] == "current"
    assert data["export"]["identity"] == data["package"]["identity"]
    assert (output / "publishing" / "package.json").is_file() and (
        output / "publishing.zip"
    ).is_file()
    loaded = load_project(source)
    fresh = evaluate_readiness(loaded.project, source, output)
    assert fresh.package_ready  # Studio and CLI share one evaluator.
    project = detail(client)["source"]
    project["publishing"]["keywords"] = ["changed keyword"]
    save(client, project)
    assert status(client)["package"]["export"]["state"] == "stale"


def test_export_failure_returns_findings_and_writes_nothing(studio):
    client, _, output = studio
    build_all(client)
    project = detail(client)["source"]
    project["publishing"] = complete_section(attestations={})
    save(client, project)
    data = export(client).json()
    assert data["export"] == {
        "success": False,
        "code": "not_ready",
        "message": data["export"]["message"],
    }
    assert "Not ready" in data["export"]["message"]
    assert not (output / "publishing").exists()


def test_cover_paper_change_is_reported_specifically(studio):
    client, _, _ = studio
    build_all(client)
    project = detail(client)["source"]
    project["publishing"] = complete_section()
    save(client, project)
    revision = detail(client)["revision"]
    client.post(
        "/api/projects/book/interior/build",
        json={"revision": revision, "profile": "paperback-8.5x11-cream"},
    )
    messages = [f["message"] for f in status(client)["readiness"]["findings"]]
    assert "Cover is out of date because the interior paper changed (white -> cream)." in messages


def test_unsafe_keys_and_requests_are_rejected(studio):
    client, _, _ = studio
    assert client.get("/api/projects/..%2F..%2Fetc/publishing").status_code == 404
    assert client.get("/api/projects/missing/publishing").status_code == 404
    bad = client.post("/api/projects/book/publishing/export", json={"revision": 3})
    assert bad.status_code == 422
    extra = client.post(
        "/api/projects/book/publishing/export",
        json={"revision": "x", "path": "C:/Windows"},
    )
    assert extra.status_code == 422
    foreign = client.post(
        "/api/projects/book/publishing/export",
        json={"revision": detail(client)["revision"]},
        headers={"origin": "https://example.com"},
    )
    assert foreign.status_code == 403
    text = client.post(
        "/api/projects/book/publishing/export",
        content=b"revision",
        headers={"content-type": "text/plain"},
    )
    assert text.status_code == 403


def test_status_cache_follows_artifact_bytes(studio):
    client, _, output = studio
    build_all(client)
    first = status(client)
    assert status(client) == first
    pdf = output / "cover.pdf"
    pdf.write_bytes(pdf.read_bytes() + b"\n")
    after = status(client)
    assert after["readiness"]["verdicts"]["cover"]["structural"] == "invalid"
    digest = hashlib.sha256(pdf.read_bytes()).hexdigest()
    assert after["readiness"]["artifacts"]["cover_pdf"]["sha256"] == digest
