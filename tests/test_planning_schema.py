"""Planning document schema, normalization, identity and the planning.yaml store."""

import os
import subprocess
import sys
from dataclasses import replace
from pathlib import Path

import pytest
from planning_helpers import ROOT, complete_plan, copy_book, document, variant

from puzzlepress import load_project
from puzzlepress.errors import ProjectError
from puzzlepress.planning import (
    PlanningWriteError,
    dump_planning,
    parse_planning,
    planning_identity,
    read_planning,
    validate_planning,
    write_planning,
)
from puzzlepress.planning.model import Evidence, PlanningDocument, WordSource


def issues(data: object) -> list[tuple[str, str]]:
    found, problems = validate_planning(data)
    assert found is None
    return [(i.path, i.code) for i in problems]


def test_minimal_document_is_an_explicitly_undecided_draft() -> None:
    doc = document({"planning_version": 1})
    assert doc == PlanningDocument()
    data = doc.to_dict()
    assert data["structure"] == {
        "puzzle_type": None,
        "target_puzzles": None,
        "print_profile": None,
        "solutions": "undecided",
        "solutions_per_page": None,
        "front_matter_pages": None,
        "back_matter_pages": None,
    }
    assert data["positioning"]["familiarity"] == "undecided"  # type: ignore[index]
    assert data["difficulty"] == {"strategy": "undecided", "levels": []}
    assert data["approval"] is None


@pytest.mark.parametrize("version", [None, 0, 2, "1", True])
def test_unsupported_or_missing_versions_are_refused_before_anything_else(version: object) -> None:
    data = {"concept": {"unknown": 1}} | ({} if version is None else {"planning_version": version})
    assert issues(data) == [("planning_version", "unsupported_version")]


def test_not_a_mapping_and_unknown_fields() -> None:
    assert issues([]) == [("planning", "type")]
    found = issues(
        {
            "planning_version": 1,
            "extra": 1,
            "concept": {"summery": "x"},
            "themes": [{"id": "a", "label": "A", "colour": "red"}],
        }
    )
    assert ("extra", "unknown_field") in found
    assert ("concept.summery", "unknown_field") in found
    assert ("themes.0.colour", "unknown_field") in found


def test_types_enums_and_bounds_are_collected_together() -> None:
    found = issues(
        variant(
            structure__target_puzzles=0,
            structure__solutions="sometimes",
            structure__solutions_per_page=3,
            positioning__familiarity="expert",
            themes__0__required="yes",
            difficulty__strategy="random",
        )
    )
    assert set(found) >= {
        ("structure.target_puzzles", "number"),
        ("structure.solutions", "choice"),
        ("structure.solutions_per_page", "choice"),
        ("positioning.familiarity", "choice"),
        ("themes.0.required", "type"),
        ("difficulty.strategy", "choice"),
    }


def test_identifiers_are_unique_per_list() -> None:
    data = complete_plan()
    data["themes"].append({"id": "engines", "label": "Engines again"})  # type: ignore[union-attr]
    data["vocabulary"].append({"theme": "tools", "entries": []})  # type: ignore[union-attr]
    data["puzzles"][1]["id"] = "engines-1"  # type: ignore[index]
    found = issues(data)
    assert ("themes.2", "duplicate_id") in found
    assert ("vocabulary.2", "duplicate_id") in found
    assert ("puzzles.1", "duplicate_id") in found
    assert ("themes.0.id", "id") in issues(variant(themes__0__id="bad id"))


def test_levels_use_profile_or_settings_and_a_word_range() -> None:
    level = {
        "id": "x",
        "label": "X",
        "profile": "gentle",
        "width": 10,
        "words": {"min": 3, "max": 4},
    }
    assert ("difficulty.levels.0.profile", "profile_or_settings") in issues(
        variant(difficulty={"strategy": "gradual", "levels": [level]})
    )
    level = {"id": "x", "label": "X", "words": {"min": 5, "max": 4}}
    assert ("difficulty.levels.0.words", "range") in issues(
        variant(difficulty={"strategy": "gradual", "levels": [level]})
    )
    level = {"id": "x", "label": "X", "words": {"min": 5}}
    assert ("difficulty.levels.0.words", "required") in issues(
        variant(difficulty={"strategy": "gradual", "levels": [level]})
    )
    level = {
        "id": "x",
        "label": "X",
        "directions": ["right", "sideways", "right"],
        "words": {"min": 1, "max": 2},
    }
    found = issues(variant(difficulty={"strategy": "gradual", "levels": [level]}))
    assert ("difficulty.levels.0.directions.1", "direction") in found
    assert ("difficulty.levels.0.directions.2", "duplicate") in found


def test_direction_order_is_not_semantic() -> None:
    a = variant(difficulty__levels__0__directions=["down", "right"])
    b = variant(difficulty__levels__0__directions=["right", "down"])
    assert document(a) == document(b)
    assert document(a).to_dict()["difficulty"]["levels"][0]["directions"] == ["right", "down"]  # type: ignore[index]


def test_dates_prices_and_identifiers_are_strict() -> None:
    note = complete_plan()["research"][0]  # type: ignore[index]
    for bad in ("2026-13-01", "2026-02-30", "09/10/2026", 20261009):
        found = issues(variant(research=[{**note, "observed": bad}]))  # type: ignore[dict-item]
        assert ("research.0.observed", "date") in found
    comparable = {"id": "c", "title": "A book", "url": "https://example.com/b"}
    assert ("comparables.0.price.amount", "amount") in issues(
        variant(comparables=[{**comparable, "price": {"amount": 12.99, "currency": "USD"}}])
    )
    assert ("comparables.0.price.currency", "currency") in issues(
        variant(comparables=[{**comparable, "price": {"amount": "12.99", "currency": "usd"}}])
    )
    ok = document(
        variant(comparables=[{**comparable, "price": {"amount": "12.99", "currency": "USD"}}])
    )
    assert ok.comparables[0].price is not None and ok.comparables[0].price.amount == "12.99"


def test_unknown_values_stay_unknown_never_zero() -> None:
    doc = document(variant(comparables=[{"id": "c", "title": "A book"}]))
    record = doc.comparables[0].to_dict()
    assert record["pages"] is None and record["puzzles"] is None and record["price"] is None
    assert record["evidence"] == "unknown"
    assert doc.comparables[0].evidence is Evidence.UNKNOWN


def test_word_provenance_defaults_to_unknown_never_human() -> None:
    doc = document(variant(vocabulary=[{"theme": "engines", "entries": [{"word": "PISTON"}]}]))
    pool = doc.vocabulary[0]
    assert pool.source is WordSource.UNKNOWN
    assert pool.source_of(pool.entries[0]) is WordSource.UNKNOWN
    doc = document(
        variant(
            vocabulary=[
                {
                    "theme": "engines",
                    "source": "human",
                    "entries": [{"word": "PISTON", "source": "ai_generated"}],
                }
            ]
        )
    )
    assert doc.vocabulary[0].source_of(doc.vocabulary[0].entries[0]) is WordSource.AI_GENERATED


def test_authored_words_are_kept_exactly_even_when_invalid() -> None:
    doc = document(
        variant(
            vocabulary=[
                {"theme": "engines", "entries": [{"word": "O-Ring"}, {"word": "Fuel  pump"}]}
            ]
        )
    )
    assert [w.word for w in doc.vocabulary[0].entries] == ["O-Ring", "Fuel  pump"]
    assert ("vocabulary.0.entries.0.word", "text") in issues(
        variant(vocabulary=[{"theme": "engines", "entries": [{"word": "TAB\tHERE"}]}])
    )


def test_text_edges_are_trimmed_and_line_breaks_only_where_allowed() -> None:
    doc = document(variant(concept__summary="  Two lines\nof concept.  "))
    assert doc.concept.summary == "Two lines\nof concept."
    assert ("concept.subject", "text") in issues(variant(concept__subject="Two\nlines"))
    assert ("concept.subject", "text") in issues(variant(concept__subject="   "))


def test_prohibited_words_follow_the_quality_normalization() -> None:
    doc = document(variant(constraints={"prohibited_words": ["zeta word", "Alpha"]}))
    assert doc.constraints.prohibited_words == ("ALPHA", "ZETAWORD")
    found = issues(variant(constraints={"prohibited_words": ["bad!"]}))
    assert found and found[0][0].startswith("constraints.prohibited_words")


def test_approval_must_be_a_planning_identity() -> None:
    assert ("approval", "approval_identity") in issues(variant(approval=True))
    assert ("approval", "approval_identity") in issues(
        variant(approval="pp1-review-sha256-" + "0" * 64)
    )
    doc = document(variant(approval="pp1-planning-sha256-" + "a" * 64))
    assert doc.approval == "pp1-planning-sha256-" + "a" * 64


def test_dump_and_parse_round_trip_in_document_order() -> None:
    doc = document(complete_plan())
    text = dump_planning(doc)
    assert parse_planning(text) == doc
    keys = [line.split(":")[0] for line in text.splitlines() if line and line[0].isalpha()]
    assert keys[0] == "planning_version" and keys[-1] == "approval"
    assert dump_planning(parse_planning(text)) == text


def test_yaml_restrictions_apply_to_planning() -> None:
    for text in (
        "planning_version: 1\nplanning_version: 1\n",
        "a: &x 1\nb: *x\n",
        "planning_version: !!int 1\n",
    ):
        with pytest.raises(ProjectError) as caught:
            parse_planning(text)
        assert caught.value.issues[0].code == "yaml"


# ----------------------------------------------------------------- identity


def test_identity_ignores_formatting_comments_and_explicit_defaults() -> None:
    doc = document(complete_plan())
    text = "# comment\n" + dump_planning(doc).replace("approval: null\n", "")
    assert parse_planning(text) == doc
    explicit = complete_plan()
    explicit["themes"][1]["required"] = False  # type: ignore[index]
    assert planning_identity("b", document(explicit)) == planning_identity("b", doc)


def test_identity_excludes_approval_and_covers_content_and_book() -> None:
    doc = document(complete_plan())
    identity = planning_identity("automotive-word-search", doc)
    assert identity.startswith("pp1-planning-sha256-") and len(identity) == 20 + 64
    approved = replace(doc, approval=identity)
    assert planning_identity("automotive-word-search", approved) == identity
    assert planning_identity("another-book", doc) != identity
    for change in (
        variant(concept__summary="Different."),
        variant(themes__1__puzzles=5),
        variant(research=[]),
        variant(puzzles=list(reversed(complete_plan()["puzzles"]))),  # type: ignore[call-overload]
    ):
        assert planning_identity("automotive-word-search", document(change)) != identity


def test_identity_is_stable_across_processes_directories_and_hash_seeds(tmp_path: Path) -> None:
    book = copy_book(tmp_path, "garden-demo")
    write_planning(book, document(complete_plan()), None)
    script = (
        "from puzzlepress import load_project\n"
        "from puzzlepress.planning import read_planning, planning_identity\n"
        f"p = read_planning({str(book)!r}).document\n"
        f"print(planning_identity(load_project({str(book)!r}).project.book.id, p))\n"
    )
    results = set()
    for seed, cwd in (("0", ROOT), ("1", tmp_path), ("4242", ROOT / "docs")):
        env = {**os.environ, "PYTHONHASHSEED": seed}
        out = subprocess.run(
            [sys.executable, "-c", script],
            cwd=cwd,
            env=env,
            capture_output=True,
            text=True,
            check=True,
        )
        results.add(out.stdout.strip())
    assert results == {planning_identity("garden-demo", document(complete_plan()))}


# ----------------------------------------------------------------- store


def test_missing_planning_file_is_a_legacy_project(tmp_path: Path) -> None:
    book = copy_book(tmp_path, "garden-demo")
    loaded = read_planning(book)
    assert loaded.document is None and loaded.revision is None
    assert load_project(book).project.book.id == "garden-demo"


def test_write_creates_replaces_and_checks_revisions(tmp_path: Path) -> None:
    book = copy_book(tmp_path, "garden-demo")
    before = (book / "book.yaml").read_bytes()
    doc = document(complete_plan())
    with pytest.raises(PlanningWriteError) as caught:
        write_planning(book, doc, "sha256-" + "0" * 64)
    assert caught.value.code == "source_changed"
    assert not (book / "planning.yaml").exists()
    saved = write_planning(book, doc, None)
    assert saved.document == doc and saved.revision is not None
    with pytest.raises(PlanningWriteError):
        write_planning(book, doc, None)  # Created meanwhile: never overwritten blindly.
    edited = replace(doc, concept=replace(doc.concept, subject="Engines"))
    again = write_planning(book, edited, saved.revision)
    assert again.document == edited and again.revision != saved.revision
    with pytest.raises(PlanningWriteError):
        write_planning(book, doc, saved.revision)  # Stale revision.
    assert read_planning(book).document == edited
    assert (book / "book.yaml").read_bytes() == before
    assert not [p for p in book.iterdir() if p.name.startswith(".puzzlepress-")]


def test_external_edit_between_open_and_save_is_detected(tmp_path: Path) -> None:
    book = copy_book(tmp_path, "garden-demo")
    write_planning(book, document(complete_plan()), None)
    loaded = read_planning(book)
    assert loaded.document is not None
    path = book / "planning.yaml"
    path.write_bytes(path.read_bytes() + b"\n# edited elsewhere\n")
    with pytest.raises(PlanningWriteError) as caught:
        write_planning(book, loaded.document, loaded.revision)
    assert caught.value.code == "source_changed"
    assert path.read_bytes().endswith(b"# edited elsewhere\n")


def test_invalid_planning_file_reports_issues(tmp_path: Path) -> None:
    book = copy_book(tmp_path, "garden-demo")
    (book / "planning.yaml").write_text("planning_version: 1\nthemes: 3\n", encoding="utf-8")
    with pytest.raises(ProjectError) as caught:
        read_planning(book)
    assert [(i.path, i.code) for i in caught.value.issues] == [("themes", "count")]
    (book / "planning.yaml").write_bytes(b"\xff\xfe")
    with pytest.raises(ProjectError):
        read_planning(book)


def test_planning_directory_is_refused(tmp_path: Path) -> None:
    book = copy_book(tmp_path, "garden-demo")
    (book / "planning.yaml").mkdir()
    with pytest.raises(ProjectError) as caught:
        read_planning(book)
    assert caught.value.issues[0].code == "not_file"


def test_planning_symlink_is_refused(tmp_path: Path) -> None:
    book = copy_book(tmp_path, "garden-demo")
    target = tmp_path / "elsewhere.yaml"
    target.write_text("planning_version: 1\n", encoding="utf-8")
    try:
        (book / "planning.yaml").symlink_to(target)
    except OSError:
        pytest.skip("Creating symlinks requires OS permission on this host")
    with pytest.raises(ProjectError):
        read_planning(book)
