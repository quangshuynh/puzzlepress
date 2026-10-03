import copy
import json
import os
import random
import subprocess
import sys
from dataclasses import FrozenInstanceError, replace
from pathlib import Path

import pytest

from puzzlepress import ProjectError, build_identity, dump_project, load_project, validate_project
from puzzlepress.batch import analyze_content, derive_puzzle_seed, generate_batch
from puzzlepress.wordsearch import Grid, WordSearchError, verify_word_search
from tests.helpers import installed_puzzlepress


def normalized(data):
    return validate_project(data).require_project()


def warning_project(garden):
    data = garden.to_dict()
    definition = copy.deepcopy(data["word_search"]["puzzles"][0])
    definition["id"] = "flowers-again"
    data["word_search"]["puzzles"].append(definition)
    data["word_search"]["quality"]["max_word_reuse"] = 1
    data["word_search"]["quality"]["prohibited_words"] = ["ROSE"]
    return normalized(data)


def failing_project(garden):
    data = garden.to_dict()
    data["word_search"]["profiles"].append(
        {
            "id": "tiny",
            "width": 1,
            "height": 1,
            "directions": ["right"],
            "max_restarts": 2,
        }
    )
    data["word_search"]["banks"].append(
        {
            "id": "letters",
            "entries": [{"id": "a", "display": "A"}, {"id": "b", "display": "B"}],
        }
    )
    data["word_search"]["puzzles"].insert(
        0,
        {
            "id": "impossible",
            "title": "Impossible",
            "theme": "Letters",
            "bank": "letters",
            "target_ids": ["a", "b"],
            "difficulty": "tiny",
        },
    )
    return normalized(data)


def test_batch_generation_determinism_immutability_and_no_io(garden, tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    state = random.getstate()
    report = generate_batch(garden)
    assert report == generate_batch(garden)
    assert report.success and report.clean
    assert report.identity == build_identity(garden)
    assert [p.id for p in report.puzzles] == ["flowers", "herbs"]
    assert all(verify_word_search(p.puzzle).valid for p in report.puzzles)
    assert random.getstate() == state
    assert not list(tmp_path.iterdir())
    assert capsys.readouterr() == ("", "")
    with pytest.raises(FrozenInstanceError):
        report.identity = "changed"
    payload = report.to_dict()
    assert json.loads(json.dumps(payload))["success"] is True
    assert payload["puzzles"][0]["seed"] == "11860534647203643612"
    payload["puzzles"][0]["puzzle"]["grid"][0] = "changed"
    assert report.puzzles[0].puzzle.grid.rows[0] != "changed"


def test_seeds_reordering_insertion_and_different_project_seed(garden):
    report = generate_batch(garden)
    data = garden.to_dict()
    data["word_search"]["puzzles"].reverse()
    reordered = generate_batch(normalized(data))
    assert reordered.puzzles == tuple(reversed(report.puzzles))
    assert reordered.identity != report.identity
    inserted = generate_batch(warning_project(garden))
    assert [r.puzzle for r in inserted.puzzles[:2]] == [r.puzzle for r in report.puzzles]
    data["build"]["seed"] = 2027
    changed = generate_batch(normalized(data))
    assert all(
        a.puzzle.grid != b.puzzle.grid
        for a, b in zip(changed.puzzles, reordered.puzzles, strict=True)
    )
    assert derive_puzzle_seed(" 002026 ", "flowers") == report.puzzles[0].seed
    assert derive_puzzle_seed(2026, "herbs") != report.puzzles[0].seed


@pytest.mark.parametrize("identifier", ["", "bad space", "a" * 65, None])
def test_invalid_seed_derivation_identifier(identifier):
    with pytest.raises(WordSearchError):
        derive_puzzle_seed(0, identifier)


def test_content_reuse_duplicates_and_prohibited_occurrences(garden):
    project = warning_project(garden)
    analysis = analyze_content(project.word_search)
    assert {item.word for item in analysis.reuse} == {"ROSE", "LILY", "IRIS"}
    assert all(item.puzzle_ids == ("flowers", "flowers-again") for item in analysis.reuse)
    assert {f.code for f in analysis.findings} == {"word_reuse", "duplicate_targets"}
    assert all(pair.grid_agreement is None for pair in analysis.similarities)
    report = generate_batch(project)
    assert report.success and not report.clean
    assert {"prohibited_word", "duplicate_targets", "word_reuse"} <= {
        f.code for f in report.findings
    }
    assert report.puzzles[0].quality.prohibited.occurrences[0].word == "ROSE"
    assert report.to_dict()["quality_config"]["max_word_reuse"] == 1
    assert report.puzzles[0].quality.prohibited_screening_enabled
    assert report.puzzles[0].puzzle == generate_batch(garden).puzzles[0].puzzle


def test_reuse_normalizes_across_different_banks_and_ids(garden):
    data = garden.to_dict()
    data["word_search"]["banks"].append(
        {
            "id": "other",
            "entries": [{"id": "different", "display": "R O S E"}],
        }
    )
    data["word_search"]["puzzles"][1].update(bank="other", target_ids=["different"])
    analysis = analyze_content(normalized(data).word_search)
    assert len(analysis.reuse) == 1
    assert analysis.reuse[0].word == "ROSE"
    assert analysis.similarities[0].target_overlap == 1
    assert analysis.similarities[0].target_jaccard == pytest.approx(1 / 3)


def test_similarity_threshold_boundary_and_duplicate_target_order(garden):
    data = garden.to_dict()
    data["word_search"]["puzzles"][1]["target_ids"] = ["rose", "lily", "mint"]
    data["word_search"]["quality"]["target_similarity_threshold"] = 0.5
    assert "similar_targets" in {
        f.code for f in analyze_content(normalized(data).word_search).findings
    }
    data["word_search"]["quality"]["target_similarity_threshold"] = 0.51
    assert "similar_targets" not in {
        f.code for f in analyze_content(normalized(data).word_search).findings
    }
    data["word_search"]["puzzles"][1]["target_ids"] = ["iris", "lily", "rose"]
    assert "duplicate_targets" in {
        f.code for f in analyze_content(normalized(data).word_search).findings
    }


def test_partial_batch_failure_keeps_successes_and_work_counts(garden):
    project = failing_project(garden)
    report = generate_batch(project)
    assert not report.success and not report.clean
    failed = report.puzzles[0]
    assert failed.id == "impossible" and failed.puzzle is None and failed.quality is None
    assert failed.errors[0].code == "search_exhausted"
    assert failed.failure_stats.attempts == 6
    assert failed.failure_stats.restarts == 2
    assert report.puzzles[1:] == generate_batch(garden).puzzles
    assert len(report.content.similarities) == 3
    assert all(p.grid_agreement is None for p in report.content.similarities[:2])


def test_missing_content_and_invalid_direct_models_are_rejected(example_path, garden):
    with pytest.raises(ProjectError, match="no puzzle definitions"):
        generate_batch(load_project(example_path).project)
    invalid = replace(garden, word_search=replace(garden.word_search, puzzles=()))
    with pytest.raises(ProjectError):
        generate_batch(invalid)
    with pytest.raises(ProjectError):
        analyze_content(invalid.word_search)


def test_unexpected_generator_bug_remains_visible(garden, monkeypatch):
    def broken(*args):
        raise RuntimeError("internal defect")

    monkeypatch.setattr("puzzlepress.batch.generate_word_search", broken)
    with pytest.raises(RuntimeError, match="internal defect"):
        generate_batch(garden)


def test_corrupt_generated_result_remains_internal_failure(garden, monkeypatch):
    valid = generate_batch(garden).puzzles[0].puzzle
    monkeypatch.setattr(
        "puzzlepress.batch.generate_word_search", lambda *args: replace(valid, grid=Grid(()))
    )
    with pytest.raises(RuntimeError, match="failed verification"):
        generate_batch(garden)


def test_batch_hash_randomization_independence():
    root = Path(__file__).resolve().parents[1]
    outputs = []
    for seed in ("1", "12345"):
        result = subprocess.run(
            [
                sys.executable,
                "-m",
                "puzzlepress",
                "puzzle",
                "batch",
                str(root / "books/garden-demo"),
                "--json",
            ],
            env={**os.environ, "PYTHONHASHSEED": seed},
            capture_output=True,
            text=True,
            check=True,
        )
        outputs.append(result.stdout)
    assert outputs[0] == outputs[1]


def test_moderate_batch(garden):
    data = garden.to_dict()
    words = ["TEST" + c + "XYZ" for c in "ABCDEFGHIJKLMNOPQRSTUVWXY"]
    data["word_search"]["banks"][0]["entries"] = [
        {"id": str(i), "display": word} for i, word in enumerate(words)
    ]
    data["word_search"]["profiles"][0].update(width=20, height=20)
    data["word_search"]["puzzles"] = [
        {
            "id": f"p{i}",
            "title": "Synthetic",
            "theme": "Synthetic",
            "bank": "garden",
            "difficulty": "gentle",
            "target_ids": [str(j) for j in range(25)],
        }
        for i in range(5)
    ]
    report = generate_batch(normalized(data))
    assert report.success
    assert len(report.puzzles) == 5 and len(report.content.similarities) == 10
    assert all(p.puzzle.stats.attempts < 10_000 for p in report.puzzles)


def test_identical_grids_are_flagged(garden):
    data = garden.to_dict()
    data["word_search"]["banks"][0]["entries"] = [{"id": "a", "display": "A"}]
    for profile in data["word_search"]["profiles"]:
        profile.update(width=1, height=1)
    for definition in data["word_search"]["puzzles"]:
        definition["target_ids"] = ["a"]
    data["word_search"]["quality"]["grid_similarity_threshold"] = 1
    report = generate_batch(normalized(data))
    assert report.content.similarities[0].grid_agreement == 1
    assert "similar_grids" in {finding.code for finding in report.findings}


def test_truncated_scan_cannot_be_reported_clean(garden, monkeypatch):
    data = garden.to_dict()
    data["word_search"]["quality"]["prohibited_words"] = ["ROSE", "LILY", "IRIS"]
    monkeypatch.setattr("puzzlepress.quality.MAX_SCAN_HITS", 1)
    report = generate_batch(normalized(data))
    assert report.success and not report.clean
    assert "scan_truncated" in {finding.code for finding in report.findings}
    assert report.puzzles[0].quality.prohibited.truncated


def run_batch_cli(path, *args):
    return subprocess.run(
        [str(installed_puzzlepress()), "puzzle", "batch", str(path), *args],
        capture_output=True,
        text=True,
        check=False,
    )


def test_installed_batch_cli_text_json_and_strict_modes(garden, tmp_path):
    path = tmp_path / "book.yaml"
    path.write_text(dump_project(garden), encoding="utf-8")
    result = run_batch_cli(path)
    assert result.returncode == 0 and not result.stderr
    assert "Generated: 2/2; quality findings: 0" in result.stdout
    assert "Theme: Flowers | Difficulty: gentle | Seed:" in result.stdout
    assert "R O S E" in result.stdout
    structured = run_batch_cli(path, "--json", "--strict-quality")
    assert structured.returncode == 0 and not structured.stderr
    payload = json.loads(structured.stdout)
    assert payload["clean"] and payload["success"]
    assert len(payload["puzzles"]) == 2
    assert structured.stdout == run_batch_cli(path, "--json", "--strict-quality").stdout
    assert not (tmp_path / "build").exists()
    assert sorted(p.name for p in tmp_path.iterdir()) == ["book.yaml"]


def test_batch_cli_warning_exit_policy(garden, tmp_path):
    path = tmp_path / "book.yaml"
    path.write_text(dump_project(warning_project(garden)), encoding="utf-8")
    result = run_batch_cli(path, "--json")
    assert result.returncode == 0
    payload = json.loads(result.stdout)
    assert payload["success"] and not payload["clean"]
    assert payload["puzzles"][0]["quality"]["prohibited"]["occurrences"][0]["coordinates"]
    strict = run_batch_cli(path, "--json", "--strict-quality")
    assert strict.returncode == 1
    assert json.loads(strict.stdout) == payload
    assert not strict.stderr


def test_batch_cli_failure_report_and_invalid_input(garden, tmp_path):
    path = tmp_path / "book.yaml"
    path.write_text(dump_project(failing_project(garden)), encoding="utf-8")
    result = run_batch_cli(path, "--json")
    assert result.returncode == 1 and not result.stderr
    payload = json.loads(result.stdout)
    assert not payload["success"]
    assert payload["puzzles"][0]["failure_stats"]["attempts"] == 6
    assert payload["puzzles"][1]["puzzle"]["grid"]
    text = run_batch_cli(path)
    assert text.returncode == 1 and "[search_exhausted]" in text.stderr
    assert "Generated: 2/3" in text.stdout
    path.write_text("schema_version: 1\nword_search: {}", encoding="utf-8")
    invalid = run_batch_cli(path, "--json")
    assert invalid.returncode == 1 and invalid.stderr and not invalid.stdout
    assert "Traceback" not in invalid.stderr


def test_batch_cli_usage_error():
    result = subprocess.run(
        [sys.executable, "-m", "puzzlepress", "puzzle", "batch"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 2
