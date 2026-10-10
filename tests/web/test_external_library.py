"""Books kept outside the engine checkout, as in a separate book repository.

The layout mirrors puzzlepress-books (`<repo>/books/<book>/book.yaml`, builds in
`<repo>/build/`) with the SYNTHETIC production book. Nothing here reads a real book.
"""

import subprocess
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from puzzlepress import load_project
from puzzlepress.studio import server
from puzzlepress.studio.server import create_app, default_frontend
from tests.helpers import ROOT, installed_puzzlepress
from tests.production_book import write_production_book


@pytest.fixture
def library(tmp_path: Path) -> Path:
    repository = tmp_path / "puzzlepress-books"
    write_production_book(repository / "books" / "production")
    return repository


def test_studio_opens_edits_and_saves_an_external_book(library: Path) -> None:
    books = library / "books"
    assert not books.resolve().is_relative_to(ROOT)
    client = TestClient(create_app(books, ROOT / "studio" / "dist"))
    listed = client.get("/api/projects").json()
    assert [p["key"] for p in listed["projects"]] == ["production"]
    detail = client.get("/api/projects/production").json()
    plan_before = (books / "production" / "planning.yaml").read_bytes()
    detail["source"]["word_search"]["puzzles"][0]["title"] = "Edited outside the engine"
    saved = client.post(
        "/api/projects/production/draft/save",
        json={"source": detail["source"], "revision": detail["revision"]},
    )
    assert saved.status_code == 200
    project = load_project(books / "production").project
    assert project.word_search is not None
    assert project.word_search.puzzles[0].title == "Edited outside the engine"
    assert (books / "production" / "planning.yaml").read_bytes() == plan_before
    stale = client.post(
        "/api/projects/production/draft/save",
        json={"source": detail["source"], "revision": detail["revision"]},
    )
    assert stale.status_code == 409
    for key in ("..", "%2e%2e", "production%2F..%2F.."):
        assert client.get(f"/api/projects/{key}").status_code in (400, 404, 422)


def test_cli_builds_an_external_book_from_another_directory(library: Path, tmp_path: Path) -> None:
    engine = tmp_path / "puzzlepress"  # A sibling working directory, like the engine checkout.
    engine.mkdir()
    relative = Path("..") / "puzzlepress-books" / "books" / "production"
    cli = str(installed_puzzlepress())
    build = subprocess.run([cli, "book", "build", str(relative)], cwd=engine, capture_output=True)
    assert build.returncode == 0, build.stderr
    # Output follows book.yaml (../../build/<id>), never the caller's directory.
    out = library / "build" / "synthetic-production-book"
    assert (out / "interior.pdf").is_file() and (out / "interior.json").is_file()
    assert list(engine.iterdir()) == []
    assert sorted(p.name for p in (library / "books" / "production").iterdir()) == [
        "book.yaml",
        "planning.yaml",
    ]
    preflight = subprocess.run(
        [cli, "book", "preflight", str(relative), "--no-write"], cwd=engine, capture_output=True
    )
    assert preflight.returncode == 0, preflight.stdout
    inspect = subprocess.run(
        [cli, "publish", "inspect", str(relative)], cwd=engine, capture_output=True
    )
    assert inspect.returncode == 1 and b"Cover: no_config" in inspect.stdout


def test_studio_finds_the_engine_frontend_from_any_directory(tmp_path, monkeypatch) -> None:  # type: ignore[no-untyped-def]
    frontend = default_frontend()
    built = ROOT / "studio" / "dist" / "index.html"
    assert frontend == (ROOT / "studio" / "dist" if built.is_file() else Path("studio/dist"))
    monkeypatch.chdir(tmp_path)
    with pytest.raises(SystemExit):
        server.main(["--books", str(tmp_path / "missing")])
