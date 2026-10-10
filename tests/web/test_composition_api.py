"""Composition through Studio's existing draft/save contract, on temporary copies only."""

import hashlib
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from puzzlepress import build_identity, dump_project, load_project
from puzzlepress.publication import build_publication
from puzzlepress.studio.server import create_app
from puzzlepress.studio.service import ProjectStore, StudioError, StudioService

ROOT = Path(__file__).resolve().parents[2]
FIXTURES = {
    "books/garden-demo": "ffd7f7eb02c5d88f1f3e4880a505e140d60562cb113973fc448aeaabcffac540",
    "tests/fixtures/legacy-automotive": (
        "209f3fd646b2bf5cfd97f646c2c7868ba376edf9e11bf262bb09a02a5f3759e0"
    ),
    "books/composition-demo": "b15651cddf6ae73c7ce5da8df967b64cb952dd0ca2f6d15b4684905db85330c7",
}


def fixture_hashes():
    return {
        key: hashlib.sha256(
            (ROOT / key / "book.yaml").read_bytes().replace(b"\r\n", b"\n")
        ).hexdigest()
        for key in FIXTURES
    }


@pytest.fixture(autouse=True)
def repository_fixtures_unchanged():
    assert fixture_hashes() == FIXTURES
    yield
    assert fixture_hashes() == FIXTURES


@pytest.fixture
def demo():
    return load_project(ROOT / "books" / "composition-demo").project


@pytest.fixture
def setup(tmp_path, demo, garden):
    books = tmp_path / "books"
    for key, project in (("book", demo), ("legacy", garden)):
        (books / key).mkdir(parents=True)
        (books / key / "book.yaml").write_text(dump_project(project), encoding="utf-8")
    return TestClient(create_app(books, tmp_path / "frontend")), books


def detail(client, key="book"):
    return client.get(f"/api/projects/{key}").json()


def post(client, operation, source, key="book", revision=None):
    body: dict[str, object] = {"source": source}
    if revision is not None:
        body["revision"] = revision
    return client.post(f"/api/projects/{key}/draft/{operation}", json=body)


def test_detail_exposes_normalized_composition(setup, demo):
    client, _ = setup
    data = detail(client)
    assert data["source"]["composition"] == demo.composition.to_dict()
    assert "composition" not in detail(client, "legacy")["source"]


def test_unsaved_plan_preview_is_deterministic_authoritative_and_read_only(setup, demo):
    client, books = setup
    source_path = books / "book" / "book.yaml"
    before = source_path.read_bytes()
    source = detail(client)["source"]
    first = post(client, "plan", source)
    assert first.status_code == 200
    assert first.json() == post(client, "plan", source).json()
    report, plan = build_publication(demo)
    payload = first.json()
    assert payload["plan"]["pages"] == [page.to_dict() for page in plan.pages]
    assert payload["plan"]["statistics"]["logical_pages"] == 11
    assert payload["verification"] == {"valid": True, "issues": []}
    assert payload["generation"]["success"]

    source["word_search"]["puzzles"].reverse()
    source["composition"]["solutions"]["per_page"] = 4
    source["composition"]["front_matter"][2]["title"] = "Draft instructions"
    draft = post(client, "plan", source).json()["plan"]
    puzzles = [p["puzzle"]["id"] for p in draft["pages"] if p["puzzle"]]
    assert puzzles == ["dunes", "harbour", "rockpool", "shoreline"]
    assert draft["statistics"]["solution_pages"] == 1
    assert draft["pages"][2]["matter"]["title"] == "Draft instructions"
    assert draft["identity"] != payload["plan"]["identity"]
    assert source_path.read_bytes() == before
    assert sorted(p.name for p in source_path.parent.iterdir()) == ["book.yaml"]


@pytest.mark.parametrize("operation", ["validate", "plan", "save"])
def test_invalid_composition_rejected_with_field_paths_and_no_write(setup, operation):
    client, books = setup
    before = (books / "book" / "book.yaml").read_bytes()
    data = detail(client)
    source = data["source"]
    source["composition"]["solutions"]["per_page"] = 3
    source["composition"]["front_matter"].append({"kind": "title_page"})
    revision = data["revision"] if operation == "save" else None
    response = post(client, operation, source, revision=revision)
    assert response.status_code == 422
    error = response.json()["error"]
    assert error["code"] == "invalid_project"
    assert {(i["path"], i["code"]) for i in error["issues"]} >= {
        ("composition.solutions.per_page", "choice"),
        ("composition.front_matter", "count"),
    }
    assert (books / "book" / "book.yaml").read_bytes() == before


def test_plan_requires_composition(setup):
    client, _ = setup
    response = post(client, "plan", detail(client, "legacy")["source"], key="legacy")
    assert response.status_code == 422
    assert response.json()["error"]["code"] == "no_composition"


def test_save_reload_preserves_semantic_composition_and_plan(setup):
    client, books = setup
    data = detail(client)
    source = data["source"]
    source["word_search"]["puzzles"].insert(0, source["word_search"]["puzzles"].pop())
    source["composition"]["front_matter"][1]["text"] = "  Edited notice.\nSecond line.  "
    source["composition"]["page_numbers"]["show_front_matter"] = True
    preview = post(client, "plan", source).json()
    saved = post(client, "save", source, revision=data["revision"])
    assert saved.status_code == 200
    reloaded = detail(client)
    assert saved.json() == reloaded
    assert reloaded["revision"] != data["revision"]
    composition = reloaded["source"]["composition"]
    assert composition["front_matter"][1]["text"] == "Edited notice.\nSecond line."
    assert composition["page_numbers"]["show_front_matter"] is True
    assert reloaded["source"]["word_search"]["puzzles"][0]["id"] == "dunes"
    after = post(client, "plan", reloaded["source"]).json()
    assert after == preview
    assert load_project(books / "book").project.composition is not None
    resaved = post(client, "save", reloaded["source"], revision=reloaded["revision"])
    assert resaved.json()["revision"] == reloaded["revision"]


def test_stale_composition_save_is_rejected_and_draft_unaffected(setup):
    client, books = setup
    data = detail(client)
    first = data["source"]
    first["composition"]["solutions"]["title"] = "Answers"
    assert post(client, "save", first, revision=data["revision"]).status_code == 200
    current = (books / "book" / "book.yaml").read_bytes()
    stale = detail(client)["source"]
    stale["composition"]["solutions"] = {"placement": "omit"}
    response = post(client, "save", stale, revision=data["revision"])
    assert response.status_code == 409
    assert response.json()["error"]["code"] == "source_changed"
    assert (books / "book" / "book.yaml").read_bytes() == current


def test_legacy_project_can_explicitly_add_composition(setup):
    client, _ = setup
    data = detail(client, "legacy")
    source = data["source"]
    source["composition"] = {"solutions": {"placement": "end", "title": "Solutions"}}
    saved = post(client, "save", source, key="legacy", revision=data["revision"])
    assert saved.status_code == 200
    body = saved.json()
    assert body["identity"] != data["identity"]
    assert body["source"]["composition"]["page_numbers"]["scheme"] == "continuous"
    plan = post(client, "plan", body["source"], key="legacy").json()["plan"]
    assert [p["kind"] for p in plan["pages"]] == ["puzzle", "puzzle", "solutions", "solutions"]


@pytest.mark.parametrize("key", ["..", "..%2Fbook", "a%5Cb", "%2e%2e"])
def test_plan_path_safety(setup, key):
    client, _ = setup
    source = detail(client)["source"]
    response = client.post(f"/api/projects/{key}/draft/plan", json={"source": source})
    assert response.status_code == 404


def test_plan_shares_generation_lock(setup, demo):
    _, books = setup
    service = StudioService(ProjectStore(books))
    with service._generation_lock, pytest.raises(StudioError) as error:
        service.plan_project(demo)
    assert error.value.code == "generation_busy"
    assert service.plan_project(demo)["plan"]["identity"] == build_identity(demo)
