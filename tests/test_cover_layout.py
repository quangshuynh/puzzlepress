"""CoverLayout: photo regions, type placement, spine, back cover, legibility, contract."""

from dataclasses import replace
from itertools import product

import pytest

from puzzlepress.cover.assets import PhotoInfo
from puzzlepress.cover.geometry import cover_geometry
from puzzlepress.cover.issues import CoverError
from puzzlepress.cover.layout import CoverCopy, layout_cover
from puzzlepress.cover.validation import validate_cover_layout
from puzzlepress.cover_config import (
    CoverConfig,
    CoverImage,
    CoverLayoutKind,
    CoverStyle,
    CoverType,
    Crop,
    Legibility,
    SpineText,
    TextAlign,
    TextTone,
    TitlePosition,
)
from puzzlepress.interior.model import Box
from puzzlepress.interior.spec import Paper, inches

W, H = inches(8.5), inches(11)
COPY = CoverCopy(
    "Seaside Word Searches",
    "Forty quiet puzzles",
    "PuzzlePress Examples",
    "Harbour Press",
    "Forty quiet puzzles for slow mornings.\nEvery grid is verified.",
)
CONFIG = CoverConfig(CoverImage("cover-assets/sea-1.jpg", "0" * 64))


def photo(width=6000, height=4000):
    return PhotoInfo("0" * 64, "jpeg", 1, width, height, width, height, 1, "srgb_assumed")


def lay(pages=300, paper=Paper.CREAM, config=CONFIG, copy=COPY, image=None):
    geometry = cover_geometry(pages, W, H, paper)
    return layout_cover("demo", copy, config, geometry, image or photo())


def roles(layout):
    return [text.role for text in layout.texts]


def by_role(layout, role):
    return [text for text in layout.texts if text.role == role]


def test_full_wrap_photo_covers_the_whole_media_box():
    layout = lay()
    g = layout.geometry
    assert layout.photo.region == g.media
    assert layout.photo.placement.contains(g.media, 1e-6)
    assert layout.background.box == g.media and layout.background.color == CONFIG.rgb()
    r = layout.resolution
    assert r.printed_inches == pytest.approx((18.0, 11.25))
    assert r.effective_dpi == pytest.approx(6000 / 18) and r.status == "ok"


def test_front_photo_covers_the_front_and_its_three_bleed_edges():
    layout = lay(config=replace(CONFIG, layout=CoverLayoutKind.FRONT_PHOTO))
    g, region = layout.geometry, layout.photo.region
    assert (region.x, region.y, region.right, region.top) == pytest.approx(
        (g.front.x, 0, g.media.right, g.media.top)
    )
    assert layout.resolution.printed_inches == pytest.approx((8.625, 11.25))


def test_front_type_order_and_positions():
    layout = lay()
    g = layout.geometry
    title, subtitle, author = (
        by_role(layout, "title"),
        by_role(layout, "subtitle"),
        by_role(layout, "author"),
    )
    assert [t.text for t in title] == ["Seaside Word", "Searches"]
    assert title[0].bounds.top == pytest.approx(g.front_design.top)
    assert title[-1].bounds.y > subtitle[0].bounds.top
    assert author[0].bounds.y == pytest.approx(g.front_design.y)
    center = g.front_design.x + g.front_design.width / 2
    for text in title + subtitle + author:
        assert text.bounds.x + text.bounds.width / 2 == pytest.approx(center)


def test_bottom_position_puts_the_author_above_and_left_alignment():
    config = replace(CONFIG, type=CoverType(position=TitlePosition.BOTTOM, align=TextAlign.LEFT))
    layout = lay(config=config)
    g = layout.geometry
    author, subtitle = by_role(layout, "author")[0], by_role(layout, "subtitle")[-1]
    assert author.bounds.top == pytest.approx(g.front_design.top)
    assert subtitle.bounds.y == pytest.approx(g.front_design.y)
    front = [t for t in layout.texts if t.role in ("title", "subtitle", "author")]
    assert all(t.bounds.x == pytest.approx(g.front_design.x) for t in front)


def test_middle_position_centers_the_title_block():
    layout = lay(config=replace(CONFIG, type=CoverType(position=TitlePosition.MIDDLE)))
    area = layout.geometry.front_design
    block = by_role(layout, "title") + by_role(layout, "subtitle")
    top, bottom = block[0].bounds.top, block[-1].bounds.y
    assert (top + bottom) / 2 == pytest.approx(area.y + area.height / 2)


def test_missing_optional_copy_prints_nothing_invented():
    layout = lay(copy=CoverCopy("Only a Title", None, None, None, None))
    assert set(roles(layout)) == {"title", "spine_title"}


def test_long_titles_step_down_within_the_preset_and_then_fail():
    long = "The Extraordinarily Comprehensive Coastal Compendium of Word Searches"
    layout = lay(copy=replace(COPY, title=long))
    sizes = {t.size for t in by_role(layout, "title")}
    assert len(sizes) == 1 and 36 <= sizes.pop() < 62
    assert len(by_role(layout, "title")) <= 3
    with pytest.raises(CoverError) as error:
        lay(copy=replace(COPY, title=" ".join(["Puzzles"] * 30)))
    assert (error.value.stage, error.value.issues[0].code) == ("layout", "text_overflow")


def test_unsupported_characters_and_overlong_back_text_fail():
    with pytest.raises(CoverError) as error:
        lay(copy=replace(COPY, title="Ω Searches"))
    assert error.value.issues[0].code == "unsupported_character"
    with pytest.raises(CoverError) as error:
        lay(copy=replace(COPY, back_text="\n".join(["A line of back text."] * 60)))
    assert error.value.issues[0].region == "cover.back_text"


def test_back_text_and_imprint_avoid_the_barcode_area():
    layout = lay()
    g = layout.geometry
    back = by_role(layout, "back_text") + by_role(layout, "imprint")
    assert len(back) == 3
    assert all(not t.bounds.overlaps(g.barcode_keep_clear, 0) for t in back)
    imprint = by_role(layout, "imprint")[0]
    assert (imprint.bounds.x, imprint.bounds.y) == pytest.approx((g.back_design.x, g.back_design.y))


def test_spine_text_by_eligibility_width_and_authored_choice():
    thin = lay(pages=11, paper=Paper.WHITE)
    assert thin.spine.to_dict() == {
        "allowed_by_page_count": False,
        "rendered": False,
        "reason": "page_count",
        "size": None,
    }
    assert not any(t.rotated for t in thin.texts)
    narrow = lay(pages=80, paper=Paper.WHITE)  # 0.18 in spine leaves under 7 pt.
    assert (narrow.spine.rendered, narrow.spine.reason) == (False, "spine_too_narrow")
    authored = lay(config=replace(CONFIG, spine_text=SpineText.NONE))
    assert (authored.spine.rendered, authored.spine.reason) == (False, "authored")
    wide = lay()
    assert wide.spine.rendered and wide.spine.size == 14
    title, author = by_role(wide, "spine_title")[0], by_role(wide, "spine_author")[0]
    safe = wide.geometry.spine_safe
    assert title.rotated and author.rotated
    assert title.bounds.top == pytest.approx(safe.top) and author.bounds.y == pytest.approx(safe.y)
    assert safe.contains(title.bounds, 1e-6) and safe.contains(author.bounds, 1e-6)
    center = safe.x + safe.width / 2
    assert title.bounds.x + title.bounds.width / 2 == pytest.approx(center)


def test_spine_text_shrinks_to_fit_and_fails_below_seven_points():
    geometry = cover_geometry(300, W, H, Paper.CREAM)
    short = replace(geometry, spine_safe=replace(geometry.spine_safe, height=inches(3.2)))
    layout = layout_cover("demo", COPY, CONFIG, short, photo())
    assert 7 <= (layout.spine.size or 0) < 14
    tiny = replace(geometry, spine_safe=replace(geometry.spine_safe, height=inches(1)))
    with pytest.raises(CoverError) as error:
        layout_cover("demo", COPY, CONFIG, tiny, photo())
    assert error.value.issues[0].code == "spine_text_overflow"


@pytest.mark.parametrize(
    ("image", "crop", "status"),
    [
        (photo(6000, 4000), Crop(), "ok"),
        (photo(6000, 4000), Crop(zoom=1.2), "image_low_effective_dpi"),
        (photo(1800, 1200), Crop(), "image_too_small"),
    ],
)
def test_resolution_status_distinguishes_zoom_from_small_photos(image, crop, status):
    layout = lay(config=replace(CONFIG, crop=crop), image=image)
    assert layout.resolution.status == status


def test_legibility_treatments():
    shade = lay()
    assert shade.panels == () and len(shade.photo.shade) == 5  # Front x2, back x2, spine.
    title_band = shade.photo.shade[0]
    assert title_band.core[1] == shade.geometry.media.top and title_band.toward == (0, 0, 0)
    assert title_band.weight(title_band.core[0] - title_band.fade - 1) == 0
    assert all((b.x0, b.x1) == (0, shade.geometry.media.right) for b in shade.photo.shade[:4])
    dark = lay(config=replace(CONFIG, type=CoverType(tone=TextTone.DARK)))
    assert dark.photo.shade[0].toward == (255, 255, 255)
    panel = lay(config=replace(CONFIG, legibility=Legibility.PANEL))
    assert panel.photo.shade == () and {p.role for p in panel.panels} >= {
        "panel_front_title",
        "panel_spine",
    }
    assert all(p.color == CONFIG.rgb() for p in panel.panels)
    plain = lay(config=replace(CONFIG, legibility=Legibility.NONE))
    assert plain.panels == () and plain.photo.shade == ()
    front_only = lay(config=replace(CONFIG, layout=CoverLayoutKind.FRONT_PHOTO))
    assert all(band.x0 >= front_only.geometry.front.x for band in front_only.photo.shade)


def test_layout_is_deterministic():
    assert lay() == lay()


@pytest.mark.parametrize(
    ("kind", "style", "position", "align", "legibility", "pages"),
    list(
        product(
            CoverLayoutKind,
            CoverStyle,
            TitlePosition,
            TextAlign,
            (Legibility.SHADE, Legibility.PANEL),
            (11, 300),
        )
    ),
)
def test_every_supported_combination_meets_the_layout_contract(
    kind, style, position, align, legibility, pages
):
    config = replace(
        CONFIG,
        layout=kind,
        type=CoverType(style=style, position=position, align=align),
        legibility=legibility,
    )
    layout = lay(pages=pages, config=config)
    assert validate_cover_layout(layout, W, H) == ()


def _codes(layout):
    return {issue.code for issue in validate_cover_layout(layout, W, H)}


def test_contract_catches_tampered_layouts():
    layout = lay()
    g = layout.geometry
    imprint = by_role(layout, "imprint")[0]
    moved = replace(imprint, bounds=Box(g.barcode.x, g.barcode.y, 40, 10))
    assert "barcode_region_conflict" in _codes(
        replace(layout, texts=tuple(moved if t is imprint else t for t in layout.texts))
    )
    title = layout.texts[0]
    for bounds, code in (
        (Box(g.front.right - 5, title.bounds.y, 50, 20), "unsafe_front_text"),
        (Box(g.front.x + 2, title.bounds.y, 50, 20), "unsafe_front_text"),
    ):
        tampered = replace(layout, texts=(replace(title, bounds=bounds),) + layout.texts[1:])
        assert code in _codes(tampered)
    small = replace(layout, texts=(replace(title, size=6.9),) + layout.texts[1:])
    assert "font_too_small" in _codes(small)
    twice = replace(layout, texts=(title, title))
    assert "text_overlap" in _codes(twice)
    thin = lay(pages=11, paper=Paper.WHITE)
    spine = by_role(layout, "spine_title")[0]
    assert "spine_text_not_allowed" in _codes(replace(thin, texts=thin.texts + (spine,)))
    wide = replace(g, media=replace(g.media, width=g.media.width + 1))
    assert "invalid_wrap_dimensions" in _codes(replace(layout, geometry=wide))
    short = replace(layout.photo, region=replace(layout.photo.region, width=g.media.width - 9))
    assert "insufficient_bleed" in _codes(replace(layout, photo=short))


def test_cover_fonts_are_bundled_pinned_and_cover_latin_1():
    import hashlib
    from importlib.resources import files

    from puzzlepress.cover.fonts import CoverFace, font_manifest, missing_characters

    manifest = font_manifest()
    assert [entry["face"] for entry in manifest] == [face.value for face in CoverFace]
    for entry in manifest:
        package = "puzzlepress.cover" if "Newsreader" in entry["file"] else "puzzlepress.interior"
        data = files(package).joinpath("fonts", entry["file"]).read_bytes()
        assert hashlib.sha256(data).hexdigest() == entry["sha256"]
    latin1 = "".join(map(chr, list(range(32, 127)) + list(range(160, 256))))
    for face in CoverFace:
        assert missing_characters(latin1, face) == ()
    assert files("puzzlepress.cover").joinpath("fonts", "OFL.txt").is_file()
