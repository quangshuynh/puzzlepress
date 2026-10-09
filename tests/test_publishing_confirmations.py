"""Identity-bound confirmations: what each covers, staleness, revert, legacy, determinism."""

import copy
import json
import os
import subprocess
import sys

import pytest

from puzzlepress import validate_project
from puzzlepress.publishing import validate_metadata
from puzzlepress.publishing.metadata import confirmations
from puzzlepress.publishing.review import COVERS, review_identity
from puzzlepress.publishing_config import CONFIRMATIONS, REVIEW_IDENTITY
from tests.helpers import ROOT, demo_variant
from tests.publishing_helpers import complete_section, confirm_current

PHOTO = "cover-assets/harbour-" + "a" * 12 + ".jpg"


def book() -> dict:
    """A composed book with a cover section and every confirmation given (synthetic)."""
    data = demo_variant().to_dict()
    data["book"]["author"] = "Synthetic Test Author"
    data["book"]["imprint"] = "Harbour Press"
    data["cover"] = {
        "version": 1,
        "image": {"path": PHOTO, "sha256": "a" * 64},
        "back_text": "Quiet seaside puzzles.",
    }
    data["publishing"] = complete_section(
        isbn={"mode": "own", "value": "9780306406157"},
        attestations={"rights": True, "ai_disclosure": True, "metadata": True, "isbn": True},
    )
    return confirm_current(data)


def states(data: dict) -> dict[str, str]:
    project = validate_project(data).require_project()
    return {c.name: c.state for c in confirmations(project)}


def stale_after(edit) -> set[str]:
    data = book()
    assert set(states(data).values()) == {"confirmed"}
    edit(data)
    return {name for name, state in states(data).items() if state == "stale"}


def puzzle(data: dict) -> dict:
    return data["word_search"]["puzzles"][0]


def bank_entry(data: dict) -> dict:
    return data["word_search"]["banks"][0]["entries"][0]


EDITS = {
    "description": (
        lambda d: d["publishing"].update(description="A different description."),
        {"metadata", "ai_disclosure"},
    ),
    "keyword": (
        lambda d: d["publishing"]["keywords"].append("tide pool words"),
        {"metadata"},
    ),
    "keyword order": (
        lambda d: d["publishing"]["keywords"].reverse(),
        {"metadata"},
    ),
    "category": (
        lambda d: d["publishing"].update(categories=["Games & Activities > Word Search"]),
        {"metadata"},
    ),
    "contributor": (
        lambda d: d["publishing"].update(contributors=[{"role": "editor", "name": "A. Editor"}]),
        {"metadata"},
    ),
    "audience": (
        lambda d: d["publishing"]["audience"].update(reading_age={"minimum": 9, "maximum": 12}),
        {"metadata"},
    ),
    "edition": (lambda d: d["publishing"].update(edition=2), {"metadata"}),
    "series": (
        lambda d: d["publishing"].update(series={"title": "Harbour Puzzles", "number": 1}),
        {"metadata"},
    ),
    "title": (lambda d: d["book"].update(title="Renamed"), {"metadata", "isbn"}),
    "subtitle": (lambda d: d["book"].update(subtitle="A new subtitle"), {"metadata", "isbn"}),
    "author": (lambda d: d["book"].update(author="Another Author"), {"metadata", "isbn"}),
    "language": (lambda d: d["book"].update(language="fr"), {"metadata"}),
    "imprint": (lambda d: d["book"].update(imprint="Other Press"), {"isbn"}),
    "isbn": (
        lambda d: d["publishing"]["isbn"].update(value="9781861972712"),
        {"isbn"},
    ),
    "photograph": (
        lambda d: d["cover"]["image"].update(sha256="b" * 64),
        {"rights", "ai_disclosure"},
    ),
    "cover text": (
        lambda d: d["cover"].update(back_text="Other words."),
        {"rights", "ai_disclosure"},
    ),
    "word list": (
        lambda d: bank_entry(d).update(display=bank_entry(d)["display"] + "S"),
        {"rights", "ai_disclosure"},
    ),
    "puzzle title": (
        lambda d: puzzle(d).update(title="Retitled"),
        {"rights", "ai_disclosure"},
    ),
    "matter text": (
        lambda d: d["composition"]["front_matter"][1].update(text="Another notice."),
        {"rights", "ai_disclosure"},
    ),
    "ai disclosure": (
        lambda d: d["publishing"]["ai_disclosure"].update(images="ai_generated"),
        {"ai_disclosure"},
    ),
}

UNRELATED = {
    "crop": lambda d: d["cover"].update(crop={"x": 0.3, "y": 0.6, "zoom": 1.5}),
    "cover design": lambda d: d["cover"].update(background="#000000", legibility="panel"),
    "build seed": lambda d: d["build"].update(seed=d["build"]["seed"] + 1),
    "solutions per page": lambda d: d["composition"]["solutions"].update(per_page=4),
    "puzzle order": lambda d: d["word_search"]["puzzles"].reverse(),
    "notes": lambda d: d["publishing"].update(notes="Remember the proof."),
    "low content": lambda d: d["publishing"].update(low_content=None),
    "output directory": lambda d: d["output"].update(directory="../elsewhere"),
    "book description (build field)": lambda d: d["book"].update(description="Internal."),
}


@pytest.mark.parametrize("case", sorted(EDITS))
def test_an_edit_stales_exactly_the_confirmations_that_cover_it(case):
    edit, expected = EDITS[case]
    assert stale_after(edit) == expected


@pytest.mark.parametrize("case", sorted(UNRELATED))
def test_unrelated_edits_keep_every_confirmation(case):
    assert stale_after(UNRELATED[case]) == set()


def test_a_photograph_change_never_touches_the_interior_identity():
    from puzzlepress.identity import build_identity

    data = book()
    before = validate_project(data).require_project()
    data["cover"]["image"]["sha256"] = "b" * 64
    after = validate_project(data).require_project()
    assert build_identity(after) == build_identity(before)
    assert {c.name for c in confirmations(after) if c.state == "stale"} == {
        "rights",
        "ai_disclosure",
    }


def test_confirming_the_current_content():
    data = book()
    project = validate_project(data).require_project()
    for c in confirmations(project):
        assert c.state == "confirmed" and c.confirmed == c.current
        assert REVIEW_IDENTITY.fullmatch(c.current)
        assert c.to_dict()["covers"] == COVERS[c.name]
    assert validate_metadata(project).verdicts()["attestations"] == "complete"


def test_a_stale_confirmation_blocks_and_says_why():
    data = book()
    data["publishing"]["keywords"].append("tide pool words")
    result = validate_metadata(validate_project(data).require_project())
    assert result.verdicts()["attestations"] == "incomplete"
    (finding,) = [f for f in result.findings if f.rule.code == "attestations"]
    assert finding.field == "publishing.attestations.metadata"
    assert finding.message.startswith("Review again: The title, author and other book details")
    assert "changed after you confirmed it" in finding.message
    stale = next(c for c in result.confirmations if c.name == "metadata")
    assert stale.state == "stale" and stale.confirmed != stale.current


def test_reverting_to_the_exact_reviewed_content_restores_the_confirmation():
    """Identity semantics, not time: the stored identity names content, not a moment."""
    data = book()
    original = data["publishing"]["description"]
    data["publishing"]["description"] = "Edited."
    assert states(data)["metadata"] == "stale"
    data["publishing"]["description"] = original
    assert set(states(data).values()) == {"confirmed"}


def test_confirming_again_records_the_new_identity():
    data = book()
    data["publishing"]["keywords"].append("tide pool words")
    project = validate_project(data).require_project()
    data["publishing"]["attestations"]["metadata"] = review_identity(project, "metadata")
    assert set(states(data).values()) == {"confirmed"}


def test_unconfirmed_and_not_required_confirmations():
    data = book()
    data["publishing"]["attestations"]["rights"] = None
    data["publishing"]["isbn"] = {"mode": "kdp_free", "value": None}
    project = validate_project(data).require_project()
    by_name = {c.name: c for c in confirmations(project)}
    assert by_name["rights"].state == "unconfirmed" and by_name["rights"].required
    assert not by_name["isbn"].required  # Only an own ISBN needs its confirmation.
    result = validate_metadata(project)
    assert [f.field for f in result.findings if f.rule.code == "attestations"] == [
        "publishing.attestations.rights"
    ]


def test_another_books_confirmation_does_not_apply():
    data = book()
    data["book"]["id"] = "another-book"
    assert set(states(data).values()) == {"stale"}


def test_legacy_boolean_confirmations_never_count():
    data = book()
    data["publishing"]["version"] = 1
    data["publishing"]["attestations"] = {
        "rights": True,
        "ai_disclosure": True,
        "metadata": True,
        "isbn": True,
    }
    project = validate_project(data).require_project()
    assert {c.state for c in confirmations(project)} == {"legacy"}
    result = validate_metadata(project)
    assert result.verdicts()["attestations"] == "incomplete"
    findings = [f for f in result.findings if f.rule.code == "attestations"]
    assert len(findings) == 4
    assert all("publishing version 1" in f.message for f in findings)
    assert all(f.action.startswith("Upgrade the publishing section") for f in findings)
    upgraded = project.publishing.upgraded()
    assert upgraded.attestations.to_dict() == dict.fromkeys(CONFIRMATIONS)
    data["publishing"] = upgraded.to_dict()
    assert set(states(data).values()) == {"unconfirmed"}


def test_version_1_false_is_simply_unconfirmed():
    data = book()
    data["publishing"]["version"] = 1
    data["publishing"]["attestations"] = dict.fromkeys(CONFIRMATIONS, False)
    assert set(states(data).values()) == {"unconfirmed"}


def test_review_identities_are_canonical_and_never_include_confirmations():
    data = book()
    project = validate_project(data).require_project()
    reordered = json.loads(json.dumps(data, sort_keys=True))  # Mapping order differs.
    again = validate_project(reordered).require_project()
    assert [review_identity(project, n) for n in CONFIRMATIONS] == [
        review_identity(again, n) for n in CONFIRMATIONS
    ]
    # Confirming one statement never stales another (confirmations are not content).
    cleared = copy.deepcopy(data)
    cleared["publishing"]["attestations"] = dict.fromkeys(CONFIRMATIONS)
    plain = validate_project(cleared).require_project()
    assert [review_identity(plain, n) for n in CONFIRMATIONS] == [
        review_identity(project, n) for n in CONFIRMATIONS
    ]
    assert len({review_identity(project, n) for n in CONFIRMATIONS}) == 4


SCRIPT = """
import json, sys
from puzzlepress import load_project
from puzzlepress.publishing.review import review_identity
project = load_project(sys.argv[1]).project
print(json.dumps([review_identity(project, n)
      for n in ("rights", "ai_disclosure", "metadata", "isbn")]))
"""


def test_review_identities_match_across_processes_hash_seeds_and_directories(tmp_path):
    from puzzlepress import load_project

    source = ROOT / "books" / "publishing-demo"
    project = load_project(source).project
    expected = [review_identity(project, n) for n in CONFIRMATIONS]
    for seed, cwd in (("0", tmp_path), ("4242", ROOT)):
        env = {**os.environ, "PYTHONHASHSEED": seed, "PYTHONPATH": str(ROOT / "src")}
        result = subprocess.run(
            [sys.executable, "-c", SCRIPT, str(source)],
            capture_output=True,
            text=True,
            cwd=cwd,
            env=env,
            check=True,
        )
        assert json.loads(result.stdout) == expected
