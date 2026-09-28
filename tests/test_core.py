import json
import os
import subprocess
import sys
from dataclasses import FrozenInstanceError
from importlib.metadata import version
from pathlib import Path

import pytest
import yaml

from puzzlepress import (
    ProjectError,
    __version__,
    build_identity,
    canonical_build_inputs,
    dump_project,
    load_project,
    locate_project,
    parse_project,
    resolve_output_directory,
    validate_project,
)


def test_installed_metadata_matches_identity_engine_version():
    assert version("puzzlepress") == __version__


def test_schema_defaults():
    minimal = {
        "schema_version": 1,
        "book": {"id": "test-book", "title": " Test Book ", "language": "en"},
        "build": {"seed": 0},
    }
    project = validate_project(minimal).require_project()
    assert project.book.title == "Test Book"
    assert project.book.subtitle is None
    assert project.content.items == ()
    assert project.output.directory == "../build/test-book"
    assert build_identity(project) == build_identity(parse_project(dump_project(project)))


@pytest.mark.parametrize(
    "section,value", [("book", None), ("build", []), ("content", None), ("output", "build")]
)
def test_invalid_section_types(source, section, value):
    data = parse_project(source).to_dict()
    data[section] = value
    result = validate_project(data)
    assert not result.valid
    assert any(issue.path == section and issue.code == "type" for issue in result.issues)


@pytest.mark.parametrize("book_id", ["../escape", "MixedCase", "con", "a/b", "", "a_b"])
def test_invalid_book_identifiers(source, book_id):
    data = parse_project(source).to_dict()
    data["book"]["id"] = book_id
    assert any(issue.path == "book.id" for issue in validate_project(data).issues)


def test_identity_v1_regression(source):
    # Change this only when intentionally changing the documented input contract
    # or engine version, or editing the source fixture's semantic content.
    assert build_identity(parse_project(source)) == (
        "pp1-sha256-7c31474f1712b985957d7edaa7ecff27f702060320eadbee7343819e13507bf2"
    )


def test_load_example_by_file_and_directory(example_path):
    loaded = load_project(example_path)
    assert load_project(example_path.parent) == loaded
    assert loaded.project.book.id == "automotive-word-search"
    assert loaded.project.build.seed == 2026
    assert loaded.project.content.items == ("ENGINE", "CLUTCH", "PISTON")
    assert loaded.source_path == example_path
    assert loaded.output_directory == example_path.parents[2] / "build/automotive-word-search"


def test_round_trip_and_immutable_values(source):
    project = parse_project(source)
    assert parse_project(dump_project(project)) == project
    assert validate_project(project.to_dict()).require_project() == project
    data = project.to_dict()
    data["content"]["items"].append("EXTRA")
    assert len(project.content.items) == 3
    with pytest.raises(FrozenInstanceError):
        project.book.title = "Changed"


def test_validation_collects_independent_errors(source):
    data = parse_project(source).to_dict()
    del data["book"]["title"]
    data["book"]["language"] = 42
    data["build"]["seed"] = -1
    data["content"]["items"] = ["", 42]
    data["book"]["typo"] = "oops"
    result = validate_project(data)
    assert not result.valid
    assert result.project is None
    assert {issue.path for issue in result.issues} == {
        "book.title",
        "book.language",
        "book.typo",
        "build.seed",
        "content.items.0",
        "content.items.1",
    }
    with pytest.raises(ProjectError) as error:
        result.require_project()
    assert error.value.issues == result.issues


@pytest.mark.parametrize("version", [7, 0, True, "1", 1.0, None])
def test_unsupported_schema_versions(source, version):
    data = parse_project(source).to_dict()
    data["schema_version"] = version
    result = validate_project(data)
    assert [(issue.path, issue.code) for issue in result.issues] == [
        ("schema_version", "unsupported_version")
    ]
    assert "Supported versions: 1" in result.issues[0].message


@pytest.mark.parametrize("field", ["schema_version", "book", "build"])
def test_missing_required_sections(source, field):
    data = parse_project(source).to_dict()
    del data[field]
    assert any(
        issue.path == field and issue.code == "required" for issue in validate_project(data).issues
    )


@pytest.mark.parametrize(
    "seed, expected", [(0, 0), (2**64 - 1, 2**64 - 1), (" 00042 ", 42), ("0000", 0)]
)
def test_seed_normalization(source, seed, expected):
    data = parse_project(source).to_dict()
    data["build"]["seed"] = seed
    assert validate_project(data).require_project().build.seed == expected


@pytest.mark.parametrize(
    "seed", [True, False, -1, 2**64, 1.0, None, "", "0x10", "-2", "+2", "1e3", "random", "9" * 5000]
)
def test_reject_invalid_seeds(source, seed):
    data = parse_project(source).to_dict()
    data["build"]["seed"] = seed
    assert any(issue.path == "build.seed" for issue in validate_project(data).issues)


@pytest.mark.parametrize(
    "bad_source",
    [
        "",
        "[]",
        "book: [",
        "a: 1\na: 2",
        "1: value",
        "schema_version: 1\n---\nschema_version: 1",
        "book: !!python/object:os.system {}",
        "book: &book {title: A}\nbuild: *book",
        "book: {<<: {title: A}}",
        "book: {[]: A}",
    ],
)
def test_malformed_or_unsupported_yaml(bad_source):
    with pytest.raises(ProjectError):
        parse_project(bad_source)


def test_yaml_syntax_errors_have_location():
    with pytest.raises(ProjectError) as error:
        parse_project("book: [")
    issue = error.value.issues[0]
    assert issue.code == "yaml"
    assert issue.line is not None and issue.column is not None


@pytest.mark.parametrize("tagged", ["!!map foo", "!!int nope", "!!bool perhaps"])
def test_explicit_yaml_tags_report_expected_errors(tagged):
    with pytest.raises(ProjectError) as error:
        parse_project(tagged)
    assert error.value.issues[0].code == "yaml"


def test_invalid_unicode_reports_validation_error(source):
    with pytest.raises(ProjectError) as error:
        parse_project(source.replace("Automotive Word Search", '"\\uD800"'))
    assert error.value.issues[0].path == "book.title"
    assert error.value.issues[0].code == "unicode"


def test_yaml_scalar_policy_and_no_global_resolver_mutation(source):
    project = parse_project(
        source.replace("2026", "00042").replace("ENGINE", "yes").replace("CLUTCH", "2026-09-27")
    )
    assert project.build.seed == 42
    assert project.content.items[:2] == ("yes", "2026-09-27")
    assert yaml.safe_load("yes") is True
    assert parse_project(dump_project(project)) == project


def test_identity_ignores_serialization_trivia_defaults_and_output(source):
    project = parse_project(source)
    reordered = project.to_dict()
    reordered = dict(reversed(list(reordered.items())))
    reordered["build"]["seed"] = "002026"
    reordered["book"]["title"] = "  Automotive Word Search  "
    del reordered["book"]["subtitle"]
    reordered["output"] = {"directory": "../elsewhere"}
    variant = parse_project("# comment\n" + yaml.safe_dump(reordered, sort_keys=False))
    assert canonical_build_inputs(project) == canonical_build_inputs(variant)
    assert build_identity(project) == build_identity(variant)
    material = json.loads(canonical_build_inputs(project))
    assert "output" not in material["project"]
    assert material["identity_version"] == 1
    assert material["engine_version"] == "0.1.0"


@pytest.mark.parametrize(
    "section,key,value",
    [
        ("book", "id", "another-book"),
        ("book", "title", "Another Title"),
        ("book", "language", "fr"),
        ("book", "subtitle", "Subtitle"),
        ("book", "author", "Author"),
        ("book", "imprint", "Press"),
        ("book", "description", "Different description"),
        ("build", "seed", 0),
        ("content", "items", ["PISTON", "CLUTCH", "ENGINE"]),
        ("content", "items", ["ENGINE", "CLUTCH"]),
    ],
)
def test_meaningful_input_changes_identity(source, section, key, value):
    project = parse_project(source)
    changed = project.to_dict()
    changed[section][key] = value
    assert build_identity(validate_project(changed).require_project()) != build_identity(project)


def test_identity_across_processes_cwd_and_hash_seed(example_path, tmp_path):
    code = (
        "import sys; from puzzlepress import load_project, build_identity; "
        "print(build_identity(load_project(sys.argv[1]).project))"
    )
    results = []
    for seed in ("1", "98765"):
        result = subprocess.run(
            [sys.executable, "-c", code, str(example_path)],
            cwd=tmp_path,
            env={**os.environ, "PYTHONHASHSEED": seed},
            capture_output=True,
            text=True,
            check=True,
        )
        results.append(result.stdout.strip())
    assert results == [build_identity(load_project(example_path).project)] * 2


def test_relative_path_and_read_only_loading(source, tmp_path, monkeypatch, capsys):
    root = tmp_path / "book source"
    root.mkdir()
    path = root / "book.yaml"
    path.write_text(source, encoding="utf-8-sig")
    before = path.read_bytes()
    monkeypatch.chdir(tmp_path)
    loaded = load_project(Path("book source"))
    assert loaded.source_path == path
    assert path.read_bytes() == before
    assert not loaded.output_directory.exists()
    assert not capsys.readouterr().out


def test_missing_file_and_no_parent_search(tmp_path):
    with pytest.raises(ProjectError) as error:
        locate_project(tmp_path)
    assert error.value.issues[0].code == "not_found"


def test_invalid_utf8(tmp_path):
    path = tmp_path / "book.yaml"
    path.write_bytes(b"\xff\xfe\xff")
    with pytest.raises(ProjectError) as error:
        load_project(path)
    assert error.value.issues[0].code == "io"


@pytest.mark.parametrize("directory", [".", "child/build", "..", "../book"])
def test_reject_source_output_overlap(source, tmp_path, directory):
    project_data = parse_project(source).to_dict()
    project_data["output"]["directory"] = directory
    project = validate_project(project_data).require_project()
    with pytest.raises(ProjectError) as error:
        resolve_output_directory(project, tmp_path / "book")
    assert error.value.issues[0].code == "source_overlap"


@pytest.mark.parametrize(
    "directory",
    [
        "/tmp/output",
        "C:/output",
        "C:output",
        "\\build",
        "../bad\\path",
        "../bad\x00path",
        "../bad:name",
    ],
)
def test_reject_nonportable_output_paths(source, directory):
    data = parse_project(source).to_dict()
    data["output"]["directory"] = directory
    assert any(issue.code == "path" for issue in validate_project(data).issues)


def test_output_cannot_be_existing_file(source, tmp_path):
    data = parse_project(source).to_dict()
    data["output"]["directory"] = "../artifact"
    (tmp_path / "artifact").write_text("keep", encoding="utf-8")
    with pytest.raises(ProjectError) as error:
        resolve_output_directory(validate_project(data).require_project(), tmp_path / "book")
    assert error.value.issues[0].code == "not_directory"


def test_output_symlink_into_source_is_rejected(source, tmp_path):
    root = tmp_path / "book"
    root.mkdir()
    alias = tmp_path / "alias"
    try:
        alias.symlink_to(root, target_is_directory=True)
    except OSError:
        pytest.skip("Creating symlinks requires OS permission on this host")
    data = parse_project(source).to_dict()
    data["output"]["directory"] = "../alias/build"
    with pytest.raises(ProjectError) as error:
        resolve_output_directory(validate_project(data).require_project(), root)
    assert error.value.issues[0].code == "source_overlap"
