"""Plan versus production book: an auditable, read-only comparison."""

import copy
import json
import os
import subprocess
from pathlib import Path

import pytest
from planning_helpers import AUTOMOTIVE, LEGACY

from puzzlepress import build_identity, load_project, validate_project
from puzzlepress.cli import main
from puzzlepress.models import Project
from puzzlepress.planning import (
    ProductionUnavailable,
    comparison_bytes,
    comparison_document,
    evaluate_plan,
    read_planning,
)
from tests.helpers import installed_puzzlepress

PLAN = read_planning(AUTOMOTIVE).document
assert PLAN is not None
BOOK = load_project(AUTOMOTIVE).project


def compare(project: Project = BOOK) -> dict:
    assert PLAN is not None
    return comparison_document(evaluate_plan(project, PLAN))


def variant(mutate) -> Project:  # type: ignore[no-untyped-def]
    data = copy.deepcopy(BOOK.to_dict())
    mutate(data)
    return validate_project(data).require_project()


def codes(document: dict) -> list[str]:
    return [d["code"] for d in document["deviations"]]


def test_production_book_matches_its_plan_without_claiming_approval() -> None:
    doc = compare()
    assert doc["matches_plan"] is True and doc["deviations"] == []
    assert doc["counts"] == {"target": 60, "planned": 60, "produced": 60}
    assert doc["planning"]["state"] == "needs_research"
    assert doc["planning"]["approved"] is False
    assert doc["planning"]["approval"] == {"status": "none", "approved_identity": None,
                                          "counts": False}  # fmt: skip
    assert doc["production"]["identity"] == build_identity(BOOK)
    assert {row["theme"]: row["produced"] for row in doc["themes"]} == {
        "engines": 10, "maintenance": 10, "tools": 8, "systems": 10, "motorsport": 8,
        "history": 6, "driving": 8,
    }  # fmt: skip
    assert [r["produced_puzzles"] for r in doc["levels"]] == [20, 20, 20]
    assert [r["produced_words"] for r in doc["levels"]] == [
        {"min": 10, "max": 11}, {"min": 13, "max": 14}, {"min": 16, "max": 16}
    ]  # fmt: skip
    vocabulary = doc["vocabulary"]
    # Every placed word is AI-generated, and stays recorded as such.
    assert vocabulary["words_by_source"]["ai_generated"] == vocabulary["produced_words"] == 793
    assert sum(vocabulary["words_by_source"].values()) == 793
    assert vocabulary["distinct_produced_words"] == 787
    assert [q["id"] for q in doc["open_questions"]] == ["q-comparables", "q-vocabulary-review"]
    assert any("split across banks" in note for note in doc["notes"])


@pytest.mark.parametrize(
    ("mutate", "expected"),
    [
        (lambda d: d["word_search"]["puzzles"][0].update(title="Changed"), ["title_differs"]),
        (lambda d: d["word_search"]["puzzles"][0].update(difficulty="standard"), ["level_differs"]),
        (lambda d: d["word_search"]["puzzles"][0]["target_ids"].reverse(), ["words_differ"]),
        (
            lambda d: d["word_search"]["puzzles"].insert(1, d["word_search"]["puzzles"].pop(2)),
            ["order_differs"],
        ),
        (
            lambda d: d["word_search"]["puzzles"].pop(),
            ["puzzle_count_differs", "puzzle_missing", "allocation_differs"],
        ),
        (lambda d: d["word_search"]["profiles"][0].update(width=14), ["profile_differs"]),
        (lambda d: d["composition"]["solutions"].update(per_page=4), ["structure_differs"]),
    ],
)
def test_each_deviation_is_reported(mutate, expected) -> None:  # type: ignore[no-untyped-def]
    doc = compare(variant(mutate))
    assert doc["matches_plan"] is False
    assert sorted(set(codes(doc))) == sorted(expected)


def test_unplanned_words_and_puzzles_are_attributed() -> None:
    def mutate(data: dict) -> None:
        bank = data["word_search"]["banks"][0]
        bank["entries"].append({"id": "sprocket", "display": "SPROCKET"})
        data["word_search"]["puzzles"][0]["target_ids"].append("sprocket")
        extra = copy.deepcopy(data["word_search"]["puzzles"][1])
        extra["id"] = "extra-01"
        data["word_search"]["puzzles"].append(extra)

    doc = compare(variant(mutate))
    found = {(d["code"], d["subject"]) for d in doc["deviations"]}
    assert ("word_outside_pool", "engines-01") in found
    assert ("words_differ", "engines-01") in found
    assert ("puzzle_unplanned", "extra-01") in found
    assert ("puzzle_count_differs", None) in found
    # Words of an unplanned puzzle and words outside any pool have unknown provenance.
    assert doc["vocabulary"]["words_by_source"]["unknown"] == 1 + 10


def test_a_project_without_production_content_has_nothing_to_compare() -> None:
    legacy = load_project(LEGACY).project
    assert PLAN is not None
    with pytest.raises(ProductionUnavailable):
        comparison_document(evaluate_plan(legacy, PLAN))


def test_cli_prints_the_comparison_and_writes_nothing(
    capsysbinary: pytest.CaptureFixture[bytes], tmp_path: Path
) -> None:
    before = {p.name: p.read_bytes() for p in AUTOMOTIVE.iterdir()}
    assert main(["plan", "production", str(AUTOMOTIVE)]) == 0
    out = capsysbinary.readouterr().out
    assert b"does not follow an approved plan" in out and b"Deviations: 0" in out
    assert main(["plan", "production", str(AUTOMOTIVE), "--json"]) == 0
    assert PLAN is not None
    assert capsysbinary.readouterr().out == comparison_bytes(evaluate_plan(BOOK, PLAN))
    assert {p.name: p.read_bytes() for p in AUTOMOTIVE.iterdir()} == before
    # A deviating copy exits 1; a project without a plan or production content too.
    book = tmp_path / "books" / "automotive"
    book.mkdir(parents=True)
    (book / "planning.yaml").write_bytes((AUTOMOTIVE / "planning.yaml").read_bytes())
    source = (AUTOMOTIVE / "book.yaml").read_text(encoding="utf-8")
    (book / "book.yaml").write_text(source.replace("title: Under the Hood", "title: Changed"),
                                    encoding="utf-8")  # fmt: skip
    assert main(["plan", "production", str(book)]) == 1
    assert b"title_differs [engines-01]" in capsysbinary.readouterr().out
    (book / "book.yaml").write_bytes((LEGACY / "book.yaml").read_bytes())
    assert main(["plan", "production", str(book)]) == 1
    assert b"no word_search section" in capsysbinary.readouterr().err


def test_installed_cli_comparison_bytes_are_stable(tmp_path: Path) -> None:
    outputs = set()
    for cwd, seed in ((tmp_path, "0"), (AUTOMOTIVE.parent, "4242")):
        result = subprocess.run(
            [str(installed_puzzlepress()), "plan", "production", str(AUTOMOTIVE), "--json"],
            capture_output=True, cwd=cwd, env={**os.environ, "PYTHONHASHSEED": seed},
        )  # fmt: skip
        assert result.returncode == 0, result.stderr
        outputs.add(result.stdout)
    assert len(outputs) == 1
    assert json.loads(outputs.pop())["comparison_version"] == 1
    assert list(tmp_path.iterdir()) == []
