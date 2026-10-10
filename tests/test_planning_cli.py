"""`puzzlepress plan inspect|validate|report|approve|handoff`: exit codes, JSON, writes."""

import json
import socket
import subprocess
from pathlib import Path

import pytest
from planning_helpers import complete_plan, copy_book, document

from puzzlepress import load_project
from puzzlepress.cli import main
from puzzlepress.planning import (
    evaluate_plan,
    handoff_bytes,
    read_planning,
    report_bytes,
    write_planning,
)
from tests.helpers import ROOT, installed_puzzlepress


def run(capsysbinary: pytest.CaptureFixture[bytes], *argv: str) -> tuple[int, bytes, bytes]:
    code = main(list(argv))
    captured = capsysbinary.readouterr()
    return code, captured.out, captured.err


@pytest.fixture(autouse=True)
def no_network(monkeypatch: pytest.MonkeyPatch) -> None:
    def refuse(*args: object, **kwargs: object) -> None:
        raise AssertionError("A planning command tried to open a network connection.")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)
    monkeypatch.setattr(socket, "getaddrinfo", refuse)


@pytest.fixture
def ready(tmp_path: Path) -> Path:
    """A copy of the synthetic production book whose plan is ready for approval."""
    book = copy_book(tmp_path)
    current = read_planning(book)
    write_planning(book, document(complete_plan()), current.revision)
    return book


def files(book: Path) -> dict[str, bytes]:
    return {p.name: p.read_bytes() for p in book.iterdir()}


def test_projects_without_a_plan_report_it(capsysbinary: pytest.CaptureFixture[bytes]) -> None:
    for command in ("inspect", "validate", "report", "handoff"):
        code, out, err = run(capsysbinary, "plan", command, str(ROOT / "books" / "garden-demo"))
        assert code == 1 and out == b"" and b"No planning document" in err


def test_demo_inspect_validate_and_report(
    capsysbinary: pytest.CaptureFixture[bytes], production_book: Path
) -> None:
    project = load_project(production_book).project
    plan = read_planning(production_book).document
    assert plan is not None
    report = evaluate_plan(project, plan)
    code, out, _ = run(capsysbinary, "plan", "inspect", str(production_book))
    assert code == 0 and report.identity.encode() in out and b"State: needs_research" in out
    code, out, _ = run(capsysbinary, "plan", "inspect", str(production_book), "--json")
    summary = json.loads(out)
    assert code == 0 and summary["planning_identity"] == report.identity
    assert summary["state"] == "needs_research" and "findings" not in summary
    code, out, _ = run(capsysbinary, "plan", "validate", str(production_book))
    assert code == 0 and b"References and vocabulary: valid" in out
    code, out, _ = run(capsysbinary, "plan", "report", str(production_book))
    assert code == 1 and b"question_blocking_open" in out and b"not publishing approval" in out
    code, out, _ = run(capsysbinary, "plan", "report", str(production_book), "--json")
    assert code == 1 and out == report_bytes(report)
    assert run(capsysbinary, "plan", "report", str(production_book), "--json")[1] == out
    code, _, err = run(capsysbinary, "plan", "handoff", str(production_book))
    assert code == 1 and b"Only an approved plan" in err


def test_validate_reports_schema_and_structural_problems(
    capsysbinary: pytest.CaptureFixture[bytes], tmp_path: Path
) -> None:
    book = copy_book(tmp_path)
    path = book / "planning.yaml"
    path.write_text("planning_version: 1\nthemes: [{id: a}]\n", encoding="utf-8")
    code, out, err = run(capsysbinary, "plan", "validate", str(book))
    assert code == 1 and out == b"" and b"planning.yaml themes.0.label [text]" in err
    code, out, _ = run(capsysbinary, "plan", "validate", str(book), "--json")
    assert code == 1 and json.loads(out)["valid"] is False
    data = complete_plan()
    data["vocabulary"][0]["entries"].append({"word": "O-RING"})  # type: ignore[index]
    write_planning(book, document(data), None if not path.exists() else _rev(path))
    code, out, _ = run(capsysbinary, "plan", "validate", str(book))
    assert code == 1 and b"word_invalid" in out


def _rev(path: Path) -> str:
    import hashlib

    return "sha256-" + hashlib.sha256(path.read_bytes()).hexdigest()


def test_approve_requires_the_reviewed_identity_and_writes_only_the_plan(
    capsysbinary: pytest.CaptureFixture[bytes], ready: Path
) -> None:
    before = files(ready)
    code, out, _ = run(capsysbinary, "plan", "report", str(ready))
    assert code == 0 and b"State: ready_for_approval" in out and b"plan approve" in out
    identity = evaluate_plan(load_project(ready).project, document(complete_plan())).identity
    code, _, err = run(capsysbinary, "plan", "approve", str(ready), "--identity", "pp1-x")
    assert code == 1 and b"Not recorded" in err and files(ready) == before
    code, out, _ = run(capsysbinary, "plan", "approve", str(ready), "--identity", identity)
    assert code == 0 and identity.encode() in out
    after = files(ready)
    assert after["book.yaml"] == before["book.yaml"]
    assert set(after) == set(before)
    assert read_planning(ready).document.approval == identity  # type: ignore[union-attr]
    code, out, _ = run(capsysbinary, "plan", "report", str(ready), "--json")
    assert code == 0 and json.loads(out)["state"] == "approved"
    code, out, _ = run(capsysbinary, "plan", "approve", str(ready), "--identity", identity)
    assert code == 0 and b"Nothing to change" in out
    # The handoff prints; it writes nothing and never touches book.yaml.
    snapshot = files(ready)
    code, out, _ = run(capsysbinary, "plan", "handoff", str(ready), "--json")
    plan = read_planning(ready).document
    assert plan is not None
    assert code == 0 and out == handoff_bytes(evaluate_plan(load_project(ready).project, plan))
    code, out, _ = run(capsysbinary, "plan", "handoff", str(ready))
    assert code == 0 and b"Nothing was generated or written" in out
    assert files(ready) == snapshot
    assert not (ready.parent.parent / "build").exists()
    code, out, _ = run(capsysbinary, "plan", "approve", str(ready), "--withdraw")
    assert code == 0 and read_planning(ready).document.approval is None  # type: ignore[union-attr]


def test_approve_refuses_a_plan_that_is_not_ready(
    capsysbinary: pytest.CaptureFixture[bytes], tmp_path: Path
) -> None:
    book = copy_book(tmp_path)
    before = files(book)
    plan = read_planning(book).document
    assert plan is not None
    identity = evaluate_plan(load_project(book).project, plan).identity
    code, _, err = run(capsysbinary, "plan", "approve", str(book), "--identity", identity)
    assert code == 1 and b"Only a plan ready for approval" in err
    assert files(book) == before


def test_usage_errors_exit_2(
    capsysbinary: pytest.CaptureFixture[bytes], production_book: Path
) -> None:
    for argv in (["plan"], ["plan", "approve", str(production_book)], ["plan", "frobnicate", "x"]):
        with pytest.raises(SystemExit) as caught:
            main(argv)
        assert caught.value.code == 2


def test_installed_cli_plans_without_writing(tmp_path: Path, production_book: Path) -> None:
    before = files(production_book)
    for command, expected in (("inspect", 0), ("validate", 0), ("report", 1), ("handoff", 1)):
        result = subprocess.run(
            [str(installed_puzzlepress()), "plan", command, str(production_book), "--json"],
            capture_output=True,
            cwd=tmp_path,
        )
        assert result.returncode == expected, (command, result.stderr)
    assert files(production_book) == before
    assert list(tmp_path.iterdir()) == []
