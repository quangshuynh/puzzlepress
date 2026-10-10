"""Serve disposable project copies for browser acceptance, never authored books."""

import shutil
import sys
import tempfile
from pathlib import Path

import uvicorn

from puzzlepress.studio.server import create_app

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tests"))

from planning_helpers import complete_plan, document  # noqa: E402

from puzzlepress.planning import write_planning  # noqa: E402

with tempfile.TemporaryDirectory(prefix="puzzlepress-browser-") as directory:
    books = Path(directory) / "books"
    for key in ("garden-demo", "composition-demo"):
        target = books / key
        target.mkdir(parents=True)
        shutil.copyfile(ROOT / "books" / key / "book.yaml", target / "book.yaml")
    # Planning: the automotive demo with its plan, and a synthetic plan ready for approval.
    shutil.copytree(ROOT / "books" / "automotive", books / "automotive")
    target = books / "planning-ready"
    target.mkdir()
    (target / "book.yaml").write_text(
        (ROOT / "tests/fixtures/legacy-automotive/book.yaml")
        .read_text(encoding="utf-8")
        .replace("Automotive Word Search", "Planning Acceptance Book"),
        encoding="utf-8",
    )
    write_planning(target, document(complete_plan()), None)  # SYNTHETIC test plan.
    target = books / "editor-demo"
    target.mkdir()
    shutil.copyfile(ROOT / "books/garden-demo/book.yaml", target / "book.yaml")
    source = target / "book.yaml"
    source.write_text(
        source.read_text(encoding="utf-8").replace(
            "Garden Word Searches", "Editor acceptance project"
        ),
        encoding="utf-8",
    )
    target = books / "composer-demo"
    target.mkdir()
    shutil.copyfile(ROOT / "books/composition-demo/book.yaml", target / "book.yaml")
    # Print builds write only inside this temporary directory, never to build/.
    target = books / "print-demo"
    target.mkdir()
    source = (ROOT / "books/composition-demo/book.yaml").read_text(encoding="utf-8")
    (target / "book.yaml").write_text(
        source.replace("../../build/composition-demo", "../../build/print-demo"), encoding="utf-8"
    )
    # Cover Studio: the cover demo with its photograph, and a book without a cover.
    shutil.copytree(ROOT / "books/cover-demo", books / "cover-demo")
    target = books / "cover-start"
    target.mkdir()
    (target / "book.yaml").write_text(
        source.replace("../../build/composition-demo", "../../build/cover-start"), encoding="utf-8"
    )
    # Publishing: the publishing demo, and a second copy for a stale-cover case.
    shutil.copytree(ROOT / "books/publishing-demo", books / "publishing-demo")
    shutil.copytree(ROOT / "books/publishing-demo", books / "publishing-stale")
    source = books / "publishing-stale" / "book.yaml"
    source.write_text(
        source.read_text(encoding="utf-8").replace(
            "../../build/publishing-demo", "../../build/publishing-stale"
        ),
        encoding="utf-8",
    )
    uvicorn.run(create_app(books, ROOT / "studio/dist"), host="127.0.0.1", port=8015)
