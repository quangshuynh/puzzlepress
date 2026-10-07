"""`puzzlepress book plan/build` contracts, failures, output safety and determinism."""

import hashlib
import json
import os
import subprocess
import sys

from puzzlepress import dump_project, load_project, validate_project
from puzzlepress.publication import build_publication
from tests.helpers import DEMO, ROOT, demo_variant, installed_puzzlepress


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
    build_dir = ROOT / "build" / "composition-demo"
    build_before = sorted(build_dir.iterdir()) if build_dir.exists() else None
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
    assert (sorted(build_dir.iterdir()) if build_dir.exists() else None) == build_before


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


def build_cli(*args, **kwargs):
    return run_cli("book", "build", *args, **kwargs)


def write_source(tmp_path, project):
    path = tmp_path / "source" / "book.yaml"
    path.parent.mkdir(parents=True)
    path.write_text(dump_project(project), encoding="utf-8")
    return path


def test_build_writes_verified_interior_and_reports_it(tmp_path):
    out = tmp_path / "out"
    result = build_cli(DEMO, "--output", out)
    assert result.returncode == 0, result.stderr
    pdf = out / "interior.pdf"
    manifest = json.loads((out / "interior.json").read_text("utf-8"))
    assert f"Interior: {pdf}" in result.stdout
    assert "Pages: 11 | trim 8.5x11 in, no bleed | profile paperback-8.5x11 v1" in result.stdout
    assert hashlib.sha256(pdf.read_bytes()).hexdigest() in result.stdout
    assert "Warning: [kdp_minimum_page_count]" in result.stderr
    assert manifest["page_count"] == 11 and manifest["book_id"] == "composition-demo"
    assert manifest["pdf"]["sha256"] == hashlib.sha256(pdf.read_bytes()).hexdigest()


def test_build_json_is_identical_across_processes_cwd_and_hash_seeds(tmp_path):
    digests, manifests = [], []
    for seed in ("0", "4242"):
        cwd = tmp_path / f"cwd{seed}"
        cwd.mkdir()
        result = build_cli(
            DEMO,
            "--output",
            tmp_path / f"out{seed}",
            "--json",
            cwd=cwd,
            env={**os.environ, "PYTHONHASHSEED": seed},
        )
        assert result.returncode == 0, result.stderr
        payload = json.loads(result.stdout)
        assert payload["success"] is True
        manifests.append(payload["manifest"])
        digests.append(hashlib.sha256(open(payload["output"]["pdf"], "rb").read()).hexdigest())
    assert digests[0] == digests[1] == manifests[0]["pdf"]["sha256"]
    assert manifests[0] == manifests[1]
    assert (tmp_path / "out0" / "interior.json").read_bytes() == (
        tmp_path / "out4242" / "interior.json"
    ).read_bytes()


def test_build_defaults_to_project_output_directory(tmp_path):
    def local_output(data):
        data["output"]["directory"] = "../build/demo"

    path = write_source(tmp_path, demo_variant(local_output))
    result = build_cli(path)
    assert result.returncode == 0, result.stderr
    assert (tmp_path / "build" / "demo" / "interior.pdf").is_file()
    assert sorted(p.name for p in path.parent.iterdir()) == ["book.yaml"]


def test_build_failures_exit_one_with_diagnostics_and_no_pdf(tmp_path):
    legacy = build_cli(ROOT / "books" / "garden-demo", "--output", tmp_path / "a")
    assert legacy.returncode == 1 and "composition [required]" in legacy.stderr
    assert "Traceback" not in legacy.stderr and not (tmp_path / "a").exists()

    def overflow(data):
        data["composition"]["front_matter"][2]["text"] = "x\n" * 999 + "x"
        data["output"]["directory"] = "../build"

    source = write_source(tmp_path / "overflow", demo_variant(overflow))
    result = build_cli(source, "--output", tmp_path / "b", "--json")
    assert result.returncode == 1 and "Traceback" not in result.stderr
    payload = json.loads(result.stdout)
    assert payload["success"] is False and payload["stage"] == "layout"
    assert payload["diagnostics"][0]["code"] == "text_overflow"
    assert payload["diagnostics"][0]["kind"] == "instructions"
    assert "[text_overflow]" in result.stderr and "page 3" in result.stderr
    assert not (tmp_path / "b").exists()

    profile = build_cli(DEMO, "--profile", "a5", "--output", tmp_path / "c")
    assert profile.returncode == 1 and "[unsupported_profile]" in profile.stderr
    inside = build_cli(DEMO, "--output", DEMO / "build")
    assert inside.returncode == 1 and "[source_overlap]" in inside.stderr
    assert not (DEMO / "build").exists()
    assert build_cli().returncode == 2


def test_build_with_failed_generation_reports_incomplete_plan(tmp_path):
    def tiny(data):
        data["word_search"]["profiles"].append(
            {"id": "tiny", "width": 4, "height": 4, "directions": ["right"], "max_restarts": 1}
        )
        data["word_search"]["puzzles"][0]["difficulty"] = "tiny"
        data["word_search"]["puzzles"][0]["target_ids"] = ["wave", "sand", "crab", "kelp", "tide"]
        data["output"]["directory"] = "../build"

    source = write_source(tmp_path, demo_variant(tiny))
    result = build_cli(source, "--json")
    assert result.returncode == 1
    payload = json.loads(result.stdout)
    assert payload["stage"] == "integrity"
    assert {d["code"] for d in payload["diagnostics"]} == {"incomplete_plan", "missing_puzzle"}
    assert not (tmp_path / "build").exists()


def test_installed_console_script_builds_interiors(tmp_path):
    result = subprocess.run(
        [str(installed_puzzlepress()), "book", "build", str(DEMO), "--output", str(tmp_path)],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 0, result.stderr
    assert (tmp_path / "interior.pdf").stat().st_size > 0


def preflight_cli(*args, **kwargs):
    return run_cli("book", "preflight", *args, **kwargs)


def test_preflight_reports_structural_valid_and_kdp_not_ready(tmp_path):
    out = tmp_path / "out"
    assert build_cli(DEMO, "--output", out).returncode == 0
    built = {p.name: p.read_bytes() for p in out.iterdir()}
    result = preflight_cli(DEMO, "--output", out)
    assert result.returncode == 1 and "Traceback" not in result.stderr
    assert "Structural: VALID" in result.stdout and "KDP readiness: NOT READY" in result.stdout
    assert (
        "kdp [kdp_minimum_page_count] 11 pages. The supported KDP paperback minimum is 24 pages."
        in result.stdout
    )
    assert "Amazon KDP decides acceptance" in result.stdout
    report = (out / "preflight.json").read_bytes()
    assert {p.name: p.read_bytes() for p in out.iterdir() if p.name != "preflight.json"} == built
    data = json.loads(report)
    assert data["structural"]["status"] == "valid" and data["kdp"]["status"] == "not_ready"
    assert data["artifacts"]["pdf"]["sha256"] == hashlib.sha256(built["interior.pdf"]).hexdigest()
    assert data["ruleset"]["id"] == "puzzlepress-kdp-paperback" and data["report_version"] == 1


def test_preflight_json_is_identical_to_report_file_and_across_processes(tmp_path):
    out = tmp_path / "out"
    assert build_cli(DEMO, "--output", out).returncode == 0
    outputs = []
    for seed, cwd in (("0", tmp_path), ("4242", ROOT)):
        result = preflight_cli(
            DEMO, "--output", out, "--json", cwd=cwd, env={**os.environ, "PYTHONHASHSEED": seed}
        )
        assert result.returncode == 1
        outputs.append(result.stdout)
        assert result.stdout.encode() == (out / "preflight.json").read_bytes()
    assert outputs[0] == outputs[1]


def test_preflight_exits_zero_only_when_kdp_ready(tmp_path):
    source = write_source(tmp_path, demo_variant(puzzles=16))
    out = tmp_path / "out"
    assert build_cli(source, "--output", out).returncode == 0
    result = preflight_cli(source, "--output", out, "--no-write")
    assert result.returncode == 0, result.stdout
    assert "KDP readiness: READY" in result.stdout and "Blocking: none" in result.stdout
    assert not (out / "preflight.json").exists()


def test_preflight_missing_stale_and_usage(tmp_path):
    missing = preflight_cli(DEMO, "--output", tmp_path / "none", "--json")
    assert missing.returncode == 1 and not (tmp_path / "none").exists()
    assert json.loads(missing.stdout)["structural"]["status"] == "invalid"
    assert "preflight.json not written" in missing.stderr

    out = tmp_path / "out"
    assert build_cli(DEMO, "--output", out).returncode == 0

    def retitled(data):
        data["book"]["title"] = "Changed"

    source = write_source(tmp_path, demo_variant(retitled))
    stale = preflight_cli(source, "--output", out, "--json", "--no-write")
    payload = json.loads(stale.stdout)
    assert stale.returncode == 1 and payload["structural"]["status"] == "invalid"
    assert {"source_current", "pdf_matches_layout"} <= {f["rule"] for f in payload["findings"]}
    assert not (out / "preflight.json").exists()

    foreign = tmp_path / "foreign"
    foreign.mkdir()
    (foreign / "interior.json").write_text('{"book_id": "other"}', encoding="utf-8")
    result = preflight_cli(DEMO, "--output", foreign)
    assert result.returncode == 1 and not (foreign / "preflight.json").exists()
    inside = preflight_cli(DEMO, "--output", DEMO / "build")
    assert inside.returncode == 1 and "[source_overlap]" in inside.stderr
    assert not (DEMO / "build").exists()
    assert preflight_cli().returncode == 2


def test_installed_console_script_preflights(tmp_path):
    exe = str(installed_puzzlepress())
    subprocess.run([exe, "book", "build", str(DEMO), "--output", str(tmp_path)], check=True)
    result = subprocess.run(
        [exe, "book", "preflight", str(DEMO), "--output", str(tmp_path), "--json"],
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode == 1 and json.loads(result.stdout)["kdp"]["status"] == "not_ready"
