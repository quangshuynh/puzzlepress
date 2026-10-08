"""`puzzlepress publish validate|inspect|package`: exit codes, JSON, no network."""

import json
import shutil
import socket
import subprocess

import pytest

from puzzlepress import load_project
from puzzlepress.cli import main
from puzzlepress.cover.build import build_cover, write_cover
from puzzlepress.interior import build_interior, print_profile, write_interior
from puzzlepress.publishing import evaluate_readiness, readiness_bytes, validate_metadata
from tests.helpers import ROOT, installed_puzzlepress
from tests.publishing_helpers import publishing_project, reconfirm

DEMO = ROOT / "books" / "publishing-demo"


def run(capsysbinary, *argv):
    code = main(list(argv))
    captured = capsysbinary.readouterr()
    return code, captured.out, captured.err


@pytest.fixture
def ready(tmp_path):
    return publishing_project(tmp_path)


@pytest.fixture
def no_network(monkeypatch):
    def refuse(*args, **kwargs):
        raise AssertionError("A publishing command tried to open a network connection.")

    monkeypatch.setattr(socket.socket, "connect", refuse)
    monkeypatch.setattr(socket, "create_connection", refuse)
    monkeypatch.setattr(socket, "getaddrinfo", refuse)


def test_validate_reports_metadata_only(capsysbinary, ready):
    source, _ = ready
    code, out, _ = run(capsysbinary, "publish", "validate", str(source), "--json")
    assert code == 0
    assert json.loads(out) == validate_metadata(load_project(source).project).to_dict()
    assert run(capsysbinary, "publish", "validate", str(source), "--json")[1] == out
    code, out, _ = run(capsysbinary, "publish", "validate", str(source))
    assert code == 0 and b"Metadata: VALID" in out and b"publish inspect" in out


def test_validate_prints_confirmation_states_and_what_to_record(capsysbinary, ready):
    from puzzlepress.publishing.review import review_identity

    source, _ = ready
    code, out, _ = run(capsysbinary, "publish", "validate", str(source))
    assert code == 0 and b"  metadata: CONFIRMED." in out and b"Only you can confirm" not in out
    path = source / "book.yaml"
    path.write_text(
        path.read_text(encoding="utf-8").replace("- seaside puzzles", "- harbour puzzles", 1),
        encoding="utf-8",
    )
    code, out, _ = run(capsysbinary, "publish", "validate", str(source))
    current = review_identity(load_project(source).project, "metadata")
    assert code == 1 and b"  metadata: STALE." in out and b"  rights: CONFIRMED." in out
    assert f"  publishing.attestations.metadata: {current}".encode() in out
    assert b"publishing.attestations.rights:" not in out
    reconfirm(source, "metadata")
    assert run(capsysbinary, "publish", "validate", str(source))[0] == 0


def test_validate_explains_legacy_confirmations(capsysbinary, tmp_path):
    source, _ = publishing_project(
        tmp_path, version=1, attestations={"rights": True, "ai_disclosure": True, "metadata": True}
    )
    code, out, _ = run(capsysbinary, "publish", "validate", str(source))
    assert code == 1 and out.count(b": LEGACY.") == 3
    assert b"first set publishing.version to 2 and every confirmation to null" in out


def test_validate_fails_without_publishing_metadata(capsysbinary):
    code, out, _ = run(
        capsysbinary, "publish", "validate", str(ROOT / "books" / "composition-demo")
    )
    assert code == 1 and b"[publishing_configured]" in out


def test_inspect_json_is_the_readiness_report(capsysbinary, ready):
    source, output = ready
    code, out, _ = run(
        capsysbinary, "publish", "inspect", str(source), "--output", str(output), "--json"
    )
    assert code == 0
    assert out == readiness_bytes(evaluate_readiness(load_project(source).project, source, output))
    code, text, _ = run(capsysbinary, "publish", "inspect", str(source), "--output", str(output))
    assert code == 0 and b"Package: READY" in text and b"Amazon KDP reviews and decides" in text


def test_package_refuses_and_writes_nothing_when_not_ready(capsysbinary, tmp_path):
    source, output = publishing_project(tmp_path, attestations={})
    before = sorted(p.name for p in output.iterdir())
    code, out, err = run(
        capsysbinary, "publish", "package", str(source), "--output", str(output), "--json"
    )
    assert code == 1
    result = json.loads(out)
    assert result["success"] is False and result["code"] == "not_ready"
    assert {f["code"] for f in result["blocking"]} == {"attestations"}
    assert b"No package was written" in err
    assert sorted(p.name for p in output.iterdir()) == before


def test_package_writes_the_verified_package(capsysbinary, ready, no_network):
    source, output = ready
    code, out, _ = run(
        capsysbinary, "publish", "package", str(source), "--output", str(output), "--zip", "--json"
    )
    assert code == 0
    result = json.loads(out)
    assert result["success"] is True and result["package_identity"].startswith("pp1-package-")
    assert [f["name"] for f in result["files"]] == sorted(
        p.name for p in (output / "publishing").iterdir() if p.name != "package.json"
    )
    assert (output / "publishing.zip").is_file()
    code, text, _ = run(capsysbinary, "publish", "inspect", str(source), "--output", str(output))
    assert code == 0 and b"Exported package: current" in text
    code, text, _ = run(capsysbinary, "publish", "package", str(source), "--output", str(output))
    assert code == 0 and b"Nothing has been uploaded or submitted." in text


def test_usage_errors_exit_2(capsysbinary):
    with pytest.raises(SystemExit) as caught:
        main(["publish"])
    assert caught.value.code == 2
    with pytest.raises(SystemExit) as caught:
        main(["publish", "package"])
    assert caught.value.code == 2


def test_publishing_demo_is_blocked_only_by_human_decisions(capsysbinary, tmp_path, no_network):
    source = tmp_path / "publishing-demo"
    shutil.copytree(DEMO, source)
    output = tmp_path / "out"
    project = load_project(source).project
    write_interior(build_interior(project, print_profile("paperback-8.5x11")), output, source)
    write_cover(build_cover(project, source, output), output, source)
    report = evaluate_readiness(project, source, output)
    verdicts = report.verdicts()
    assert verdicts["metadata"] == "valid"
    assert verdicts["interior"] == {"state": "current", "structural": "valid", "kdp": "ready"}
    assert verdicts["cover"] == {"state": "current", "structural": "valid", "kdp": "ready"}
    blocking = {f.rule.code for f in report.findings if f.severity.value == "error"}
    assert blocking == {"ai_disclosure_complete", "attestations"}
    code, _, _ = run(capsysbinary, "publish", "package", str(source), "--output", str(output))
    assert code == 1 and not (output / "publishing").exists()


def test_installed_console_script(tmp_path):
    source, output = publishing_project(tmp_path)
    command = [str(installed_puzzlepress()), "publish", "inspect", str(source)]
    completed = subprocess.run(
        [*command, "--output", str(output), "--json"], capture_output=True, check=False
    )
    assert completed.returncode == 0
    assert json.loads(completed.stdout)["verdicts"]["package"] == "ready"
