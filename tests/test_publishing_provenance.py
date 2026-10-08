"""Provenance record, KDP metadata record and the human submission checklist."""

import json

import pytest

from puzzlepress import load_project
from puzzlepress.publishing.provenance import provenance_record
from puzzlepress.publishing.readiness import evaluate_readiness
from puzzlepress.publishing.submission import checklist_markdown, kdp_metadata
from tests.cover_helpers import LEAKS, photo_bytes
from tests.publishing_helpers import DESCRIPTION, publishing_project

FORBIDDEN_CLAIMS = (
    "amazon approved",
    "approved by amazon",
    "guaranteed",
    "copyright verified",
    "ownership verified",
    "legally certified",
    "has been submitted",
    "was submitted",
    "published on amazon",
)


def evaluate(source, output):
    return evaluate_readiness(load_project(source).project, source, output)


@pytest.fixture(scope="module")
def ready(tmp_path_factory):
    source, output = publishing_project(
        tmp_path_factory.mktemp("provenance"), photo=photo_bytes(5400, 3600, private=True)
    )
    return source, output, evaluate(source, output)


def test_machine_facts_and_author_declarations_are_separate(ready):
    source, output, report = ready
    record = provenance_record(report)
    facts, declared = record["machine_facts"], record["author_declarations"]
    interior = json.loads((output / "interior.json").read_text(encoding="utf-8"))
    cover = json.loads((output / "cover.json").read_text(encoding="utf-8"))
    assert facts["interior"]["interior_identity"] == interior["interior_identity"]
    assert facts["interior"]["pdf_sha256"] == interior["pdf"]["sha256"]
    assert facts["cover"]["cover_identity"] == cover["cover_identity"]
    assert facts["cover"]["photograph"]["sha256"] == cover["photo"]["sha256"]
    assert facts["publishing_identity"] == report.metadata.publishing_identity
    assert "no machine-learning model" in facts["puzzles"]["generator"]
    assert facts["puzzles"]["count"] == 16
    assert declared["ai_disclosure"]["images"] == {"declared": "human", "kdp": "not_required"}
    assert [c["name"] for c in declared["confirmations"]] == ["rights", "ai_disclosure", "metadata"]
    assert all(c["confirmed"] for c in declared["confirmations"])
    assert any("do not prove authorship, copyright" in limit for limit in record["limits"])


def test_no_paths_or_camera_metadata_reach_the_records(ready):
    source, output, report = ready
    texts = [
        json.dumps(provenance_record(report)),
        json.dumps(kdp_metadata(report)),
        checklist_markdown(report),
    ]
    for text in texts:
        assert str(source) not in text and str(output) not in text
        assert "photo_path" not in text and "cover-assets" not in text
        assert not any(leak.decode() in text for leak in LEAKS)
        assert "GPS" not in text.replace("EXIF, GPS, XMP", "")


def test_metadata_record_is_exactly_as_authored(ready):
    _, _, report = ready
    data = kdp_metadata(report)
    assert data["description"] == DESCRIPTION
    assert data["keywords"] == ["seaside puzzles", "coastal vocabulary", "large print activity"]
    assert data["categories"] == [
        {
            "path": "Humor & Entertainment > Puzzles & Games > Word Search",
            "status": "saved_preference_not_verified_in_kdp",
        }
    ]
    assert data["isbn"] == {
        "mode": "kdp_free",
        "value": None,
        "status": "assigned_by_kdp_during_setup",
    }
    assert data["imprint"] == {"authored": None, "kdp_listing": "Independently published"}
    assert data["language"] == {"tag": "en", "kdp_name": "English"}
    assert data["print"]["page_count"] == 29


def test_checklist_lists_human_steps_without_claiming_them(ready):
    _, _, report = ready
    text = checklist_markdown(report)
    assert text.startswith("# KDP paperback checklist: ")
    assert "Nothing on this list has been done in KDP" in text
    assert "- [ ] Book title: Seaside Word Searches" in text
    assert "    1. seaside puzzles\n    2. coastal vocabulary" in text
    assert "    > Solutions are at the back." in text
    for step in (
        "Print Previewer",
        "printed proof",
        "Paperback cover finish",
        "Trim size: 8.5 x 11 in",
        "Ink and paper: black ink on white paper",
        "No bleed",
        "free KDP ISBN",
        "Submit for publishing yourself",
    ):
        assert step in text, step
    assert "- [x]" not in text
    lowered = text.casefold()
    assert not any(claim in lowered for claim in FORBIDDEN_CLAIMS)
    assert checklist_markdown(report) == text


def test_checklist_marks_undecided_values(tmp_path):
    source, output = publishing_project(
        tmp_path,
        cover=False,
        isbn={"mode": "undecided", "value": None},
        low_content=None,
        ai_disclosure={"text": "unknown", "images": "ai_generated", "translations": "none"},
        attestations={},
    )
    report = evaluate(source, output)
    text = checklist_markdown(report)
    assert "ISBN: UNDECIDED" in text and "Low-content book: UNDECIDED" in text
    assert "Text: not yet declared (DECIDE BEFORE SUBMITTING)" in text
    assert "Images: AI-generated (disclose as AI-generated)" in text
    assert "- NOT CONFIRMED: I hold the rights" in text
    assert "BLOCKING [isbn_decided]" in text


def test_own_isbn_is_shown_with_its_imprint(tmp_path):
    source, output = publishing_project(
        tmp_path,
        cover=False,
        isbn={"mode": "own", "value": "978-0-306-40615-7"},
    )
    text = checklist_markdown(evaluate(source, output))
    assert "use my own ISBN 978-0-306-40615-7 with imprint MISSING" in text
    assert "- NOT CONFIRMED: My ISBN is registered" in text
