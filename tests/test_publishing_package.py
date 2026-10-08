"""Publishing package: assembly, identity, verified export, ZIP and determinism."""

import hashlib
import io
import json
import os
import subprocess
import sys
import zipfile

import pytest

from puzzlepress import load_project
from puzzlepress.publishing import package as package_module
from puzzlepress.publishing.package import (
    ALL_NAMES,
    ARCHIVE,
    NAMES,
    PackageError,
    archive_bytes,
    assemble_package,
    export_state,
    verify_archive,
    verify_package_files,
    write_package,
)
from puzzlepress.publishing.readiness import evaluate_readiness
from tests.cover_helpers import LEAKS, photo_bytes
from tests.helpers import ROOT
from tests.publishing_helpers import publishing_project, reconfirm


def evaluate(source, output):
    return evaluate_readiness(load_project(source).project, source, output)


def package_of(source, output):
    return assemble_package(evaluate(source, output))


def snapshot(*directories, skip=("publishing",)):
    return {
        p.relative_to(d).as_posix(): hashlib.sha256(p.read_bytes()).hexdigest()
        for d in directories
        for p in sorted(d.rglob("*"))
        if p.is_file() and not any(part in skip for part in p.relative_to(d).parts)
    }


def edit(source, old, new):
    path = source / "book.yaml"
    text = path.read_text(encoding="utf-8")
    assert old in text
    path.write_text(text.replace(old, new, 1), encoding="utf-8")


@pytest.fixture
def ready(tmp_path):
    return publishing_project(tmp_path / "book", photo=photo_bytes(5400, 3600, private=True))


def test_package_contains_exactly_the_documented_files(ready):
    source, output = ready
    package = package_of(source, output)
    names = [name for name, _ in package.files]
    assert names == sorted(ALL_NAMES) and len(names) == 9
    assert package.file("interior.pdf") == (output / "interior.pdf").read_bytes()
    assert package.file("cover.pdf") == (output / "cover.pdf").read_bytes()
    manifest, problem = verify_package_files(dict(package.files))
    assert problem is None and manifest == package.manifest
    assert manifest["status"] == "ready_for_manual_kdp_submission"
    assert "Not submitted to Amazon" in manifest["statement"]
    assert [f["name"] for f in manifest["files"]] == list(NAMES)
    for entry in manifest["files"]:
        data = package.file(entry["name"])
        assert entry["sha256"] == hashlib.sha256(data).hexdigest() and entry["bytes"] == len(data)
        assert entry["purpose"]


def test_not_ready_books_are_refused_and_nothing_is_written(tmp_path):
    source, output = publishing_project(tmp_path, attestations={})
    with pytest.raises(PackageError) as caught:
        package_of(source, output)
    assert caught.value.code == "not_ready" and "Not ready" in str(caught.value)
    assert not (output / "publishing").exists()


def test_no_paths_or_private_metadata_in_any_file(ready):
    source, output = ready
    package = package_of(source, output)
    for name, data in package.files:
        for marker in (str(source), str(output), str(source).replace("\\", "\\\\")):
            assert marker.encode() not in data, name
        assert not any(leak in data for leak in LEAKS), name
    assert b"Exif" not in package.file("cover.pdf")


def test_identity_tracks_metadata_and_artifacts(ready):
    source, output = ready
    first = package_of(source, output)
    assert first.identity.startswith("pp1-package-sha256-")
    assert package_of(source, output).identity == first.identity
    edit(source, "- seaside puzzles", "- harbour puzzles")
    assert not evaluate(source, output).package_ready  # The metadata confirmation is stale.
    reconfirm(source, "metadata")
    changed = package_of(source, output)
    assert changed.identity != first.identity
    assert changed.file("interior.pdf") == first.file("interior.pdf")
    assert changed.file("cover.pdf") == first.file("cover.pdf")
    identities = changed.manifest["identities"]
    assert identities["publishing"] != first.manifest["identities"]["publishing"]
    assert identities["interior"] == first.manifest["identities"]["interior"]


def test_export_is_verified_and_read_only_for_sources(ready):
    source, output = ready
    before = snapshot(source, output)
    package = package_of(source, output)
    assert export_state(output, source, package.book_id, package.identity).state == "none"
    written = write_package(package, output, source)
    assert written.directory == (output / "publishing").resolve()
    assert sorted(p.name for p in written.directory.iterdir()) == sorted(ALL_NAMES)
    assert snapshot(source, output) == before
    assert export_state(output, source, package.book_id, package.identity).state == "current"
    assert not [p for p in output.iterdir() if p.name.startswith(".publishing-")]


def test_export_replaces_its_own_package_and_reports_staleness(ready):
    source, output = ready
    first = package_of(source, output)
    write_package(first, output, source)
    edit(source, "- seaside puzzles", "- harbour puzzles")
    reconfirm(source, "metadata")
    second = package_of(source, output)
    state = export_state(output, source, second.book_id, second.identity)
    assert state.state == "stale" and state.identity == first.identity
    write_package(second, output, source)
    assert export_state(output, source, second.book_id, second.identity).state == "current"
    leftovers = [p.name for p in output.iterdir() if p.name.startswith(".publishing-")]
    assert leftovers == []


def test_renderer_change_stales_interior_cover_and_package(tmp_path, monkeypatch):
    """Interior renderer -> interior identity -> cover freshness -> package identity."""
    from puzzlepress.interior import build as interior_build
    from puzzlepress.interior import build_interior, print_profile, write_interior

    monkeypatch.setattr(interior_build, "RENDERER_VERSION", 1)  # Built before renderer 2.
    source, output = publishing_project(tmp_path / "book")
    old = package_of(source, output)
    write_package(old, output, source)
    old_cover = json.loads((output / "cover.json").read_bytes())
    monkeypatch.undo()

    report = evaluate(source, output)
    verdicts = report.verdicts()
    assert verdicts["interior"]["state"] == "stale" and verdicts["cover"]["state"] == "stale"
    assert not report.package_ready
    assert any(
        f.message == "Interior is out of date: Renderer version changed after this interior "
        "was built."
        for f in report.findings
    )
    assert export_state(output, source, old.book_id, None).state == "stale"
    assert report.identities()["publishing"] == old.manifest["identities"]["publishing"]

    # Rebuilding only the interior: the cover's geometry and bytes are unaffected, so it
    # stays current (its provenance warns); the package identity changes.
    project = load_project(source).project
    write_interior(build_interior(project, print_profile("paperback-8.5x11")), output, source)
    report = evaluate(source, output)
    assert report.verdicts()["interior"]["state"] == "current"
    assert report.verdicts()["cover"]["state"] == "current" and report.package_ready
    assert any(f.related == "cover_interior_provenance" for f in report.findings)
    assert json.loads((output / "cover.json").read_bytes()) == old_cover
    new = assemble_package(report)
    assert new.identity != old.identity
    assert export_state(output, source, new.book_id, new.identity).state == "stale"


def test_damaged_exports_are_detected(ready):
    source, output = ready
    package = package_of(source, output)
    write_package(package, output, source)
    (output / "publishing" / "metadata.json").write_bytes(b"{}\n")
    state = export_state(output, source, package.book_id, package.identity)
    assert state.state == "damaged" and "metadata.json" in state.problem


@pytest.mark.parametrize("case", ["file", "foreign_file", "other_book"])
def test_unrelated_files_are_never_replaced(ready, case):
    source, output = ready
    package = package_of(source, output)
    target = output / "publishing"
    if case == "file":
        target.write_text("not a directory", encoding="utf-8")
    else:
        target.mkdir()
        if case == "foreign_file":
            (target / "notes.txt").write_text("mine", encoding="utf-8")
        else:
            (target / "package.json").write_text('{"book_id": "another-book"}', encoding="utf-8")
    before = snapshot(output, skip=())
    with pytest.raises(PackageError) as caught:
        write_package(package, output, source)
    assert caught.value.code == "output_collision"
    assert snapshot(output, skip=()) == before


def test_export_requires_this_books_interior_and_disjoint_output(ready, tmp_path):
    source, output = ready
    package = package_of(source, output)
    with pytest.raises(PackageError) as caught:
        write_package(package, source / "inside", source)
    assert caught.value.code == "output_unavailable"
    empty = tmp_path / "elsewhere"
    empty.mkdir()
    with pytest.raises(PackageError) as caught:
        write_package(package, empty, source)
    assert caught.value.code == "output_missing"
    assert list(empty.iterdir()) == []


def test_failed_export_leaves_the_previous_package(ready, monkeypatch):
    source, output = ready
    first = package_of(source, output)
    write_package(first, output, source)
    before = snapshot(output / "publishing", skip=())
    edit(source, "- seaside puzzles", "- harbour puzzles")
    reconfirm(source, "metadata")
    second = package_of(source, output)
    calls = {"n": 0}
    real = package_module._write

    def failing(path, data):
        calls["n"] += 1
        if calls["n"] == 5:
            raise OSError("disk full (simulated)")
        real(path, data)

    monkeypatch.setattr(package_module, "_write", failing)
    with pytest.raises(PackageError) as caught:
        write_package(second, output, source)
    assert caught.value.code == "write_failed"
    assert snapshot(output / "publishing", skip=()) == before
    assert not [p for p in output.iterdir() if p.name.startswith(".publishing-")]
    assert export_state(output, source, first.book_id, first.identity).state == "current"


def test_archive_is_deterministic_and_safe(ready):
    source, output = ready
    package = package_of(source, output)
    data = archive_bytes(package)
    assert archive_bytes(package_of(source, output)) == data
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        infos = archive.infolist()
        assert [i.filename for i in infos] == [f"publishing/{n}" for n in sorted(ALL_NAMES)]
        for info in infos:
            assert info.date_time == (1980, 1, 1, 0, 0, 0)
            assert info.compress_type == zipfile.ZIP_STORED
            assert not info.filename.startswith(("/", "\\")) and ".." not in info.filename
            assert ":" not in info.filename
    assert verify_archive(data, package) is None
    assert verify_archive(data.replace(b"Seaside", b"Seasidx", 1), package) is not None
    written = write_package(package, output, source, archive=True)
    assert written.archive is not None and written.archive.name == ARCHIVE
    assert written.archive.read_bytes() == data


def test_archive_of_another_book_is_not_replaced(ready):
    source, output = ready
    (output / ARCHIVE).write_bytes(b"PK not ours")
    with pytest.raises(PackageError) as caught:
        write_package(package_of(source, output), output, source, archive=True)
    assert caught.value.code == "output_collision"
    assert (output / ARCHIVE).read_bytes() == b"PK not ours"


SCRIPT = """
import hashlib, json, sys
from pathlib import Path
from puzzlepress import load_project
from puzzlepress.publishing.package import archive_bytes, assemble_package
from puzzlepress.publishing.readiness import evaluate_readiness, readiness_bytes
source, output = Path(sys.argv[1]), Path(sys.argv[2])
report = evaluate_readiness(load_project(source).project, source, output)
package = assemble_package(report)
print(json.dumps({
    "identity": package.identity,
    "readiness": hashlib.sha256(readiness_bytes(report)).hexdigest(),
    "files": {name: hashlib.sha256(data).hexdigest() for name, data in package.files},
    "zip": hashlib.sha256(archive_bytes(package)).hexdigest(),
}))
"""


def test_package_is_byte_identical_across_processes_and_working_directories(ready, tmp_path):
    source, output = ready
    package = package_of(source, output)
    expected = {
        "identity": package.identity,
        "files": {name: hashlib.sha256(data).hexdigest() for name, data in package.files},
        "zip": hashlib.sha256(archive_bytes(package)).hexdigest(),
    }
    results = []
    for seed, cwd in (("0", tmp_path), ("4242", ROOT)):
        env = dict(os.environ, PYTHONHASHSEED=seed)
        completed = subprocess.run(
            [sys.executable, "-c", SCRIPT, str(source), str(output)],
            cwd=cwd,
            env=env,
            capture_output=True,
            text=True,
            check=True,
        )
        results.append(json.loads(completed.stdout))
    assert results[0] == results[1]
    assert {k: results[0][k] for k in expected} == expected
