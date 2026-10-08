"""Publishing section schema: versioning, bounds, normalization and identity boundaries."""

import pytest

from puzzlepress import validate_project
from puzzlepress.identity import build_identity
from puzzlepress.publishing import publishing_identity
from puzzlepress.publishing_config import ContentOrigin, IsbnMode, PublishingConfig
from puzzlepress.yaml_io import dump_project, parse_project
from tests.helpers import demo_variant
from tests.publishing_helpers import complete_section


def base() -> dict:
    return demo_variant().to_dict()


def issues(section: object, data: dict | None = None) -> list[tuple[str, str]]:
    data = data or base()
    data["publishing"] = section
    return [(i.path, i.code) for i in validate_project(data).issues]


def project(**overrides: object):
    data = base()
    data["publishing"] = complete_section(**overrides)
    return validate_project(data).require_project()


def test_absent_section_is_omitted_and_changes_nothing():
    plain = demo_variant()
    assert plain.publishing is None and "publishing" not in plain.to_dict()
    assert publishing_identity(plain) is None


def test_minimal_section_normalizes_to_explicit_undecided_values():
    data = base()
    data["publishing"] = {"version": 1}
    config = validate_project(data).require_project().publishing
    assert config == PublishingConfig()
    assert config.isbn.mode is IsbnMode.UNDECIDED
    assert config.ai_disclosure.text is ContentOrigin.UNKNOWN
    assert config.audience.sexually_explicit is None and config.low_content is None
    assert not any(config.attestations.to_dict().values())
    explicit = base()
    explicit["publishing"] = config.to_dict()
    assert validate_project(explicit).require_project() == validate_project(data).require_project()


@pytest.mark.parametrize("version", [2, 0, "1", True, None])
def test_unsupported_versions_are_rejected(version):
    assert issues({"version": version}) == [("publishing.version", "unsupported_version")]


def test_missing_version_and_non_mapping():
    assert issues({}) == [("publishing.version", "unsupported_version")]
    assert issues(["x"]) == [("publishing", "type")]


def test_requires_composition():
    data = base()
    del data["composition"]
    assert ("publishing", "requires_composition") in issues({"version": 1}, data)


def test_unknown_fields_are_errors_at_every_level():
    found = issues(
        {
            "version": 1,
            "price": 9.99,
            "isbn": {"mode": "own", "number": "x"},
            "audience": {"adult": True},
            "attestations": {"approved_at": "2026-10-08"},
        }
    )
    assert ("publishing.price", "unknown_field") in found
    assert ("publishing.isbn.number", "unknown_field") in found
    assert ("publishing.audience.adult", "unknown_field") in found
    assert ("publishing.attestations.approved_at", "unknown_field") in found


@pytest.mark.parametrize(
    ("section", "expected"),
    [
        ({"description": "   "}, ("publishing.description", "text")),
        ({"description": "a\tb"}, ("publishing.description", "text")),
        ({"description": "x" * 10_001}, ("publishing.description", "text")),
        ({"description": 12}, ("publishing.description", "text")),
        ({"keywords": "word search"}, ("publishing.keywords", "count")),
        ({"keywords": ["ok", ""]}, ("publishing.keywords.1", "text")),
        ({"keywords": ["two\nlines"]}, ("publishing.keywords.0", "text")),
        ({"keywords": ["k"] * 21}, ("publishing.keywords", "count")),
        ({"categories": ["x" * 301]}, ("publishing.categories.0", "text")),
        ({"low_content": "no"}, ("publishing.low_content", "type")),
        (
            {"audience": {"sexually_explicit": "yes"}},
            ("publishing.audience.sexually_explicit", "type"),
        ),
        (
            {"audience": {"reading_age": {"minimum": 12, "maximum": 6}}},
            ("publishing.audience.reading_age", "range"),
        ),
        (
            {"audience": {"reading_age": {"minimum": 19}}},
            ("publishing.audience.reading_age.minimum", "number"),
        ),
        ({"edition": 0}, ("publishing.edition", "number")),
        ({"edition": True}, ("publishing.edition", "number")),
        ({"series": {"title": "Coast", "number": 1.5}}, ("publishing.series.number", "number")),
        ({"series": {"number": 2}}, ("publishing.series.title", "text")),
        (
            {"contributors": [{"role": "ghost", "name": "A"}]},
            ("publishing.contributors.0.role", "choice"),
        ),
        ({"contributors": [{"role": "editor"}]}, ("publishing.contributors.0.name", "text")),
        ({"isbn": {"mode": "free"}}, ("publishing.isbn.mode", "choice")),
        (
            {"isbn": {"mode": "kdp_free", "value": "9780306406157"}},
            ("publishing.isbn.value", "isbn_value_unexpected"),
        ),
        ({"ai_disclosure": {"text": "none"}}, ("publishing.ai_disclosure.text", "choice")),
        ({"ai_disclosure": {"images": "ai"}}, ("publishing.ai_disclosure.images", "choice")),
        ({"attestations": {"rights": "true"}}, ("publishing.attestations.rights", "type")),
        ({"notes": "x" * 2001}, ("publishing.notes", "text")),
    ],
)
def test_schema_rejects_uninterpretable_values(section, expected):
    assert expected in issues({"version": 1, **section})


def test_kdp_limits_are_not_schema_errors():
    # Eight keywords, four categories and a long description still save; KDP
    # limits are reported by publishing validation with their source.
    config = project(
        keywords=[f"keyword {n}" for n in range(8)],
        categories=["A > B", "C > D", "E > F", "G > H"],
        description="x" * 5000,
        isbn={"mode": "own", "value": "not an isbn"},
    ).publishing
    assert len(config.keywords) == 8 and config.isbn.value == "not an isbn"


def test_text_is_trimmed_but_otherwise_preserved():
    config = project(
        description="  Line one.\n\nLine two, with ünïcode.  ",
        isbn={"mode": "own", "value": " 978-0-306-40615-7 "},
    ).publishing
    assert config.description == "Line one.\n\nLine two, with ünïcode."
    assert config.isbn.value == "978-0-306-40615-7"


def test_yaml_round_trip_and_canonical_bytes():
    valid = project(contributors=[{"role": "editor", "name": "B. Editor"}])
    text = dump_project(valid)
    assert parse_project(text) == valid
    assert dump_project(parse_project(text)) == text


def test_publishing_never_changes_build_identity():
    plain = demo_variant()
    first = project()
    second = project(keywords=["different"], description="Another description.")
    assert build_identity(plain) == build_identity(first) == build_identity(second)


def test_publishing_identity_covers_metadata_and_referenced_book_details():
    first = project()
    assert publishing_identity(first).startswith("pp1-publishing-sha256-")
    assert publishing_identity(first) == publishing_identity(project())
    assert publishing_identity(project(keywords=["changed"])) != publishing_identity(first)
    attested = project(attestations={"rights": False, "ai_disclosure": True, "metadata": True})
    assert publishing_identity(attested) != publishing_identity(first)
    data = base()
    data["publishing"] = complete_section()
    data["book"]["title"] = "Renamed"
    assert publishing_identity(validate_project(data).require_project()) != publishing_identity(
        first
    )
