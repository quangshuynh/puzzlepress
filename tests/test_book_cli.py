"""`puzzlepress book plan` text/JSON contracts, failures and process determinism."""

import json
import os
import subprocess
import sys
from pathlib import Path

from puzzlepress import dump_project, load_project, validate_project
from puzzlepress.publication import build_publication
from tests.helpers import installed_puzzlepress

ROOT = Path(__file__).resolve().parents[1]
DEMO = ROOT / "books" / "composition-demo"


def run_cli(*args, **kwargs):
    return subprocess.run(
        [sys.executable, "-m", "puzzlepress", *map(str, args)],
        capture_output=True,
        text=True,
        check=False,
        **kwargs,
    )


def test_text_plan_lists_reading_order_numbering_and_statistics():
    before = DEMO.joinpath("book.yaml").read_bytes()
    result = run_cli("book", "plan", DEMO)
    assert result.returncode == 0 and not result.stderr
    lines = result.stdout.splitlines()
    assert "composition-demo: 11 logical pages, verified" in lines[1]
    rows = [line.split(None, 4) for line in lines[3:14]]
    assert [row[:3] for row in rows[:5]] == [
        ["1", "recto", "(i)"],
        ["2", "verso", "(ii)"],
        ["3", "recto", "(iii)"],
        ["4", "verso", "(iv)"],
        ["5", "recto", "1"],
    ]
    assert "Blank: puzzles start on recto" in lines[6]
    assert "Puzzle 1: Along the Shoreline [shoreline]; solution p. 5" in lines[7]
    assert "Solutions for puzzle 1 (p. 1), 2 (p. 2) | heading: Solutions" in lines[11]
    assert "blanks: 1" in result.stdout and "not a final printed page count" in result.stdout
    assert DEMO.joinpath("book.yaml").read_bytes() == before
    assert not (ROOT / "build" / "composition-demo").exists()


def test_json_plan_matches_core_and_is_identical_across_processes(tmp_path):
    project = load_project(DEMO).project
    report, plan = build_publication(project)
    outputs = []
    for seed in ("0", "4242"):
        result = run_cli(
            "book",
            "plan",
            DEMO,
            "--json",
            cwd=tmp_path,
            env={**os.environ, "PYTHONHASHSEED": seed},
        )
        assert result.returncode == 0 and not result.stderr
        outputs.append(result.stdout)
    assert outputs[0] == outputs[1]
    payload = json.loads(outputs[0])
    assert payload["plan"] == json.loads(json.dumps(plan.to_dict()))
    assert payload["verification"] == {"valid": True, "issues": []}
    assert payload["generation"] == {"success": True, "clean": True, "quality_findings": 0}
    assert all(isinstance(p["puzzle"]["seed"], str) for p in payload["plan"]["pages"][4:8])


def test_expected_failures_have_no_traceback(tmp_path, garden):
    legacy = run_cli("book", "plan", ROOT / "books" / "garden-demo")
    assert legacy.returncode == 1 and not legacy.stdout
    assert "composition [required]" in legacy.stderr and "Traceback" not in legacy.stderr
    path = tmp_path / "book.yaml"
    path.write_text(dump_project(garden) + "composition: {solutions: {placement: x}}\n")
    invalid = run_cli("book", "plan", path, "--json")
    assert invalid.returncode == 1 and not invalid.stdout
    assert "composition.solutions.placement [choice]" in invalid.stderr
    assert run_cli("book").returncode == 2
    assert run_cli("book", "plan").returncode == 2


def test_generation_failure_prints_plan_and_exits_one(tmp_path):
    data = load_project(DEMO).project.to_dict()
    data["word_search"]["profiles"].append(
        {"id": "tiny", "width": 4, "height": 4, "directions": ["right"], "max_restarts": 1}
    )
    data["word_search"]["puzzles"][0]["difficulty"] = "tiny"
    data["word_search"]["puzzles"][0]["target_ids"] = ["wave", "sand", "crab", "kelp", "tide"]
    data["output"]["directory"] = "../build"
    path = tmp_path / "source" / "book.yaml"
    path.parent.mkdir()
    path.write_text(dump_project(validate_project(data).require_project()), encoding="utf-8")
    result = run_cli("book", "plan", path, "--json")
    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert not payload["plan"]["complete"] and payload["verification"]["valid"]
    assert payload["plan"]["pages"][4]["puzzle"]["digest"] is None
    assert "word_search.puzzles.0 [generation_failed]" in result.stderr


def test_installed_console_script_plans_books():
    result = subprocess.run(
        [str(installed_puzzlepress()), "book", "plan", str(DEMO)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert "11 logical pages, verified" in result.stdout
