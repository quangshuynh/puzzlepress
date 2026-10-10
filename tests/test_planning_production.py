"""Plan versus production book: an auditable, read-only comparison."""

import copy
import json
import os
import subprocess
from pathlib import Path

import pytest
from planning_helpers import LEGACY

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


@pytest.fixture(scope="module")
def synthetic(tmp_path_factory):  # type: ignore[no-untyped-def]
    """The SYNTHETIC production book: (directory, project, plan)."""
    from production_book import write_production_book

    book = write_production_book(tmp_path_factory.mktemp("comparison") / "books" / "production")
    plan = read_planning(book).document
    assert plan is not None
    return book, load_project(book).project, plan


def compare(synthetic, project: Project | None = None) -> dict:  # type: ignore[no-untyped-def]
    _, book, plan = synthetic
    return comparison_document(evaluate_plan(project or book, plan))


def variant(synthetic, mutate) -> Project:  # type: ignore[no-untyped-def]
    data = copy.deepcopy(synthetic[1].to_dict())
    mutate(data)
    return validate_project(data).require_project()


def codes(document: dict) -> list[str]:
    return [d["code"] for d in document["deviations"]]


def test_production_book_matches_its_plan_without_claiming_approval(synthetic) -> None:  # type: ignore[no-untyped-def]
    doc = compare(synthetic)
    book = synthetic[1]
    assert doc["matches_plan"] is True and doc["deviations"] == []
    assert doc["counts"] == {"target": 60, "planned": 60, "produced": 60}
    assert doc["planning"]["state"] == "needs_research"
    assert doc["planning"]["approved"] is False
    assert doc["planning"]["approval"] == {"status": "none", "approved_identity": None,
                                          "counts": False}  # fmt: skip
    assert doc["production"]["identity"] == build_identity(book)
    assert {row["theme"]: row["produced"] for row in doc["themes"]} == {
        "north": 10, "east": 10, "south": 8, "west": 10, "high": 8, "low": 6, "coast": 8,
    }  # fmt: skip
    assert [r["produced_puzzles"] for r in doc["levels"]] == [20, 20, 20]
    assert [r["produced_words"] for r in doc["levels"]] == [
        {"min": 10, "max": 11}, {"min": 13, "max": 14}, {"min": 16, "max": 16}
    ]  # fmt: skip
    vocabulary = doc["vocabulary"]
    # Every placed word keeps the source the plan records for it.
    placed = vocabulary["produced_words"]
    assert vocabulary["words_by_source"]["ai_generated"] == placed == 798
    assert sum(vocabulary["words_by_source"].values()) == placed
    assert vocabulary["distinct_produced_words"] == 798
    assert [q["id"] for q in doc["open_questions"]] == ["q-comparables"]
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
def test_each_deviation_is_reported(synthetic, mutate, expected) -> None:  # type: ignore[no-untyped-def]
    doc = compare(synthetic, variant(synthetic, mutate))
    assert doc["matches_plan"] is False
    assert sorted(set(codes(doc))) == sorted(expected)


def test_unplanned_words_and_puzzles_are_attributed(synthetic) -> None:  # type: ignore[no-untyped-def]
    def mutate(data: dict) -> None:
        bank = data["word_search"]["banks"][0]
        bank["entries"].append({"id": "sprocket", "display": "SPROCKET"})
        data["word_search"]["puzzles"][0]["target_ids"].append("sprocket")
        extra = copy.deepcopy(data["word_search"]["puzzles"][1])
        extra["id"] = "extra-01"
        data["word_search"]["puzzles"].append(extra)

    doc = compare(synthetic, variant(synthetic, mutate))
    found = {(d["code"], d["subject"]) for d in doc["deviations"]}
    assert ("word_outside_pool", "north-01") in found
    assert ("words_differ", "north-01") in found
    assert ("puzzle_unplanned", "extra-01") in found
    assert ("puzzle_count_differs", None) in found
    # Words of an unplanned puzzle and words outside any pool have unknown provenance.
    copied = len(synthetic[1].word_search.puzzles[1].target_ids)
    assert doc["vocabulary"]["words_by_source"]["unknown"] == 1 + copied


def test_a_project_without_production_content_has_nothing_to_compare(synthetic) -> None:  # type: ignore[no-untyped-def]
    legacy = load_project(LEGACY).project
    with pytest.raises(ProductionUnavailable):
        comparison_document(evaluate_plan(legacy, synthetic[2]))


def test_cli_prints_the_comparison_and_writes_nothing(
    capsysbinary: pytest.CaptureFixture[bytes], tmp_path: Path, synthetic
) -> None:  # type: ignore[no-untyped-def]
    book_dir, project, plan = synthetic
    before = {p.name: p.read_bytes() for p in book_dir.iterdir()}
    assert main(["plan", "production", str(book_dir)]) == 0
    out = capsysbinary.readouterr().out
    assert b"does not follow an approved plan" in out and b"Deviations: 0" in out
    assert main(["plan", "production", str(book_dir), "--json"]) == 0
    assert capsysbinary.readouterr().out == comparison_bytes(evaluate_plan(project, plan))
    assert {p.name: p.read_bytes() for p in book_dir.iterdir()} == before
    # A deviating copy exits 1; a project without a plan or production content too.
    book = tmp_path / "books" / "copy"
    book.mkdir(parents=True)
    (book / "planning.yaml").write_bytes((book_dir / "planning.yaml").read_bytes())
    source = (book_dir / "book.yaml").read_text(encoding="utf-8")
    (book / "book.yaml").write_text(source.replace("title: Northern Warm-up 1", "title: Changed"),
                                    encoding="utf-8")  # fmt: skip
    assert main(["plan", "production", str(book)]) == 1
    assert b"title_differs [north-01]" in capsysbinary.readouterr().out
    (book / "book.yaml").write_bytes((LEGACY / "book.yaml").read_bytes())
    assert main(["plan", "production", str(book)]) == 1
    assert b"no word_search section" in capsysbinary.readouterr().err


def test_installed_cli_comparison_bytes_are_stable(tmp_path: Path, synthetic) -> None:  # type: ignore[no-untyped-def]
    book_dir = synthetic[0]
    outputs = set()
    for cwd, seed in ((tmp_path, "0"), (book_dir.parent, "4242")):
        result = subprocess.run(
            [str(installed_puzzlepress()), "plan", "production", str(book_dir), "--json"],
            capture_output=True, cwd=cwd, env={**os.environ, "PYTHONHASHSEED": seed},
        )  # fmt: skip
        assert result.returncode == 0, result.stderr
        outputs.add(result.stdout)
    assert len(outputs) == 1
    assert json.loads(outputs.pop())["comparison_version"] == 1
    assert list(tmp_path.iterdir()) == []
