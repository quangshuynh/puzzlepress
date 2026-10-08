"""Publishing metadata validation: KDP limits at their boundaries, ISBNs, disclosure."""

import pytest

from puzzlepress import validate_project
from puzzlepress.publishing import KDP_METADATA, RULES, validate_metadata
from puzzlepress.publishing.isbn import check_isbn, isbn13_check_digit
from puzzlepress.publishing.metadata import kdp_ai_answers
from puzzlepress.publishing.model import Basis, Outcome, Severity
from puzzlepress.publishing.rules import PAPERBACK_LANGUAGES
from puzzlepress.publishing_config import AiDisclosure, ContentOrigin
from tests.helpers import demo_variant
from tests.publishing_helpers import complete_section, confirm_current


def project(book: dict | None = None, mutate=None, puzzles: int | None = None, **overrides):
    data = demo_variant(puzzles=puzzles).to_dict()
    data["book"]["author"] = "Synthetic Test Author"
    data["publishing"] = complete_section(**overrides)
    data["book"].update(book or {})
    if mutate:
        mutate(data)
    return validate_project(confirm_current(data)).require_project()


def report(**kwargs):
    return validate_metadata(project(**kwargs))


def codes(result, severity: str | None = None) -> list[str]:
    return [
        f.rule.code for f in result.findings if severity is None or f.severity.value == severity
    ]


def fields(result, code: str) -> list[str | None]:
    return [f.field for f in result.findings if f.rule.code == code]


def test_complete_metadata_is_valid_with_only_review_notes():
    result = report()
    assert result.verdicts() == {
        "metadata": "valid",
        "disclosure": "complete",
        "attestations": "complete",
    }
    assert codes(result, "error") == [] and codes(result, "warning") == []
    assert codes(result, "info") == ["categories_unverified"]


def test_missing_section_blocks_and_leaves_rules_unevaluated():
    result = validate_metadata(demo_variant())
    assert result.verdicts()["metadata"] == "missing"
    assert codes(result) == ["publishing_configured"]
    outcomes = {r.rule.code: r.outcome for r in result.results}
    assert outcomes["description_length"] is Outcome.NOT_EVALUATED
    assert not result.metadata_valid and not result.attestations_complete


def test_every_rule_names_a_source_and_basis():
    for rule in RULES.values():
        assert rule.source.url.startswith(("https://kdp.amazon.com/", "docs/"))
        assert rule.basis in Basis
    kdp = {
        r.code
        for r in RULES.values()
        if r.basis is Basis.KDP_REQUIREMENT and r.scope.value not in ("interior", "cover")
    }
    assert all(RULES[c].source.url.startswith("https://kdp.amazon.com/") for c in kdp)


# ---------------------------------------------------------------- title and names


def test_title_and_subtitle_boundary():
    at = report(book={"title": "T" * 150, "subtitle": "S" * 49})
    over = report(book={"title": "T" * 150, "subtitle": "S" * 50})
    assert "title_length" not in codes(at)
    finding = next(f for f in over.findings if f.rule.code == "title_length")
    assert (finding.actual, finding.required) == (200, 199)
    assert RULES["title_length"].basis is Basis.KDP_AMBIGUOUS


@pytest.mark.parametrize("title", ["N/A", "unknown", "!!!", "<b>Puzzles</b>"])
def test_title_content_errors(title):
    assert fields(report(book={"title": title}), "title_content") == ["book.title"]


def test_title_promotional_and_generic_wording_are_warnings():
    result = report(book={"title": "Bestselling Free Word Search Book Book"})
    assert codes(result, "warning").count("title_review") == 2
    assert "title_content" not in codes(result)


def test_author_required_and_names_checked():
    assert fields(report(book={"author": None}), "author_present") == ["book.author"]
    result = report(
        book={"imprint": "n/a"},
        contributors=[
            {"role": "editor", "name": "<i>Ed</i>"},
            {"role": "author", "name": "Synthetic Test Author"},
            {"role": "illustrator", "name": "A. Artist"},
            {"role": "illustrator", "name": "a. artist"},
        ],
    )
    assert fields(result, "names_content") == ["book.imprint", "publishing.contributors.0.name"]
    assert fields(result, "contributors_review") == [
        "publishing.contributors.1",
        "publishing.contributors.3",
    ]


def test_imprint_length_boundary():
    assert "imprint_length" not in codes(report(book={"imprint": "I" * 100}))
    assert "imprint_length" in codes(report(book={"imprint": "I" * 101}))


@pytest.mark.parametrize(("tag", "ok"), [("en", True), ("en-GB", True), ("de", True),
                                          ("pl", True), ("ar", False), ("hi", False),
                                          ("zh-Hant", False), ("xx", False)])  # fmt: skip
def test_paperback_languages(tag, ok):
    assert ("language_supported" not in codes(report(book={"language": tag}))) is ok


def test_language_table_excludes_ebook_only_languages():
    assert len(PAPERBACK_LANGUAGES) == 39
    assert not {"ar", "zh", "gu", "hi", "ml", "mr", "fa", "ta"} & set(PAPERBACK_LANGUAGES)


# ---------------------------------------------------------------- description


def test_description_is_required_for_a_package():
    result = report(description=None)
    assert codes(result) == ["description_present", "categories_unverified"]
    outcomes = {r.rule.code: r.outcome for r in result.results}
    assert outcomes["description_length"] is Outcome.NOT_EVALUATED


def test_description_length_boundary():
    limit = KDP_METADATA.max_description
    assert limit == 4000
    assert "description_length" not in codes(report(description="a " * 2000))
    finding = next(
        f
        for f in report(description="ab" * 2000 + "c").findings
        if f.rule.code == "description_length"
    )
    assert (finding.actual, finding.required) == (4001, 4000)


@pytest.mark.parametrize(
    ("text", "fragment"),
    [
        ("Visit https://example.com today.", "website address"),
        ("See puzzlepress.com for more.", "website address"),
        ("Write to author@example.org.", "email address"),
        ("Call +1 (555) 123-4567.", "phone number"),
        ("Only $9.99.", "price"),
        ("Now 4.99 USD.", "price"),
        ("Please leave a review!", "request for reviews"),
        ("Calm puzzles 🧩 for evenings.", "emoji"),
        ("Calm​puzzles.", "invisible characters"),
    ],
)
def test_description_prohibited_content(text, fragment):
    found = [f.message for f in report(description=text).findings]
    assert any(fragment in m for m in found), found
    assert "description_prohibited" in codes(report(description=text), "error")


def test_description_markup_is_rejected_not_rewritten():
    result = report(description="<b>Bold</b> puzzles")
    assert codes(result, "error") == ["description_markup"]
    assert result.publishing_identity  # The authored text stays as written.
    assert project(description="<b>Bold</b> puzzles").publishing.description == (
        "<b>Bold</b> puzzles"
    )


@pytest.mark.parametrize(
    "text",
    [
        '"A delight from start to finish" - Puzzle Weekly',
        "Five stars from readers.",
        "Limited time offer.",
        "A bestselling series.",
    ],
)
def test_description_review_warnings(text):
    result = report(description=text)
    assert codes(result, "warning") == ["description_review"]
    assert codes(result, "error") == []


def test_keyword_stuffing_is_a_warning():
    text = " ".join(["Puzzle lovers love puzzle grids puzzle fun puzzle time puzzle puzzle."] * 2)
    assert "description_review" in codes(report(description=text), "warning")


@pytest.mark.parametrize(
    ("text", "claimed"),
    [
        ("Twelve word searches.", 12),
        ("Contains 20 large-print puzzles.", 20),
        ("Twenty-five grids to solve.", 25),
        ("One hundred puzzles!", 100),
    ],
)
def test_description_counts_must_match_the_book(text, claimed):
    finding = next(
        f for f in report(description=text).findings if f.rule.code == "description_claims"
    )
    assert (finding.actual, finding.required) == (claimed, 4)
    assert finding.severity is Severity.ERROR


@pytest.mark.parametrize(
    "text",
    ["Four word searches.", "4 themed puzzles.", "Each puzzle hides 8 words in a 14 x 14 grid."],
)
def test_matching_or_unrelated_numbers_are_not_claims(text):
    assert "description_claims" not in codes(report(description=text))


def test_solutions_mentioned_but_omitted():
    def omit(data):
        data["composition"]["solutions"] = {"placement": "omit"}

    result = report(description="Calm word searches. Solutions included.", mutate=omit)
    assert fields(result, "description_claims") == ["publishing.description"]
    assert "description_claims" not in codes(report(description="Solutions included."))


# ---------------------------------------------------------------- keywords and categories


def test_keyword_count_boundary():
    assert "keywords_count" not in codes(report(keywords=[f"theme {n}" for n in "abcdefg"]))
    finding = next(
        f
        for f in report(keywords=[f"theme {n}" for n in "abcdefgh"]).findings
        if f.rule.code == "keywords_count"
    )
    assert (finding.actual, finding.required) == (8, 7)


def test_keyword_format_and_duplicates():
    result = report(
        keywords=["seaside puzzles", "Seaside  Puzzles", '"coast"', "kindle unlimited", "<b>x</b>"]
    )
    assert fields(result, "keywords_format") == [
        "publishing.keywords.1",
        "publishing.keywords.2",
        "publishing.keywords.3",
        "publishing.keywords.4",
    ]


def test_keyword_variants_and_review_items_are_warnings():
    result = report(
        book={"title": "Harbour Lights"},
        keywords=["word search", "word searches", "wordsearch", "best puzzles", "book",
                  "harbour lights", "games"],
        categories=["Puzzles > Games"],
    )  # fmt: skip
    assert codes(result, "error") == []
    assert fields(result, "keywords_review") == [
        "publishing.keywords.1",
        "publishing.keywords.2",
        "publishing.keywords.3",
        "publishing.keywords.4",
        "publishing.keywords.5",
        "publishing.keywords.6",
    ]


def test_no_unsourced_keyword_length_limit_is_applied():
    """KDP's keywords page states no per-keyword length; PuzzlePress invents none."""
    long = "harbour and lighthouse word search puzzles for quiet coastal afternoons"
    assert len(long) > 50
    result = report(keywords=[long, "k" * 200])
    assert codes(result, "error") == [] and codes(result, "warning") == []
    assert "keywords_length" not in RULES
    assert not hasattr(KDP_METADATA, "keyword_field_length")


def test_no_keywords_is_only_a_note():
    result = report(keywords=[])
    assert codes(result, "info") == ["categories_unverified", "keywords_present"]
    assert result.metadata_valid


def test_category_count_format_and_status():
    three = ["A > B", "A > C", "D"]
    assert "categories_count" not in codes(report(categories=three))
    assert "categories_count" in codes(report(categories=[*three, "E > F"]))
    result = report(categories=["A >  > B", "A > B", "a > b"])
    assert fields(result, "categories_format") == [
        "publishing.categories.0",
        "publishing.categories.2",
    ]
    empty = report(categories=[])
    assert codes(empty, "warning") == ["categories_present"] and empty.metadata_valid
    unverified = next(f for f in report().findings if f.rule.code == "categories_unverified")
    assert "saved preferences" in unverified.message and unverified.severity is Severity.INFO


# ---------------------------------------------------------------- audience and classification


def test_explicit_content_must_be_answered():
    result = report(audience={"sexually_explicit": None})
    assert codes(result, "error") == ["audience_explicit"]
    assert not result.metadata_valid


def test_reading_age_consistency():
    young = {"sexually_explicit": True, "reading_age": {"minimum": 9, "maximum": 12}}
    assert "audience_reading_age" in codes(report(audience=young))
    adult = {"sexually_explicit": True, "reading_age": {"minimum": 18, "maximum": 18}}
    assert "audience_reading_age" not in codes(report(audience=adult))
    half = {"sexually_explicit": False, "reading_age": {"minimum": 9, "maximum": None}}
    assert "audience_reading_age" in codes(report(audience=half))


def test_low_content_must_be_decided_and_is_reviewed():
    assert codes(report(low_content=None), "error") == ["low_content_decided"]
    low = report(low_content=True, isbn={"mode": "none", "value": None})
    assert codes(low, "warning") == ["low_content_review"] and low.metadata_valid


# ---------------------------------------------------------------- ISBN


def test_isbn_check_digit_algorithm():
    assert isbn13_check_digit("978030640615") == "7"
    assert check_isbn("978-0-306-40615-7").digits == "9780306406157"
    assert check_isbn("979 10 90636 07 1").digits == "9791090636071"
    bad = check_isbn("978-0-306-40615-6")
    assert bad.digits is None and bad.required == "7"
    assert "ISBN-10" in (check_isbn("0-306-40615-2").problem or "")
    assert "978 or 979" in (check_isbn("9770306406157").problem or "")
    assert "13 digits" in (check_isbn("97803064061").problem or "")
    assert "Hyphens" in (check_isbn("978--0306406157").problem or "")


def test_isbn_modes():
    assert codes(report(isbn={"mode": "undecided", "value": None}), "error") == ["isbn_decided"]
    own = report(
        isbn={"mode": "own", "value": "978-0-306-40615-7"},
        book={"imprint": "Harbour Press"},
        attestations={"rights": True, "ai_disclosure": True, "metadata": True, "isbn": True},
    )
    assert codes(own, "error") == [] and codes(own, "warning") == []
    note = next(r for r in own.results if r.rule.code == "isbn_valid").note
    assert "not verified" in note
    missing = report(isbn={"mode": "own", "value": None})
    assert "isbn_valid" in codes(missing, "error")
    wrong = report(isbn={"mode": "own", "value": "978-0-306-40615-6"})
    assert fields(wrong, "isbn_valid") == ["publishing.isbn.value"]


def test_own_isbn_needs_imprint_and_its_own_attestation():
    result = report(isbn={"mode": "own", "value": "9780306406157"})
    assert fields(result, "isbn_imprint") == ["book.imprint"]
    assert fields(result, "attestations") == ["publishing.attestations.isbn"]


def test_free_isbn_imprint_note_and_eligibility():
    free = report(book={"imprint": "Harbour Press"})
    assert codes(free, "warning") == ["isbn_imprint"]
    assert "Independently published" in free.findings[0].message
    assert "isbn_eligibility" in codes(report(low_content=True))
    assert "isbn_eligibility" in codes(report(isbn={"mode": "none", "value": None}))


def test_series_and_low_content():
    series = {"title": "Coastal Puzzles", "number": 2}
    assert "series_eligibility" not in codes(report(series=series))
    low = report(series=series, low_content=True, isbn={"mode": "none", "value": None})
    assert "series_eligibility" in codes(low, "error")
    assert fields(report(series={"title": "N/A", "number": 1}), "title_content") == [
        "publishing.series.title"
    ]


# ---------------------------------------------------------------- AI disclosure and attestations


def test_unknown_provenance_blocks_disclosure():
    result = report(ai_disclosure={"text": "human", "images": "unknown", "translations": "unknown"})
    assert fields(result, "ai_disclosure_complete") == [
        "publishing.ai_disclosure.images",
        "publishing.ai_disclosure.translations",
    ]
    assert result.verdicts()["disclosure"] == "incomplete"
    assert result.metadata_valid  # Disclosure is its own verdict.


def test_ai_answers_follow_kdp_definitions():
    answers = kdp_ai_answers(
        AiDisclosure(ContentOrigin.AI_ASSISTED, ContentOrigin.AI_GENERATED, ContentOrigin.NONE)
    )
    assert answers == {
        "text": {"declared": "ai_assisted", "kdp": "not_required"},
        "images": {"declared": "ai_generated", "kdp": "disclose"},
        "translations": {"declared": "none", "kdp": "not_applicable"},
    }
    result = report(
        ai_disclosure={"text": "human", "images": "ai_generated", "translations": "none"}
    )
    assert codes(result, "info") == ["categories_unverified", "ai_disclosure_required"]
    assert result.verdicts()["disclosure"] == "complete"


def test_procedural_generation_is_never_declared_for_the_author():
    # The default is unknown: PuzzlePress never classifies content on the author's behalf.
    data = demo_variant().to_dict()
    data["publishing"] = {"version": 1}
    config = validate_project(data).require_project().publishing
    assert config.ai_disclosure == AiDisclosure()
    assert set(kdp_ai_answers(config.ai_disclosure)[k]["kdp"] for k in ("text", "images")) == {
        "undecided"
    }


def test_attestations_are_never_assumed():
    result = report(attestations={})
    assert fields(result, "attestations") == [
        "publishing.attestations.ai_disclosure",
        "publishing.attestations.metadata",
        "publishing.attestations.rights",
    ]
    assert result.verdicts()["attestations"] == "incomplete"
    assert result.metadata_valid


def test_findings_and_results_are_deterministic():
    first = report(description="Visit www.example.com", keywords=["a", "A", "best"])
    second = report(description="Visit www.example.com", keywords=["a", "A", "best"])
    assert [f.to_dict() for f in first.findings] == [f.to_dict() for f in second.findings]
    assert [r.to_dict() for r in first.results] == [r.to_dict() for r in second.results]
