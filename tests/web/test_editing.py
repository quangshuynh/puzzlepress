"""Every mutation uses an isolated temporary project, never repository sources."""

import hashlib
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from puzzlepress import dump_project, load_project, validate_project
from puzzlepress.studio import editing
from puzzlepress.studio.editing import DraftStore
from puzzlepress.studio.server import create_app
from puzzlepress.studio.service import ProjectStore, StudioError


@pytest.fixture
def setup(tmp_path, garden):
    books = tmp_path / "books"
    source = books / "draft" / "book.yaml"
    source.parent.mkdir(parents=True)
    source.write_text("# Authored comment\n" + dump_project(garden), encoding="utf-8")
    client = TestClient(create_app(books, tmp_path / "frontend"))
    detail = client.get("/api/projects/draft").json()
    return client, source, detail


def post(setup, operation, source=None):
    client, _, detail = setup
    return client.post(
        f"/api/projects/draft/draft/{operation}",
        json={
            "source": source if source is not None else detail["source"],
            **({"revision": detail["revision"]} if operation == "save" else {}),
        },
    )


def test_validate_preview_are_deterministic_and_do_not_write(setup):
    _, source, detail = setup
    before = source.read_bytes()
    detail["source"]["word_search"]["puzzles"][0]["title"] = "Draft flowers"
    assert post(setup, "validate").json()["validation"]["valid"]
    a = post(setup, "preview").json()
    assert a == post(setup, "preview").json()
    assert a["report"]["puzzles"][0]["title"] == "Draft flowers"
    assert a["verification"]["flowers"]["valid"]
    assert isinstance(a["report"]["puzzles"][0]["seed"], str)
    detail["source"]["word_search"]["puzzles"].reverse()
    b = post(setup, "preview").json()
    assert a["report"]["puzzles"][0] == b["report"]["puzzles"][1]
    assert source.read_bytes() == before
    assert list(source.parent.iterdir()) == [source]


def test_save_canonicalizes_then_reloads_exact_authoritative_state(setup):
    client, source, detail = setup
    detail["source"]["build"]["seed"] = " 00018446744073709551615 "
    detail["source"]["word_search"]["puzzles"][0]["title"] = "  Draft flowers  "
    response = post(setup, "save")
    assert response.status_code == 200
    saved = response.json()
    assert saved == client.get("/api/projects/draft").json()
    assert saved["source"]["build"]["seed"] == "18446744073709551615"
    assert saved["source"]["word_search"]["puzzles"][0]["title"] == "Draft flowers"
    assert saved["revision"] == "sha256-" + hashlib.sha256(source.read_bytes()).hexdigest()
    assert saved["revision"] != detail["revision"]
    assert source.read_bytes() == dump_project(load_project(source).project).encode()
    assert b"# Authored comment" not in source.read_bytes()
    assert b"subtitle: null" in source.read_bytes()
    detail.update(saved)
    before = source.read_bytes()
    assert post(setup, "save").json() == saved
    assert source.read_bytes() == before


@pytest.mark.parametrize("operation", ["validate", "preview", "save"])
@pytest.mark.parametrize("fault", ["duplicate", "character", "reference", "output", "unknown"])
def test_invalid_drafts_rejected_without_writes(setup, operation, fault):
    _, source, detail = setup
    before = source.read_bytes()
    draft = detail["source"]
    bank = draft["word_search"]["banks"][0]
    if fault == "duplicate":
        bank["entries"][1]["display"] = bank["entries"][0]["display"]
    elif fault == "character":
        bank["entries"][0]["display"] = "CAFÉ!"
    elif fault == "reference":
        draft["word_search"]["puzzles"][0]["bank"] = "missing"
    elif fault == "output":
        draft["output"]["directory"] = "generated"
    else:
        draft["invented"] = True
    response = post(setup, operation)
    assert response.status_code == 422
    assert response.json()["error"]["issues"]
    assert source.read_bytes() == before
    assert list(source.parent.iterdir()) == [source]


@pytest.mark.parametrize("external", ["comment", "invalid", "semantic", "output"])
def test_stale_revision_never_overwrites_external_source(setup, external):
    _, source, detail = setup
    if external == "comment":
        source.write_bytes(source.read_bytes() + b"\n# external edit\n")
    elif external == "invalid":
        source.write_text("not: a valid project")
    else:
        raw = load_project(source).project.to_dict()
        if external == "semantic":
            raw["book"]["title"] = "External"
        else:
            raw["output"]["directory"] = "../../other-output"
        source.write_text(dump_project(validate_project(raw).require_project()))
    before = source.read_bytes()
    response = post(setup, "save")
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "source_changed"
    assert source.read_bytes() == before


@pytest.mark.parametrize("failure", ["replace", "fsync", "serialize"])
def test_failed_staging_preserves_original_and_cleans_temporary(setup, monkeypatch, failure):
    _, source, _ = setup
    before = source.read_bytes()

    def fail(*args, **kwargs):
        raise OSError("private filesystem diagnostic")

    if failure == "serialize":
        monkeypatch.setattr(editing, "dump_project", fail)
    else:
        monkeypatch.setattr(editing.os, failure, fail)
    response = post(setup, "save")
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "save_failed"
    assert "private filesystem" not in response.text
    assert source.read_bytes() == before
    assert list(source.parent.iterdir()) == [source]


def test_rechecks_revision_after_staging(setup, monkeypatch):
    _, source, _ = setup
    real_dump = editing.dump_project

    def concurrent_edit(project):
        source.write_bytes(source.read_bytes() + b"# competing editor\n")
        return real_dump(project)

    monkeypatch.setattr(editing, "dump_project", concurrent_edit)
    assert post(setup, "save").status_code == 409
    assert source.read_bytes().endswith(b"# competing editor\n")
    assert list(source.parent.iterdir()) == [source]


def test_concurrent_saves_accept_only_one_revision(setup):
    _, source, detail = setup
    draft = detail["source"]
    draft["book"]["title"] = "New title"
    stores = [DraftStore(ProjectStore(source.parent.parent)) for _ in range(2)]

    def save(store):
        try:
            store.save("draft", draft, detail["revision"])
            return 200
        except StudioError as error:
            return error.status

    with ThreadPoolExecutor(2) as pool:
        assert sorted(pool.map(save, stores)) == [200, 409]
    assert load_project(source).project.book.title == "New title"


def test_draft_failure_and_quality_are_separate_from_save_validity(setup):
    _, _, detail = setup
    ws = detail["source"]["word_search"]
    ws["profiles"][0]["max_attempts"] = 1
    ws["quality"]["prohibited_words"] = ["MINT"]
    preview = post(setup, "preview").json()
    assert not preview["report"]["success"]
    assert preview["report"]["puzzles"][0]["errors"][0]["code"] == "search_exhausted"
    assert any(f["code"] == "prohibited_word" for f in preview["report"]["findings"])
    assert post(setup, "save").status_code == 200


@pytest.mark.parametrize("key", ["../outside", "..", "a/b", "a\\b", "C:drive"])
def test_write_path_traversal_rejected(setup, key):
    _, source, detail = setup
    with pytest.raises(StudioError):
        DraftStore(ProjectStore(source.parent.parent)).save(
            key, detail["source"], detail["revision"]
        )


def test_save_boundary_and_deleted_source(setup):
    client, source, detail = setup
    url = "/api/projects/draft/draft/save"
    assert client.post(url, json={"source": detail["source"]}).status_code == 422
    assert client.post(url, content="source=x").status_code == 403
    assert (
        client.post(url, json=detail, headers={"Origin": "https://outside.test"}).status_code == 403
    )
    source.unlink()
    assert post(setup, "save").status_code == 404
    assert not source.exists()


def test_boundary_rechecked_after_staging(setup, monkeypatch):
    _, source, detail = setup
    before = source.read_bytes()
    real_source = ProjectStore.source
    count = 0

    def moved(store, key):
        nonlocal count
        count += 1
        return source.parent.parent / "outside.yaml" if count == 3 else real_source(store, key)

    monkeypatch.setattr(ProjectStore, "source", moved)
    assert post(setup, "save").status_code == 409
    assert source.read_bytes() == before


def test_repository_fixture_bytes_unchanged():
    root = Path(__file__).resolve().parents[2]
    for key, expected in {
        "garden-demo": "ffd7f7eb02c5d88f1f3e4880a505e140d60562cb113973fc448aeaabcffac540",
        "automotive": "209f3fd646b2bf5cfd97f646c2c7868ba376edf9e11bf262bb09a02a5f3759e0",
    }.items():
        # CRLF and LF checkouts must agree; bytes are also checked in browser tests.
        raw = (root / "books" / key / "book.yaml").read_bytes().replace(b"\r\n", b"\n")
        assert hashlib.sha256(raw).hexdigest() == expected


def test_post_replace_reload_failure_is_explicit(setup, monkeypatch):
    _, source, detail = setup
    detail["source"]["book"]["title"] = "Persisted but unconfirmed"

    def failed_snapshot(*args):
        raise StudioError(503, "source_unavailable", "private path")

    monkeypatch.setattr(ProjectStore, "snapshot", failed_snapshot)
    response = post(setup, "save")
    assert response.status_code == 503
    assert response.json()["error"]["code"] == "save_unconfirmed"
    assert "private path" not in response.text
    assert load_project(source).project.book.title == "Persisted but unconfirmed"


def test_corrupt_staged_serialization_never_replaces_source(setup, monkeypatch):
    _, source, _ = setup
    before = source.read_bytes()
    monkeypatch.setattr(editing, "dump_project", lambda project: "invalid: source")
    assert post(setup, "save").status_code == 422
    assert source.read_bytes() == before
    assert list(source.parent.iterdir()) == [source]


def test_symlink_write_rejected(setup, tmp_path):
    _, source, detail = setup
    outside = tmp_path / "outside.yaml"
    outside.write_bytes(source.read_bytes())
    before = outside.read_bytes()
    link = source.parent.parent / "linked"
    link.mkdir()
    try:
        (link / "book.yaml").symlink_to(outside)
    except OSError:
        pytest.skip("Creating symlinks requires OS permission on this host")
    with pytest.raises(StudioError):
        DraftStore(ProjectStore(source.parent.parent)).save(
            "linked", detail["source"], detail["revision"]
        )
    assert outside.read_bytes() == before
