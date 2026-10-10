"""Generator scale: the 100-puzzle cap, its work budget and behavior at 20, 60 and 100.

Books are built in memory from a small synthetic bank of generic words; nothing is
written. The real 60-puzzle book is covered by test_automotive_production.py.
"""

import hashlib
import json
import os
import subprocess
import sys
import tracemalloc

import pytest

from puzzlepress import build_identity, validate_project
from puzzlepress.batch import derive_puzzle_seed, generate_batch, puzzle_digest
from puzzlepress.content import MAX_BATCH_ATTEMPTS, MAX_PUZZLES
from puzzlepress.publication import build_publication
from tests.helpers import ROOT

WORDS = (
    "ANCHOR BASKET CANDLE DONKEY EMBLEM FABRIC GARDEN HARBOR ISLAND JIGSAW KETTLE "
    "LANTERN MEADOW NAPKIN ORCHID PARCEL QUARRY RIBBON SADDLE TABLET UMBRELLA VELVET "
    "WALNUT YOGURT ZIPPER"
).split()


def book(count: int, *, attempts: int | None = None, width: int = 11, words: int = 7) -> dict:
    profile: dict[str, object] = {
        "id": "even",
        "width": width,
        "height": width,
        "directions": ["right", "down", "down-right"],
    }
    if attempts is not None:
        profile["max_attempts"] = attempts
    return {
        "schema_version": 1,
        "book": {"id": "scale-book", "title": "Scale", "language": "en"},
        "build": {"seed": 2026},
        "word_search": {
            "banks": [
                {"id": "things", "entries": [{"id": w.lower(), "display": w} for w in WORDS]}
            ],
            "profiles": [profile],
            "puzzles": [
                {
                    "id": f"set-{n:03d}",
                    "title": f"Set {n}",
                    "theme": "Things",
                    "bank": "things",
                    "target_ids": [WORDS[(n * 3 + k) % len(WORDS)].lower() for k in range(words)],
                    "difficulty": "even",
                }
                for n in range(1, count + 1)
            ],
        },
        "composition": {
            "front_matter": [{"kind": "title_page"}],
            "solutions": {"placement": "end", "title": "Solutions", "per_page": 4},
        },
    }


def codes(data: dict) -> set[str]:
    return {issue.code for issue in validate_project(data).issues}


def test_cap_is_100_and_101_is_rejected() -> None:
    assert MAX_PUZZLES == 100
    assert validate_project(book(100)).valid
    assert "count" in codes(book(101))


def test_work_budget_keeps_the_former_worst_case() -> None:
    # 20 puzzles at the 1,000,000-attempt maximum was the bound before the cap rose.
    assert MAX_BATCH_ATTEMPTS == 20 * 1_000_000
    assert validate_project(book(20, attempts=1_000_000)).valid
    assert "work_budget" in codes(book(21, attempts=1_000_000))
    # Defaults (100,000 attempts) keep a full 100-puzzle book within the budget.
    assert validate_project(book(100)).valid
    assert validate_project(book(100, attempts=200_000)).valid
    assert "work_budget" in codes(book(100, attempts=200_001))


@pytest.mark.parametrize("count", [20, 60, 100])
def test_batches_generate_verify_and_report_quality_at_scale(count: int) -> None:
    project = validate_project(book(count)).require_project()
    report = generate_batch(project)
    assert report.success and len(report.puzzles) == count
    assert len({r.id for r in report.puzzles}) == count
    assert len(report.content.similarities) == count * (count - 1) // 2
    # Every puzzle places every requested word; the batch verified each solution.
    for result in report.puzzles:
        assert result.puzzle is not None
        assert len(result.puzzle.solution.placements) == 7
    # Reuse is reported, never repaired: 26 words over many puzzles repeat.
    assert any(f.code == "word_reuse" for f in report.findings)
    _, plan = build_publication(project)
    assert plan.complete and plan.statistics.puzzles == count


def test_puzzle_seeds_and_grids_ignore_unrelated_puzzles() -> None:
    small = generate_batch(validate_project(book(20)).require_project())
    data = book(100)
    data["word_search"]["puzzles"].reverse()
    large = generate_batch(validate_project(data).require_project())
    digests = {r.id: puzzle_digest(r.puzzle) for r in large.puzzles if r.puzzle}
    for result in small.puzzles:
        assert result.seed == derive_puzzle_seed(2026, result.id)
        assert result.puzzle is not None
        assert digests[result.id] == puzzle_digest(result.puzzle)


def test_partial_failure_at_scale_keeps_every_other_puzzle() -> None:
    data = book(60)
    data["word_search"]["profiles"].append(
        {"id": "cramped", "width": 6, "height": 6, "directions": ["right"], "max_restarts": 2,
         "max_attempts": 2_000}
    )  # fmt: skip
    failing = data["word_search"]["puzzles"][30]
    failing["difficulty"] = "cramped"
    failing["target_ids"] = ["anchor", "basket", "candle", "donkey", "emblem", "fabric", "garden"]
    report = generate_batch(validate_project(data).require_project())
    assert not report.success
    failed = [r for r in report.puzzles if r.puzzle is None]
    assert [r.id for r in failed] == [failing["id"]]
    assert failed[0].errors[0].code == "search_exhausted"
    assert failed[0].failure_stats is not None and failed[0].failure_stats.attempts <= 2_000
    assert sum(r.puzzle is not None for r in report.puzzles) == 59
    _, plan = build_publication(validate_project(data).require_project())
    assert not plan.complete
    assert [d.code for d in plan.diagnostics] == ["generation_failed"]


def test_invalid_content_fails_before_any_generation_at_scale() -> None:
    data = book(80)
    data["word_search"]["puzzles"][79]["id"] = data["word_search"]["puzzles"][0]["id"]
    data["word_search"]["puzzles"][40]["target_ids"] = ["missing"]
    data["word_search"]["banks"][0]["entries"].append({"id": "bad", "display": "O-RING"})
    data["word_search"]["profiles"][0]["width"] = 51
    assert {"duplicate_id", "reference", "characters", "range"} <= codes(data)


def test_memory_stays_bounded_for_100_puzzles() -> None:
    project = validate_project(book(100, width=9, words=5)).require_project()
    tracemalloc.start()
    try:
        report = generate_batch(project)
        _, peak = tracemalloc.get_traced_memory()
    finally:
        tracemalloc.stop()
    assert report.success
    # Measured about 2 MB; the bound catches quadratic report growth gone wrong.
    assert peak < 32 * 1024 * 1024


def test_60_puzzle_batch_bytes_are_identical_across_processes(tmp_path) -> None:
    source = tmp_path / "book.json"
    source.write_text(json.dumps(book(60)), encoding="utf-8")
    code = (
        "import hashlib, json, sys\n"
        "from puzzlepress import validate_project\n"
        "from puzzlepress.batch import generate_batch\n"
        "p = validate_project(json.load(open(sys.argv[1]))).require_project()\n"
        "data = json.dumps(generate_batch(p).to_dict(), sort_keys=True).encode()\n"
        "print(hashlib.sha256(data).hexdigest())\n"
    )
    results = set()
    for seed, cwd in (("1", tmp_path), ("987", ROOT)):
        env = {**os.environ, "PYTHONHASHSEED": seed}
        out = subprocess.run(
            [sys.executable, "-c", code, str(source)],
            capture_output=True, text=True, cwd=cwd, env=env, check=True,
        )  # fmt: skip
        results.add(out.stdout.strip())
    project = validate_project(book(60)).require_project()
    local = json.dumps(generate_batch(project).to_dict(), sort_keys=True).encode()
    assert results == {hashlib.sha256(local).hexdigest()}
    assert build_identity(project).startswith("pp1-sha256-")
