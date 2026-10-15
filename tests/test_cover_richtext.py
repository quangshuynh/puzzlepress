"""Rich text on covers: schema, canonical form, layout, PDF content and compatibility."""

import hashlib
import io
import os
import subprocess
import sys

import pytest
from pypdf import PdfReader

from puzzlepress.cover.build import render_cover
from puzzlepress.cover.issues import CoverError
from puzzlepress.cover.richtext import variants
from puzzlepress.cover_richtext import RichText, plain_equivalent
from puzzlepress.cover_validation import validate_cover
from puzzlepress.publishing.review import _content
from tests.helpers import ROOT
from tests.test_cover_design import facts, layout_codes, project, render, v3

BOX = {"id": "blurb", "type": "text", "region": "back"}
FRAME = {"x": 72, "y": 300, "width": 300, "height": 300}


def rich(*blocks):
    return {"rich": 1, "blocks": list(blocks)}


def para(*runs, **fields):
    return {**fields, "runs": [r if isinstance(r, dict) else {"text": r} for r in runs]}


def box(document, **fields):
    return {**BOX, "box": FRAME, "rich": document, "size": 12, **fields}


def lines(build, role="back_element:blurb"):
    return [t for t in build.layout.texts if t.role == role]


def pdf_text(build) -> str:
    return " ".join(PdfReader(io.BytesIO(build.pdf)).pages[0].extract_text().split())


def fonts(build) -> set[str]:
    page = PdfReader(io.BytesIO(build.pdf)).pages[0]
    names = page["/Resources"]["/Font"]
    return {str(names[key].get_object()["/BaseFont"]).split("+")[-1] for key in names}


# ------------------------------------------------------------------ schema


def test_rich_text_round_trips_in_canonical_form():
    document = rich(
        para("Inside", type="heading", align="center", space_after=6),
        para("Sixty ", {"text": "themed", "bold": True}, " puzzles", list="bullet"),
        para({"text": "Large print", "italic": True, "underline": True, "size": 14}),
        para(),  # A blank line.
        para({"text": "Color", "color": "#C03030", "font": "serif"}, line_spacing=1.5),
    )
    cover = v3([box(document)], back_text=document)
    config, issues = validate_cover(cover, True)
    assert not issues and config is not None
    element = config.elements[0]
    assert element.rich is not None and element.text == element.rich.plain()
    assert config.back_text == "Inside\nSixty themed puzzles\nLarge print\n\nColor"
    round_trip = config.to_dict()
    assert round_trip["back_text"]["blocks"][4]["runs"][0]["color"] == "#c03030"  # type: ignore[index]
    again, more = validate_cover(round_trip, True)
    assert not more and again == config and again.to_dict() == round_trip


@pytest.mark.parametrize(
    ("document", "code"),
    [
        ({"rich": 2, "blocks": [para("x")]}, "unsupported_version"),
        (rich(para({"text": "x", "html": "<b>"})), "unknown_field"),
        (rich(para({"text": "x", "font": "Comic Sans"})), "unknown_font"),
        (rich(para({"text": "x", "color": "red"})), "color"),
        (rich(para({"text": "x", "size": 400})), "range"),
        (rich(para({"text": "x\u0007"})), "text"),
        (rich(para({"text": ""})), "text"),
        (rich(para()), "text"),
        (rich(para("x", type="heading", list="bullet")), "heading_in_list"),
        (rich(para("x", space_after=500)), "range"),
        (rich(*[para("x")] * 41), "count"),
        (rich(para("x" * 601)), "text"),
    ],
)
def test_rich_text_schema_refusals(document, code):
    _, issues = validate_cover(v3([box(document)]), True)
    assert code in {issue.code for issue in issues}


def test_text_and_rich_together_and_version_1_rich_back_text_are_refused():
    _, issues = validate_cover(v3([{**box(rich(para("x"))), "text": "x"}]), True)
    assert "text_and_rich" in {i.code for i in issues}
    legacy = {
        "version": 1,
        "image": {"path": "cover-assets/a.jpg", "sha256": "a" * 64},
        "back_text": rich(para("x")),
    }
    _, issues = validate_cover(legacy, True)
    assert "requires_version_2" in {i.code for i in issues}


def test_plain_equivalence_is_detected():
    config, _ = validate_cover(v3([box(rich(para("a"), para("b")))]), True)
    assert config is not None and plain_equivalent(config.elements[0].rich)  # type: ignore[union-attr, arg-type]
    styled, _ = validate_cover(v3([box(rich(para({"text": "a", "bold": True})))]), True)
    assert styled is not None and not plain_equivalent(styled.elements[0].rich)  # type: ignore[union-attr, arg-type]


# ------------------------------------------------------------------ layout and PDF


def test_unformatted_rich_text_renders_the_plain_bytes():
    text = "Sixty themed puzzles for the long drive home.\nThree levels."
    plain = render(v3([{**BOX, "box": FRAME, "text": text, "size": 12}], back_text=text))
    document = rich(para("Sixty themed puzzles for the long drive home."), para("Three levels."))
    formatted = render(v3([box(document)], back_text=document))
    assert formatted.pdf == plain.pdf
    assert formatted.layout.texts == plain.layout.texts
    # The identity records that the source is now rich text; the drawing is the same.
    assert formatted.manifest["cover_identity"] != plain.manifest["cover_identity"]


def test_bold_italic_and_underline_style_only_the_selected_words():
    document = rich(
        para(
            "Find every ",
            {"text": "hidden", "bold": True},
            " word in ",
            {"text": "sixty", "italic": True, "underline": True},
            " grids.",
        )
    )
    build = render(v3([box(document, font="sans")]))
    parts = lines(build)
    by_text = {t.text: t for t in parts}
    assert by_text["hidden"].face == "sans-bold" and by_text["sixty"].face == "sans-italic"
    assert by_text["Find every "].face == "sans"
    # Segments share one baseline and follow each other left to right.
    assert len({round(t.origin[1], 6) for t in parts}) == 1
    ordered = sorted(parts, key=lambda t: t.bounds.x)
    assert [t.text for t in ordered] == ["Find every ", "hidden", " word in ", "sixty", " grids."]
    for left, right in zip(ordered, ordered[1:], strict=False):
        assert right.bounds.x == pytest.approx(left.bounds.right)
    assert by_text["sixty"].underline is not None and by_text["hidden"].underline is None
    underline = by_text["sixty"].underline
    assert by_text["sixty"].bounds.contains(underline, 0.001) and underline.height >= 0.75
    assert {"BitstreamVeraSans-Bold", "BitstreamVeraSans-Oblique"} <= fonts(build)
    assert "Find every hidden word in sixty grids." in pdf_text(build)


def test_mixed_sizes_share_a_line_with_room_for_the_largest():
    document = rich(para("small ", {"text": "BIG", "size": 30}, " small"), para("next line"))
    build = render(v3([box(document)]))
    parts = lines(build)
    big = next(t for t in parts if t.text == "BIG")
    small = next(t for t in parts if t.text == "small ")
    assert big.origin[1] == small.origin[1] and big.size == 30 and small.size == 12
    following = next(t for t in parts if t.text == "next line")
    assert following.bounds.top <= big.bounds.y + 0.001  # No overlap with the large run.


def test_wrapping_crosses_style_changes_and_keeps_explicit_breaks():
    words = [{"text": f"word{i} ", "bold": i % 2 == 0} for i in range(30)]
    document = rich(para(*words), para("first\nsecond"))
    build = render(v3([box(document, font="sans")]))
    parts = lines(build)
    baselines = sorted({round(t.origin[1], 3) for t in parts}, reverse=True)
    assert len(baselines) >= 4
    for baseline in baselines:
        row = [t for t in parts if round(t.origin[1], 3) == baseline]
        assert min(t.bounds.x for t in row) >= build.layout.geometry.back.x + 72 - 0.01
        assert max(t.bounds.right for t in row) <= build.layout.geometry.back.x + 372 + 0.01
    assert {"first", "second"} <= {t.text for t in parts}


def test_lists_indent_and_number_their_items():
    document = rich(
        para("One", list="number"),
        para("Two", list="number"),
        para("Note"),
        para("Again", list="number"),
        para("Dot", list="bullet"),
    )
    build = render(v3([box(document)]))
    texts = [t.text for t in lines(build)]
    assert texts == ["1.", "One", "2.", "Two", "Note", "1.", "Again", "•", "Dot"]
    parts = {t.text: t for t in lines(build)}
    assert parts["One"].bounds.x > parts["Note"].bounds.x  # Hanging indent.
    assert parts["1."].bounds.right < parts["One"].bounds.x
    assert "1. One" in pdf_text(build)


def test_alignment_and_spacing_are_per_block():
    document = rich(
        para("Left"),
        para("Centered", align="center", space_before=24),
        para("Right", align="right"),
    )
    build = render(v3([box(document)]))
    parts = {t.text: t for t in lines(build)}
    left_edge = build.layout.geometry.back.x + 72
    assert parts["Left"].bounds.x == pytest.approx(left_edge)
    assert parts["Centered"].bounds.x + parts["Centered"].bounds.width / 2 == pytest.approx(
        left_edge + 150
    )
    assert parts["Right"].bounds.right == pytest.approx(left_edge + 300)
    plain = render(v3([box(rich(para("Left"), para("Centered")))]))
    gap = {t.text: t for t in lines(plain)}
    moved = gap["Centered"].origin[1] - parts["Centered"].origin[1]
    assert moved == pytest.approx(24)


def test_headings_use_the_display_or_bold_cut():
    serif = render(v3([box(rich(para("Inside", type="heading")), font="serif")]))
    (heading,) = lines(serif)
    assert heading.face == "serif-display" and heading.size == 15
    sans = render(v3([box(rich(para("Inside", type="heading")), font="sans")]))
    assert lines(sans)[0].face == "sans-bold"


def test_missing_font_variants_fail_explicitly():
    for document in (
        rich(para({"text": "Bold serif", "bold": True, "font": "serif"})),
        rich(para({"text": "Both", "bold": True, "italic": True, "font": "sans"})),
    ):
        with pytest.raises(CoverError) as error:
            render(v3([box(document)]), issues=True)
        assert error.value.issues[0].code == "font_variant_unavailable"
    assert variants()["serif"] == ["regular", "italic"]


def test_missing_glyphs_and_overflow_are_reported():
    with pytest.raises(CoverError) as error:
        render(v3([box(rich(para("Snowman ☃")))]), issues=True)
    assert error.value.issues[0].code == "unsupported_character"
    long = rich(*[para("Sixty themed puzzles with solutions", list="bullet")] * 12)
    short = {**FRAME, "height": 100}
    assert "text_box_overflow" in layout_codes(v3([box(long, box=short)]))
    unbreakable = rich(para({"text": "W" * 40, "size": 30}))
    with pytest.raises(CoverError) as error:
        render(v3([box(unbreakable)]), issues=True)
    assert error.value.issues[0].code == "text_overflow"
    edge = {**box(rich(para("Edge"))), "box": {"x": 2, "y": 400, "width": 200, "height": 60}}
    assert "unsafe_back_text" in layout_codes(v3([edge]))


def test_rich_back_text_keeps_clear_of_the_barcode_and_feeds_publishing_plain_text():
    document = rich(
        para("Sixty themed puzzles", type="heading"),
        para("Every grid has a ", {"text": "solution", "bold": True}, "."),
    )
    built = project(v3(back_text=document, text={"back_text": {"font": "sans"}}))
    build = render_cover(built, facts(), {})
    back = [t for t in build.layout.texts if t.role == "back_text"]
    assert {t.text for t in back} >= {"Sixty themed puzzles", "solution"}
    assert built.cover is not None and built.cover.back_text == (
        "Sixty themed puzzles\nEvery grid has a solution."
    )
    contents = _content(built)
    assert "Every grid has a solution." in str(contents)
    tall = rich(*[para("A short line.", space_after=30)] * 30)
    with pytest.raises(CoverError) as error:
        render(v3(back_text=tall))
    assert error.value.issues[0].code == "text_overflow"


def test_legacy_plain_versions_are_untouched():
    for version in (1, 2):
        cover = {
            "version": version,
            "image": {"path": "cover-assets/a.jpg", "sha256": "a" * 64},
            "back_text": "Plain\ntext",
        }
        config, issues = validate_cover(cover, True)
        assert not issues and config is not None and config.back_rich is None
        assert config.to_dict()["back_text"] == "Plain\ntext"


def test_rich_text_pdf_bytes_repeat_across_processes():
    document = rich(
        para("Inside", type="heading"),
        para("Bold ", {"text": "words", "bold": True, "underline": True}, list="bullet"),
    )
    build = render(v3([box(document, font="sans")]))
    script = (
        "import hashlib,sys;sys.path.insert(0, '.');"
        "from tests.test_cover_richtext import rebuild;print(rebuild())"
    )
    for seed in ("0", "777"):
        result = subprocess.run(
            [sys.executable, "-c", script],
            capture_output=True,
            text=True,
            cwd=ROOT,
            env={**os.environ, "PYTHONHASHSEED": seed, "PYTHONPATH": str(ROOT / "src")},
            check=True,
        )
        assert result.stdout.strip() == hashlib.sha256(build.pdf).hexdigest()


def rebuild() -> str:
    """Used by the cross-process test: the same document rendered in a fresh process."""
    document = rich(
        para("Inside", type="heading"),
        para("Bold ", {"text": "words", "bold": True, "underline": True}, list="bullet"),
    )
    return hashlib.sha256(render(v3([box(document, font="sans")])).pdf).hexdigest()


def test_rich_text_document_plain_text():
    assert RichText().plain() == ""
