"""Cover section schema: normalization, round trip, identity boundary and rejection."""

import math

import pytest

from puzzlepress import validate_project
from puzzlepress.cover_config import CoverLayoutKind, Legibility, SpineText, TextTone
from puzzlepress.identity import build_identity
from puzzlepress.yaml_io import dump_project, parse_project
from tests.helpers import demo_variant

DIGEST = "ab" * 32
MINIMAL = {"version": 1, "image": {"path": "cover-assets/harbour-1.jpg", "sha256": DIGEST}}


def with_cover(cover):
    def mutate(data):
        data["cover"] = cover

    return mutate


def source(cover):
    data = demo_variant().to_dict()
    data["cover"] = cover
    return data


def issues(cover, **changes):
    data = source(cover)
    data.update(changes)
    return [(i.path, i.code) for i in validate_project(data).issues]


def test_minimal_cover_normalizes_explicit_defaults():
    cover = demo_variant(with_cover(MINIMAL)).cover
    assert cover is not None
    assert cover.layout is CoverLayoutKind.FULL_WRAP
    assert (cover.crop.x, cover.crop.y, cover.crop.zoom) == (0.5, 0.5, 1.0)
    assert cover.legibility is Legibility.SHADE and cover.spine_text is SpineText.AUTO
    assert cover.type.tone is TextTone.LIGHT and cover.back_text is None
    assert cover.to_dict() == {
        "version": 1,
        "layout": "full_wrap",
        "image": MINIMAL["image"],
        "crop": {"x": 0.5, "y": 0.5, "zoom": 1.0},
        "type": {"style": "editorial", "position": "top", "align": "center", "tone": "light"},
        "legibility": "shade",
        "background": "#26302b",
        "spine_text": "auto",
    }


def test_full_cover_round_trips_through_canonical_yaml():
    full = {
        **MINIMAL,
        "layout": "front_photo",
        "crop": {"x": 0.123456, "y": 1, "zoom": 2.5},
        "type": {"style": "bold", "position": "bottom", "align": "left", "tone": "dark"},
        "legibility": "panel",
        "background": "#A0B1C2",
        "spine_text": "none",
        "back_text": "  Forty quiet puzzles.\nFor slow mornings.  ",
    }
    project = demo_variant(with_cover(full))
    cover = project.cover
    assert cover is not None
    # Crop values normalize to four decimals; colors to lowercase; text is trimmed.
    assert (cover.crop.x, cover.crop.y, cover.crop.zoom) == (0.1235, 1.0, 2.5)
    assert cover.background == "#a0b1c2"
    assert cover.back_text == "Forty quiet puzzles.\nFor slow mornings."
    assert parse_project(dump_project(project)) == project


def test_cover_never_changes_build_identity():
    plain = demo_variant()
    covered = demo_variant(with_cover(MINIMAL))
    moved = demo_variant(with_cover({**MINIMAL, "crop": {"x": 0.1}}))
    assert build_identity(plain) == build_identity(covered) == build_identity(moved)
    assert "cover" not in plain.to_dict() and "cover" in covered.to_dict()


def test_cover_requires_composition():
    data = source(MINIMAL)
    del data["composition"]
    assert [(i.path, i.code) for i in validate_project(data).issues] == [
        ("cover", "requires_composition")
    ]


@pytest.mark.parametrize(
    "path",
    [
        "/abs/photo.jpg",
        "C:/photo.jpg",
        "cover-assets\\photo.jpg",
        "cover-assets/../book.jpg",
        "cover-assets/sub/photo.jpg",
        "other/photo.jpg",
        "photo.jpg",
        "cover-assets/Photo.jpg",
        "cover-assets/photo.gif",
        "cover-assets/photo.jpeg",
        "cover-assets/-photo.jpg",
        "cover-assets/" + "a" * 200 + ".jpg",
        7,
    ],
)
def test_asset_paths_must_stay_portable_inside_cover_assets(path):
    cover = {**MINIMAL, "image": {"path": path, "sha256": DIGEST}}
    assert issues(cover) == [("cover.image.path", "asset_path")]


@pytest.mark.parametrize(
    ("crop", "expected"),
    [
        ({"x": -0.01}, [("cover.crop.x", "crop_out_of_bounds")]),
        ({"y": 1.01}, [("cover.crop.y", "crop_out_of_bounds")]),
        ({"zoom": 0.99}, [("cover.crop.zoom", "crop_invalid")]),
        ({"zoom": 4.01}, [("cover.crop.zoom", "crop_invalid")]),
        ({"x": math.nan}, [("cover.crop.x", "crop_invalid")]),
        ({"x": math.inf}, [("cover.crop.x", "crop_invalid")]),
        ({"x": True}, [("cover.crop.x", "crop_invalid")]),
        ({"x": "0.5"}, [("cover.crop.x", "crop_invalid")]),
        ({"left": 0}, [("cover.crop.left", "unknown_field")]),
    ],
)
def test_invalid_crops_are_rejected(crop, expected):
    assert issues({**MINIMAL, "crop": crop}) == expected


def test_crop_bounds_are_inclusive():
    cover = demo_variant(with_cover({**MINIMAL, "crop": {"x": 0, "y": 1, "zoom": 4}})).cover
    assert cover is not None and (cover.crop.x, cover.crop.y, cover.crop.zoom) == (0, 1, 4)


@pytest.mark.parametrize(
    ("cover", "expected"),
    [
        ({"version": 1}, [("cover.image", "required")]),
        ({**MINIMAL, "version": 3}, [("cover.version", "unsupported_version")]),
        ({"image": MINIMAL["image"]}, [("cover.version", "unsupported_version")]),
        (
            {**MINIMAL, "image": {"path": "cover-assets/a.jpg", "sha256": "AB" * 32}},
            [("cover.image.sha256", "digest")],
        ),
        ({**MINIMAL, "layout": "collage"}, [("cover.layout", "choice")]),
        ({**MINIMAL, "type": {"style": "script"}}, [("cover.type.style", "choice")]),
        ({**MINIMAL, "type": {"x": 1}}, [("cover.type.x", "unknown_field")]),
        ({**MINIMAL, "legibility": "glow"}, [("cover.legibility", "choice")]),
        ({**MINIMAL, "spine_text": "always"}, [("cover.spine_text", "choice")]),
        ({**MINIMAL, "background": "red"}, [("cover.background", "color")]),
        ({**MINIMAL, "background": "#12345"}, [("cover.background", "color")]),
        ({**MINIMAL, "back_text": ""}, [("cover.back_text", "text")]),
        ({**MINIMAL, "back_text": "a\tb"}, [("cover.back_text", "text")]),
        ({**MINIMAL, "back_text": "x" * 1201}, [("cover.back_text", "text")]),
        ({**MINIMAL, "isbn": "978"}, [("cover.isbn", "unknown_field")]),
        ([], [("cover", "type")]),
    ],
)
def test_invalid_cover_fields(cover, expected):
    assert issues(cover) == expected


def test_back_text_limit_is_inclusive():
    cover = demo_variant(with_cover({**MINIMAL, "back_text": "x" * 1200})).cover
    assert cover is not None and len(cover.back_text or "") == 1200
