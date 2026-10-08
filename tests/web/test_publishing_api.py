"""Publishing API: status, draft metadata checks, saves, revision-checked export."""

import hashlib

import pytest
from fastapi.testclient import TestClient

from puzzlepress import load_project
from puzzlepress.publishing import evaluate_readiness
from puzzlepress.studio.server import create_app
from tests.cover_helpers import cover_project
from tests.publishing_helpers import complete_section, confirm_current


def _output(data):
    data["output"] = {"directory": "../../build/book"}
    data["book"]["imprint"] = None


@pytest.fixture
def studio(tmp_path):
    books = tmp_path / "books"
    source, _ = cover_project(books, mutate=_output, build_interior=False, puzzles=16)
    client = TestClient(create_app(books, tmp_path / "frontend"))
    return client, source, tmp_path / "build" / "book"


def with_section(project, **overrides):
    """The project with a complete publishing section, confirmed as it is (synthetic)."""
    project["publishing"] = complete_section(**overrides)
    return confirm_current(project)


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
    with_section(project, keywords=["a"] * 2 + ["b"] * 7)
    data = client.post("/api/projects/book/draft/publishing", json={"source": project}).json()
    findings = data["metadata"]["findings"]
    assert {f["code"] for f in findings} >= {"keywords_count", "keywords_format"}
    assert any(f["field"] == "publishing.keywords.1" for f in findings)
    assert (source / "book.yaml").read_bytes() == before
    project["publishing"]["version"] = 3
    invalid = client.post("/api/projects/book/draft/publishing", json={"source": project})
    assert invalid.status_code == 422
    assert invalid.json()["error"]["issues"][0]["path"] == "publishing.version"


def test_saving_metadata_keeps_the_interior_current(studio):
    client, _, _ = studio
    build_all(client)
    project = detail(client)["source"]
    with_section(project)
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
    with_section(project)
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
    data = status(client)
    assert data["package"]["export"]["state"] == "stale"
    assert data["readiness"]["verdicts"]["attestations"] == "incomplete"  # Review again.


def draft(client, project):
    response = client.post("/api/projects/book/draft/publishing", json={"source": project})
    assert response.status_code == 200
    return response.json()


def test_confirming_through_the_draft_check_save_and_reload(studio):
    """The browser copies Python's review identity; Python decides whether it applies."""
    client, source, _ = studio
    build_all(client)
    project = detail(client)["source"]
    with_section(project, attestations={})
    checked = draft(client, project)
    assert checked["upgrade"] is None
    rows = {c["name"]: c for c in checked["metadata"]["confirmations"]}
    assert {n: (c["state"], c["required"]) for n, c in rows.items()} == {
        "rights": ("unconfirmed", True),
        "ai_disclosure": ("unconfirmed", True),
        "metadata": ("unconfirmed", True),
        "isbn": ("unconfirmed", False),
    }
    for name in ("rights", "ai_disclosure", "metadata"):
        project["publishing"]["attestations"][name] = rows[name]["current"]
    checked = draft(client, project)
    assert checked["metadata"]["verdicts"]["attestations"] == "complete"
    # Editing the description asks for review of what covers it, not of rights.
    project["publishing"]["description"] += " Large print."
    after = {c["name"]: c["state"] for c in draft(client, project)["metadata"]["confirmations"]}
    assert after == {
        "rights": "confirmed",
        "ai_disclosure": "stale",
        "metadata": "stale",
        "isbn": "unconfirmed",
    }
    current = {c["name"]: c["current"] for c in draft(client, project)["metadata"]["confirmations"]}
    for name in ("ai_disclosure", "metadata"):
        project["publishing"]["attestations"][name] = current[name]
    revision = detail(client)["revision"]
    assert save(client, project).status_code == 200
    reloaded = detail(client)
    assert reloaded["revision"] != revision
    assert reloaded["source"]["publishing"]["attestations"] == project["publishing"]["attestations"]
    readiness = status(client)["readiness"]
    assert readiness["verdicts"]["package"] == "ready"
    assert {c["state"] for c in readiness["confirmations"] if c["required"]} == {"confirmed"}
    # Studio and the CLI share one evaluator: the saved draft checks equal validate's report.
    from puzzlepress.publishing import validate_metadata

    cli = validate_metadata(load_project(source).project).to_dict()
    assert draft(client, reloaded["source"])["metadata"] == cli
    # A save against the earlier revision is rejected; the file keeps the confirmations.
    stale = client.post(
        "/api/projects/book/draft/save", json={"source": project, "revision": revision}
    )
    assert stale.status_code == 409 and stale.json()["error"]["code"] == "source_changed"
    assert detail(client)["revision"] == reloaded["revision"]


def test_version_1_sections_are_offered_an_upgrade_and_never_count(studio):
    client, _, _ = studio
    project = detail(client)["source"]
    project["publishing"] = complete_section(
        version=1, attestations={"rights": True, "ai_disclosure": True, "metadata": True}
    )
    checked = draft(client, project)
    states = {c["name"]: c["state"] for c in checked["metadata"]["confirmations"]}
    assert states == {
        "rights": "legacy",
        "ai_disclosure": "legacy",
        "metadata": "legacy",
        "isbn": "unconfirmed",
    }
    assert checked["metadata"]["verdicts"]["attestations"] == "incomplete"
    upgrade = checked["upgrade"]
    assert upgrade["version"] == 2
    assert upgrade["attestations"] == dict.fromkeys(("rights", "ai_disclosure", "metadata", "isbn"))
    assert {k: v for k, v in upgrade.items() if k not in ("version", "attestations")} == {
        k: v for k, v in project["publishing"].items() if k not in ("version", "attestations")
    }
    # A legacy section still saves exactly as written; adopting the upgrade saves too.
    assert save(client, project).status_code == 200
    assert detail(client)["source"]["publishing"]["attestations"]["rights"] is True
    project = detail(client)["source"]
    project["publishing"] = upgrade
    assert save(client, project).status_code == 200
    assert draft(client, detail(client)["source"])["upgrade"] is None


def test_export_failure_returns_findings_and_writes_nothing(studio):
    client, _, output = studio
    build_all(client)
    project = detail(client)["source"]
    with_section(project, attestations={})
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
    with_section(project)
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
