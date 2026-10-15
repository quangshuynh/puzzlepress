"""Cover version 2: text layer overrides, extra layers, schema and compatibility."""

from dataclasses import replace

import pytest

from puzzlepress import validate_project
from puzzlepress.cover.build import semantic_config
from puzzlepress.cover.issues import CoverError
from puzzlepress.cover.layout import CoverCopy, cover_display, layout_cover, same_words
from puzzlepress.cover.validation import validate_cover_layout
from puzzlepress.cover_config import (
    CoverFont,
    ExtraLayer,
    LayerAlign,
    LayerPanel,
    LetterCase,
    TextLayer,
    TextRole,
)
from puzzlepress.identity import build_identity
from puzzlepress.yaml_io import dump_project, parse_project
from tests.helpers import demo_variant
from tests.test_cover_layout import CONFIG, COPY, H, W, by_role, lay, photo, roles

DIGEST = "ab" * 32
V1 = {"version": 1, "image": {"path": "cover-assets/harbour-1.jpg", "sha256": DIGEST}}


def source(cover):
    data = demo_variant().to_dict()
    data["cover"] = cover
    return data


def issues(cover):
    return [(i.path, i.code) for i in validate_project(source(cover)).issues]


def v2(**layers):
    return replace(CONFIG, version=2, text=tuple((TextRole(k), v) for k, v in layers.items()))


# ---------------------------------------------------------------- schema


def test_version_1_covers_keep_their_exact_canonical_form():
    project = validate_project(source(V1)).require_project()
    assert project.cover is not None and project.cover.version == 1
    assert "text" not in project.cover.to_dict() and "fonts" not in project.cover.to_dict()


def test_version_1_rejects_version_2_fields():
    assert issues({**V1, "text": {"title": {"visible": False}}}) == [
        ("cover.text", "requires_version_2")
    ]


def test_version_2_layers_normalize_and_round_trip():
    cover = {
        **V1,
        "version": 2,
        "fonts": [
            {
                "id": "display",
                "path": "cover-assets/fonts/display-1.ttf",
                "sha256": DIGEST,
                "license": " SIL OFL 1.1 ",
                "source": None,
            }
        ],
        "text": {
            "subtitle": {"size": 18.456, "color": "#AABBCC", "offset": {"x": 1.234, "y": -5}},
            "title": {"visible": False, "font": "display", "case": "upper"},
            "author": {},
        },
        "extra": [{"id": "tagline", "panel": "front", "text": " Sixty puzzles ", "align": "right"}],
    }
    project = validate_project(source(cover)).require_project()
    config = project.cover
    assert config is not None
    assert [role for role, _ in config.text] == [TextRole.TITLE, TextRole.SUBTITLE]
    assert config.layer(TextRole.TITLE) == TextLayer(
        visible=False, font="display", case=LetterCase.UPPER
    )
    sub = config.layer(TextRole.SUBTITLE)
    assert (sub.size, sub.color, sub.offset) == (18.46, "#aabbcc", (1.23, -5.0))
    assert config.layer(TextRole.AUTHOR).is_default
    assert config.extra == (
        ExtraLayer(
            "tagline",
            LayerPanel.FRONT,
            "Sixty puzzles",
            TextLayer(text="Sixty puzzles", align=LayerAlign.RIGHT),
        ),
    )
    assert config.fonts == (
        CoverFont("display", "cover-assets/fonts/display-1.ttf", DIGEST, "SIL OFL 1.1", None),
    )
    data = config.to_dict()
    assert data["text"] == {
        "title": {"visible": False, "font": "display", "case": "upper"},
        "subtitle": {"size": 18.46, "color": "#aabbcc", "offset": {"x": 1.23, "y": -5.0}},
    }
    assert data["extra"] == [
        {"id": "tagline", "panel": "front", "text": "Sixty puzzles", "align": "right"}
    ]
    again = parse_project(dump_project(project))
    assert again == project
    assert dump_project(again) == dump_project(project)


@pytest.mark.parametrize(
    ("cover", "expected"),
    [
        ({"text": {"title": {"font": "missing"}}}, [("cover.text.title.font", "unknown_font")]),
        ({"text": {"title": {"size": 2}}}, [("cover.text.title.size", "range")]),
        ({"text": {"title": {"size": True}}}, [("cover.text.title.size", "number")]),
        ({"text": {"title": {"color": "red"}}}, [("cover.text.title.color", "color")]),
        ({"text": {"title": {"align": "justify"}}}, [("cover.text.title.align", "choice")]),
        ({"text": {"title": {"visible": "no"}}}, [("cover.text.title.visible", "type")]),
        ({"text": {"title": {"line_spacing": 9}}}, [("cover.text.title.line_spacing", "range")]),
        (
            {"text": {"title": {"offset": {"x": 5000}}}},
            [("cover.text.title.offset.x", "range")],
        ),
        ({"text": {"back_text": {"text": "x"}}}, [("cover.text.back_text.text", "unknown_field")]),
        ({"text": {"spine": {}}}, [("cover.text.spine", "unknown_field")]),
        ({"text": {"title": {"text": "  "}}}, [("cover.text.title.text", "text")]),
        (
            {"extra": [{"id": "a", "panel": "front"}]},
            [("cover.extra.0.text", "required")],
        ),
        (
            {"extra": [{"id": "A b", "panel": "spine", "text": "x"}]},
            [("cover.extra.0.id", "id"), ("cover.extra.0.panel", "choice")],
        ),
        (
            {"fonts": [{"id": "serif", "path": "cover-assets/fonts/a-1.ttf", "sha256": DIGEST}]},
            [("cover.fonts.0.id", "id")],
        ),
        (
            {"fonts": [{"id": "a", "path": "../fonts/a.ttf", "sha256": DIGEST}]},
            [("cover.fonts.0.path", "asset_path")],
        ),
        (
            {"fonts": [{"id": "a", "path": "cover-assets/fonts/a.woff", "sha256": DIGEST}]},
            [("cover.fonts.0.path", "asset_path")],
        ),
    ],
)
def test_invalid_version_2_fields_are_reported_with_paths(cover, expected):
    assert issues({**V1, "version": 2, **cover}) == expected


def test_cover_layers_stay_outside_the_build_identity():
    base = demo_variant().to_dict()
    plain = validate_project(source(V1)).require_project()
    styled = validate_project(
        source({**V1, "version": 2, "text": {"title": {"visible": False}}})
    ).require_project()
    assert (
        build_identity(plain)
        == build_identity(styled)
        == build_identity(validate_project(base).require_project())
    )
    assert plain.book == styled.book


def test_font_provenance_is_not_cover_identity():
    font = CoverFont("display", "cover-assets/fonts/d-1.ttf", DIGEST)
    one = replace(CONFIG, version=2, fonts=(font,))
    two = replace(CONFIG, version=2, fonts=(replace(font, license="OFL", source="Somewhere"),))
    assert semantic_config(one) == semantic_config(two)
    moved = replace(one, fonts=(replace(font, path="cover-assets/fonts/other-1.ttf"),))
    assert semantic_config(moved) == semantic_config(one)


# ---------------------------------------------------------------- layout


def test_version_2_without_overrides_lays_out_exactly_like_version_1():
    assert lay(config=replace(CONFIG, version=2)).texts == lay().texts
    assert lay(config=replace(CONFIG, version=2)).photo == lay().photo


def test_hidden_title_removes_only_the_cover_text():
    layout = lay(config=v2(title=TextLayer(visible=False)))
    assert "title" not in roles(layout)
    assert {"subtitle", "author", "spine_title"} <= set(roles(layout))
    assert not validate_cover_layout(layout, W, H)
    assert cover_display(layout.config, COPY)["title"] is None
    # The title block now starts with the subtitle at the top of the type area.
    assert by_role(layout, "subtitle")[0].bounds.top == pytest.approx(
        layout.geometry.front_design.top
    )


def test_display_text_override_and_letter_case():
    layout = lay(config=v2(title=TextLayer(text="Seaside\nWord Searches", case=LetterCase.UPPER)))
    lines = [t.text for t in by_role(layout, "title")]
    assert lines[0] == "SEASIDE" and " ".join(lines[1:]) == "WORD SEARCHES"
    display = cover_display(layout.config, COPY)
    assert display["title"] == "Seaside\nWord Searches"
    assert same_words(display["title"], COPY.title)
    assert not same_words("Seaside Puzzles", COPY.title)


def test_offsets_move_text_by_exact_points():
    base = lay()
    moved = lay(config=v2(author=TextLayer(offset=(12.5, 30.0))))
    for before, after in zip(by_role(base, "author"), by_role(moved, "author"), strict=True):
        assert after.origin == (before.origin[0] + 12.5, before.origin[1] + 30.0)
        assert after.bounds.x == pytest.approx(before.bounds.x + 12.5)
        assert after.bounds.y == pytest.approx(before.bounds.y + 30.0)
    assert by_role(moved, "title") == by_role(base, "title")


def test_explicit_size_alignment_color_and_spacing():
    layer = TextLayer(
        size=30, align=LayerAlign.RIGHT, color="#ff8800", letter_spacing=2, line_spacing=1.5
    )
    layout = lay(config=v2(subtitle=layer))
    lines = by_role(layout, "subtitle")
    area = layout.geometry.front_design
    assert all(t.size == 30 and t.tracking == 2 for t in lines)
    assert all(t.bounds.right == pytest.approx(area.right) for t in lines)
    assert lines[0].color == pytest.approx((1.0, 0x88 / 255, 0.0))


def test_text_moved_out_of_the_safe_area_fails_validation_not_layout():
    layout = lay(config=v2(title=TextLayer(offset=(0, 200))))
    codes = {issue.code for issue in validate_cover_layout(layout, W, H)}
    assert "unsafe_front_text" in codes


def test_text_moved_onto_the_barcode_is_a_conflict():
    layout = lay(config=v2(imprint=TextLayer(offset=(420, 0))))
    codes = {issue.code for issue in validate_cover_layout(layout, W, H)}
    assert "barcode_region_conflict" in codes


def test_overlapping_moved_layers_are_reported():
    base = lay()
    title = by_role(base, "title")[0].bounds
    author = by_role(base, "author")[0].bounds
    layout = lay(config=v2(author=TextLayer(offset=(0, title.y - author.y))))
    assert "text_overlap" in {issue.code for issue in validate_cover_layout(layout, W, H)}


def test_explicit_size_that_cannot_fit_is_an_expected_failure():
    with pytest.raises(CoverError) as error:
        lay(config=v2(title=TextLayer(size=160)))
    assert error.value.issues[0].code == "text_overflow"


def test_extra_layers_sit_in_their_panel_and_validate():
    config = replace(
        CONFIG,
        version=2,
        extra=(
            ExtraLayer("tagline", LayerPanel.FRONT, "Sixty calm puzzles", TextLayer(size=14)),
            ExtraLayer("note", LayerPanel.BACK, "Large print", TextLayer(offset=(0, 120))),
            ExtraLayer("hidden", LayerPanel.FRONT, "Hidden", TextLayer(visible=False)),
        ),
    )
    layout = lay(config=config)
    assert "front_extra:tagline" in roles(layout) and "back_extra:note" in roles(layout)
    assert "front_extra:hidden" not in roles(layout)
    tagline = by_role(layout, "front_extra:tagline")[0]
    assert layout.geometry.front_safe.contains(tagline.bounds, 0.01)
    assert not validate_cover_layout(layout, W, H)


def test_hidden_back_text_and_imprint():
    layout = lay(config=v2(back_text=TextLayer(visible=False), imprint=TextLayer(visible=False)))
    assert "back_text" not in roles(layout) and "imprint" not in roles(layout)


def test_shading_follows_moved_text():
    base = lay()
    moved = lay(config=v2(title=TextLayer(offset=(0, -100)), subtitle=TextLayer(offset=(0, -100))))
    assert moved.photo.shade[0].core[0] == pytest.approx(base.photo.shade[0].core[0] - 100)


def test_layer_overrides_are_deterministic():
    config = v2(title=TextLayer(size=50, letter_spacing=1.25, offset=(3, -4)))
    one = layout_cover("demo", COPY, config, lay().geometry, photo())
    two = layout_cover("demo", CoverCopy(**COPY.to_dict()), config, lay().geometry, photo())
    assert one == two
