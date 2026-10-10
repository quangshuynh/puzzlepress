import copy
import json

import pytest

from puzzlepress import (
    build_identity,
    canonical_build_inputs,
    dump_project,
    parse_project,
    validate_project,
)
from puzzlepress.content import MAX_BANKS, MAX_PROFILES, MAX_PUZZLES


def change(data, path, value):
    cursor = data
    for key in path[:-1]:
        cursor = cursor[key]
    cursor[path[-1]] = value


def test_extended_schema_round_trip_and_serialization_independence(garden):
    assert garden.schema_version == 1
    assert parse_project(dump_project(garden)) == garden
    assert validate_project(garden.to_dict()).require_project() == garden
    data = garden.to_dict()
    data["word_search"]["banks"][0]["entries"][0]["display"] = "CHANGED"
    assert garden.word_search.banks[0].entries[0].display == "ROSE"
    material = json.loads(canonical_build_inputs(garden))
    assert material["word_search_pipeline_version"] == 1
    assert material["project"]["word_search"] == garden.word_search.to_dict()


@pytest.mark.parametrize(
    "path,value",
    [
        (("profiles", 0, "width"), 11),
        (("profiles", 0, "height"), 9),
        (("profiles", 0, "directions"), ["left", "up"]),
        (("profiles", 0, "max_attempts"), 200_000),
        (("profiles", 0, "max_restarts"), 30),
        (("banks", 0, "entries", 0, "display"), "DAISY"),
        (("puzzles", 0, "id"), "flowers-two"),
        (("puzzles", 0, "title"), "New Title"),
        (("puzzles", 0, "theme"), "New Theme"),
        (("puzzles", 0, "difficulty"), "varied"),
        (("puzzles", 0, "target_ids"), ["lily", "rose"]),
        (("quality", "max_word_reuse"), 3),
        (("quality", "target_similarity_threshold"), 0.7),
        (("quality", "grid_similarity_threshold"), 0.8),
        (("quality", "prohibited_words"), ["TEST"]),
    ],
)
def test_every_new_semantic_input_affects_identity(garden, path, value):
    data = garden.to_dict()
    change(data["word_search"], path, value)
    changed = validate_project(data).require_project()
    assert build_identity(changed) != build_identity(garden)


def test_equivalent_defaults_directions_and_policy_forms(garden):
    data = garden.to_dict()
    a = copy.deepcopy(data)
    del a["word_search"]["quality"]
    for profile in a["word_search"]["profiles"]:
        del profile["max_restarts"]
        del profile["max_attempts"]
        profile["directions"].reverse()
    a["build"]["seed"] = "002026"
    a["output"]["directory"] = "../elsewhere"
    assert build_identity(validate_project(a).require_project()) == build_identity(garden)
    data["word_search"]["quality"]["prohibited_words"] = ["FUEL PUMP", "test"]
    a["word_search"]["quality"] = {"prohibited_words": [" TEST ", "fuelpump"]}
    assert build_identity(validate_project(a).require_project()) == build_identity(
        validate_project(data).require_project()
    )


@pytest.mark.parametrize(
    "path,value",
    [
        ((), None),
        ((), []),
        (("typo",), 1),
        (("banks",), []),
        (("banks",), [None]),
        (("banks", 0, "extra"), 1),
        (("banks", 0, "entries"), []),
        (("banks", 0, "entries", 0, "display"), "A\tB"),
        (("banks", 0, "entries", 0, "display"), None),
        (("banks", 0, "entries", 0, "display"), "L I L Y"),
        (("banks", 0, "entries", 0, "id"), "lily"),
        (("banks", 0, "entries", 0, "extra"), 1),
        (("profiles",), []),
        (("profiles",), [True]),
        (("profiles", 0, "width"), True),
        (("profiles", 0, "height"), 51),
        (("profiles", 0, "width"), None),
        (("profiles", 0, "extra"), 1),
        (("profiles", 0, "max_attempts"), 0),
        (("profiles", 0, "directions"), []),
        (("profiles", 0, "directions"), ["sideways"]),
        (("profiles", 0, "directions"), ["right", "right"]),
        (("profiles", 0, "directions"), [{}]),
        (("puzzles",), []),
        (("puzzles",), "bad"),
        (("puzzles", 0, "id"), "../bad"),
        (("puzzles", 0, "theme"), ""),
        (("puzzles", 0, "title"), "\ud800"),
        (("puzzles", 0, "bank"), "missing"),
        (("puzzles", 0, "difficulty"), "missing"),
        (("puzzles", 0, "target_ids"), ["missing"]),
        (("puzzles", 0, "target_ids"), ["rose", "rose"]),
        (("puzzles", 0, "extra"), 1),
        (("quality",), None),
        (("quality", "extra"), 1),
        (("quality", "max_word_reuse"), 0),
        (("quality", "max_word_reuse"), True),
        (("quality", "target_similarity_threshold"), float("nan")),
        (("quality", "target_similarity_threshold"), float("inf")),
        (("quality", "target_similarity_threshold"), "0.8"),
        (("quality", "grid_similarity_threshold"), False),
        (("quality", "grid_similarity_threshold"), 0),
        (("quality", "grid_similarity_threshold"), 1.1),
        (("quality", "prohibited_words"), ["BAD!"]),
        (("quality", "prohibited_words"), ["FUEL PUMP", "fuelpump"]),
        (("quality", "prohibited_words"), [None]),
    ],
)
def test_invalid_schema_extension(garden, path, value):
    data = garden.to_dict()
    if path:
        change(data["word_search"], path, value)
    else:
        data["word_search"] = value
    result = validate_project(data)
    assert not result.valid
    assert result.issues
    assert all(issue.path.startswith("word_search") for issue in result.issues)


@pytest.mark.parametrize(
    ("field", "limit"), [("banks", MAX_BANKS), ("profiles", MAX_PROFILES), ("puzzles", MAX_PUZZLES)]
)
def test_duplicate_object_ids_and_collection_limits(garden, field, limit):
    data = garden.to_dict()
    items = data["word_search"][field]
    items.append(copy.deepcopy(items[0]))
    assert any(i.code == "duplicate_id" for i in validate_project(data).issues)
    data["word_search"][field] = [items[0]] * (limit + 1)
    assert any(i.code == "count" for i in validate_project(data).issues)


def test_geometric_fit_and_independent_errors(garden):
    data = garden.to_dict()
    data["word_search"]["profiles"][0]["width"] = 1
    data["word_search"]["profiles"][0]["height"] = 1
    data["word_search"]["puzzles"][1]["bank"] = "missing"
    data["book"]["title"] = ""
    codes = {i.code for i in validate_project(data).issues}
    assert {"cannot_fit", "reference", "type"} <= codes


def test_issue_paths_match_authored_fields(garden):
    data = garden.to_dict()
    data["word_search"]["profiles"][0]["width"] = 0
    data["word_search"]["banks"][0]["entries"][0]["display"] = None
    data["word_search"]["banks"][0]["entries"][1]["display"] = "!"
    data["word_search"]["quality"]["prohibited_words"] = ["ABC", "!"]
    paths = {issue.path for issue in validate_project(data).issues}
    assert {
        "word_search.profiles.0.width",
        "word_search.banks.0.entries.0.display",
        "word_search.banks.0.entries.1.display",
        "word_search.quality.prohibited_words.1",
    } <= paths
