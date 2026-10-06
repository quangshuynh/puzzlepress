"""Serve disposable project copies for browser acceptance, never authored books."""

import shutil
import tempfile
from pathlib import Path

import uvicorn

from puzzlepress.studio.server import create_app

ROOT = Path(__file__).resolve().parents[2]

with tempfile.TemporaryDirectory(prefix="puzzlepress-browser-") as directory:
    books = Path(directory) / "books"
    for key in ("garden-demo", "automotive", "composition-demo"):
        target = books / key
        target.mkdir(parents=True)
        shutil.copyfile(ROOT / "books" / key / "book.yaml", target / "book.yaml")
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
    uvicorn.run(create_app(books, ROOT / "studio/dist"), host="127.0.0.1", port=8015)
