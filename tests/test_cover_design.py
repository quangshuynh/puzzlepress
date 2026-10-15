"""Cover version 3: regions, design elements, flattening, conversion and determinism."""

import hashlib
import io
import os
import subprocess
import sys
from dataclasses import replace

import pytest
from pypdf import PdfReader

from puzzlepress.cover import build as cover_build
from puzzlepress.cover.assets import decode_photo
from puzzlepress.cover.build import InteriorFacts, render_cover
from puzzlepress.cover.convert import convert_to_regions, design_presets
from puzzlepress.cover.inspection import STROKE_OPERATORS, read_cover_facts
from puzzlepress.cover.issues import CoverError
from puzzlepress.cover.model import CoverPhoto, CoverShape
from puzzlepress.cover.preflight import preflight_cover
from puzzlepress.cover_config import CoverLayoutKind, Legibility
from puzzlepress.cover_validation import validate_cover
from puzzlepress.interior.spec import Paper, inches
from puzzlepress.validation import validate_project
from tests.cover_helpers import cover_project, photo_bytes
from tests.helpers import ROOT, demo_variant

PHOTO = decode_photo(photo_bytes(5400, 3600))
OTHER = decode_photo(photo_bytes(2400, 3000))
NAVY, CREAM, RED = "#1d2a44", "#f4efe4", "#c03030"


def facts(pages: int = 95, paper: Paper = Paper.WHITE) -> InteriorFacts:
    profile = "paperback-8.5x11-cream" if paper is Paper.CREAM else "paperback-8.5x11"
    return InteriorFacts(
        "composition-demo",
        "pp1-interior-sha256-" + "1" * 64,
        "pp1-sha256-" + "2" * 64,
        "3" * 64,
        pages,
        {"profile_id": profile, "profile_version": 2, "ink": "black"},
        inches(8.5),
        inches(11),
        paper,
    )


def image(photo=PHOTO, path="cover-assets/harbour-1.jpg"):
    return {"path": path, "sha256": photo.info.sha256}


def regions(back=NAVY, spine=NAVY, front=NAVY, **front_extra):
    return {
        "back": {"color": back},
        "spine": {"color": spine},
        "front": {"color": front, **front_extra},
    }


def project(cover: dict, **book):
    def mutate(data):
        data["book"].update({"imprint": "Harbour Press", **book})
        data["cover"] = cover

    return demo_variant(mutate)


def v3(elements=(), **fields):
    return {"version": 3, "regions": regions(), "elements": list(elements), **fields}


def front_photo(**fields):
    return {"id": "photo", "type": "photo", "region": "front", "image": image(), **fields}


def render(cover: dict, photos=None, pages=95, issues=False, **book):
    built = project(cover, **book)
    supplied = photos or {PHOTO.info.sha256: PHOTO, OTHER.info.sha256: OTHER}
    return render_cover(built, facts(pages), supplied, allow_layout_issues=issues)


def layout_codes(cover: dict, **kwargs) -> set[str]:
    return {issue.code for issue in render(cover, issues=True, **kwargs).layout_issues}


def raster(pdf: bytes, scale: float = 0.25):
    pdfium = pytest.importorskip("pypdfium2")
    return pdfium.PdfDocument(pdf)[0].render(scale=scale).to_pil().convert("RGB")


def sample(build, x: float, y: float, scale: float = 0.25):
    """RGB at page point (x, y), y upward."""
    picture = raster(build.pdf, scale)
    height = build.layout.geometry.media.height
    return picture.getpixel((int(x * scale), int((height - y) * scale)))


def near(actual, expected, tolerance=6):
    return all(abs(a - b) <= tolerance for a, b in zip(actual, expected, strict=True))


def rgb(hex_color: str):
    return tuple(int(hex_color[i : i + 2], 16) for i in (1, 3, 5))


# ------------------------------------------------------------------ schema


def test_version_3_round_trips_and_keeps_editing_aids_out_of_identity():
    cover = v3(
        [
            front_photo(name="Front photograph", locked=True),
            {
                "id": "band",
                "type": "rect",
                "region": "front",
                "box": {"x": 0, "y": 500, "width": 612, "height": 120},
                "fill": CREAM,
                "opacity": 0.6,
            },
        ]
    )
    config, issues = validate_cover(cover, True)
    assert issues == () and config is not None
    again, _ = validate_cover(config.to_dict(), True)
    assert again == config
    base = render(cover)
    unlocked = cover | {"elements": [front_photo(), cover["elements"][1]]}
    assert render(unlocked).manifest["cover_identity"] == base.manifest["cover_identity"]
    assert render(unlocked).pdf == base.pdf


@pytest.mark.parametrize(
    ("cover", "expected"),
    [
        (
            {"version": 2, "image": image(), "regions": regions()},
            ("cover.regions", "requires_version_3"),
        ),
        (v3(background=NAVY), ("cover.background", "not_in_version_3")),
        ({"version": 3, "elements": []}, ("cover.regions", "required")),
        (
            v3([{**front_photo(), "region": "spine"}]),
            ("cover.elements.0.region", "region_not_allowed"),
        ),
        (
            v3(
                [
                    {
                        "id": "t",
                        "type": "text",
                        "region": "spine",
                        "box": {"x": 0, "y": 0, "width": 9, "height": 9},
                        "text": "A",
                    }
                ]
            ),
            ("cover.elements.0.region", "region_not_allowed"),
        ),
        (
            v3(
                [
                    {
                        "id": "r",
                        "type": "rect",
                        "region": "front",
                        "fill": RED,
                        "stroke": CREAM,
                        "opacity": 0.5,
                        "box": {"x": 0, "y": 0, "width": 9, "height": 9},
                    }
                ]
            ),
            ("cover.elements.0.opacity", "opacity_with_stroke"),
        ),
        (
            v3([{"id": "r", "type": "rect", "region": "front", "fill": None}]),
            ("cover.elements.0.fill", "shape_invisible"),
        ),
        (
            v3([{"id": "r", "type": "rect", "region": "front", "rotation": 10}]),
            ("cover.elements.0.rotation", "rotation_needs_box"),
        ),
        (
            v3(
                [
                    {
                        "id": "l",
                        "type": "line",
                        "region": "front",
                        "from": {"x": 5, "y": 5},
                        "to": {"x": 5, "y": 5},
                    }
                ]
            ),
            ("cover.elements.0.to", "line_too_short"),
        ),
        (
            v3(
                [
                    {
                        "id": "l",
                        "type": "line",
                        "region": "front",
                        "from": {"x": 0, "y": 0},
                        "to": {"x": 90, "y": 0},
                        "width": 0.5,
                    }
                ]
            ),
            ("cover.elements.0.width", "range"),
        ),
        (v3([front_photo(), front_photo()]), ("cover.elements.1.id", "duplicate")),
        (
            v3([front_photo(id=f"p{n}") for n in range(5)]),
            ("cover.elements", "too_many_photos"),
        ),
        (
            v3(
                [
                    {
                        "id": "t",
                        "type": "text",
                        "region": "front",
                        "box": {"x": 0, "y": 0, "width": 90, "height": 20},
                        "text": "x",
                        "font": "missing",
                    }
                ]
            ),
            ("cover.elements.0.font", "unknown_font"),
        ),
    ],
)
def test_version_3_schema_refusals(cover, expected):
    _, issues = validate_cover(cover, True)
    assert expected in [(i.path, i.code) for i in issues]


# ------------------------------------------------------------------ conversion


@pytest.mark.parametrize("layout", [CoverLayoutKind.FULL_WRAP, CoverLayoutKind.FRONT_PHOTO])
@pytest.mark.parametrize("legibility", list(Legibility))
@pytest.mark.parametrize("pages", [95, 300])
def test_conversion_renders_identical_pdf_bytes(layout, legibility, pages):
    cover = {
        "version": 2,
        "layout": layout.value,
        "image": image(),
        "legibility": legibility.value,
        "background": NAVY,
        "back_text": "Quiet seaside puzzles.",
        "extra": [{"id": "tagline", "panel": "front", "text": "Sixty puzzles", "size": 16}],
        "text": {"subtitle": {"offset": {"x": 0, "y": -24}}},
    }
    original = render(cover, pages=pages)
    converted = convert_to_regions(original.layout.config)
    assert converted.version == 3 and converted.image is None
    again = render_cover(
        replace(project(cover), cover=converted), facts(pages), {PHOTO.info.sha256: PHOTO}
    )
    assert again.pdf == original.pdf
    # The configuration changed, so the cover identity does; nothing else does.
    assert again.manifest["cover_identity"] != original.manifest["cover_identity"]
    checked, issues = validate_cover(converted.to_dict(), True)
    assert issues == () and checked == converted


def test_conversion_is_explicit_and_only_for_versions_1_and_2():
    config = render(v3([front_photo()])).layout.config
    with pytest.raises(ValueError):
        convert_to_regions(config)
    legacy, _ = validate_cover({"version": 1, "image": image()}, True)
    assert legacy is not None and legacy.version == 1  # Validation never upgrades.


def test_presets_are_authored_values_that_render():
    legacy, _ = validate_cover({"version": 1, "image": image(), "background": NAVY}, True)
    assert legacy is not None
    presets = design_presets(legacy)
    assert [p.id for p in presets] == [
        "front-photo-solid-back",
        "full-wrap-photo",
        "framed-photo",
        "solid-with-rules",
    ]
    for preset in presets:
        checked, issues = validate_cover(preset.config.to_dict(), True)
        assert issues == () and checked == preset.config, preset.id
        build = render(preset.config.to_dict())
        assert build.layout_issues == ()


# ------------------------------------------------------------------ regions


def test_regions_take_their_own_colors_and_gradients():
    cover = v3(regions=regions(back=NAVY, spine=CREAM, front=RED, gradient={"to": "#000000"}))
    build = render(cover, pages=300)
    g = build.layout.geometry
    assert [f.role for f in build.layout.region_fills] == [
        "region_back",
        "region_spine",
        "region_front",
    ]
    assert near(sample(build, g.back.x + 100, 400), rgb(NAVY))
    assert near(sample(build, g.spine.x + g.spine.width / 2, 400), rgb(CREAM))
    top = sample(build, g.front.x + 300, g.media.top - 4)
    bottom = sample(build, g.front.x + 300, 4)
    assert near(top, rgb(RED), 12) and near(bottom, (0, 0, 0), 12)
    facts_ = read_cover_facts(build.pdf)
    assert not facts_.base.pages[0].transparency and "sh" in facts_.operators
    assert not facts_.operators & STROKE_OPERATORS and facts_.images == ()


def test_uniform_regions_draw_one_background_and_no_photo_needed():
    build = render(v3())
    assert build.layout.region_fills == () and build.layout.photos == ()
    assert build.layout.resolution is None and build.image_sizes == ()
    assert build.manifest["photos"] == [] and build.manifest["resolution"] is None


def test_region_geometry_derives_from_page_count():
    rect = {
        "id": "r",
        "type": "rect",
        "region": "front",
        "box": {"x": 36, "y": 36, "width": 72, "height": 72},
        "fill": RED,
    }
    thin, wide = render(v3([rect]), pages=95), render(v3([rect]), pages=300)
    (a,), (b,) = thin.layout.stack, wide.layout.stack
    assert isinstance(a, CoverShape) and isinstance(b, CoverShape)
    shift = wide.layout.geometry.spine_width - thin.layout.geometry.spine_width
    assert b.box.x - a.box.x == pytest.approx(shift)
    assert a.box.x == pytest.approx(thin.layout.geometry.front.x + 36)


# ------------------------------------------------------------------ elements


def _rect(element_id, x, y, width, height, fill, **fields):
    box = {"x": x, "y": y, "width": width, "height": height}
    return {"id": element_id, "type": "rect", "region": "front", "box": box, "fill": fill, **fields}


def test_stack_order_visibility_and_strokes():
    lower = _rect("lower", 100, 300, 200, 200, RED)
    upper = _rect("upper", 150, 350, 200, 200, CREAM, stroke="#000000", stroke_width=4)
    build = render(v3([lower, upper]))
    front = build.layout.geometry.front
    assert near(sample(build, front.x + 125, 325), rgb(RED))
    assert near(sample(build, front.x + 250, 450), rgb(CREAM))
    assert near(sample(build, front.x + 152, 450), (0, 0, 0), 30)  # The inside stroke.
    swapped = render(v3([upper, lower]))
    assert near(sample(swapped, front.x + 250, 450), rgb(RED))
    hidden = render(v3([lower, {**upper, "visible": False}]))
    assert [item.role for item in hidden.layout.stack] == ["front_element:lower"]
    assert near(sample(hidden, front.x + 320, 520), rgb(NAVY))
    assert not read_cover_facts(build.pdf).operators & STROKE_OPERATORS


def test_rotated_shapes_and_lines_have_painted_bounds():
    rect = _rect("r", 100, 100, 100, 50, RED, rotation=90)
    line = {
        "id": "l",
        "type": "line",
        "region": "back",
        "from": {"x": 50, "y": 300},
        "to": {"x": 150, "y": 400},
        "width": 2,
    }
    ellipse = {**_rect("e", 300, 100, 100, 50, CREAM, rotation=45), "type": "ellipse"}
    build = render(v3([rect, line, ellipse]))
    shapes = {s.role: s for s in build.layout.stack if isinstance(s, CoverShape)}
    r = shapes["front_element:r"].bounds
    assert (r.width, r.height) == pytest.approx((50, 100))
    l_shape = shapes["back_element:l"]
    assert l_shape.rotation == pytest.approx(45) and l_shape.box.width == pytest.approx(
        2**0.5 * 100
    )
    e = shapes["front_element:e"].bounds
    assert e.width == pytest.approx(e.height) and 50 < e.width < 100


def test_translucent_shape_blends_with_a_solid_region():
    band = _rect("band", 0, 300, 612, 100, "#ffffff", opacity=0.5)
    build = render(v3([band]))
    (shape,) = build.layout.stack
    assert isinstance(shape, CoverShape) and shape.opacity == 1.0
    expected = tuple(round((255 + c) / 2) for c in rgb(NAVY))
    assert near(sample(build, build.layout.geometry.front.x + 300, 350), expected)
    assert not read_cover_facts(build.pdf).base.pages[0].transparency


def test_translucent_shape_is_baked_into_the_photograph_under_it():
    band = _rect("band", 100, 300, 300, 100, "#ffffff", opacity=0.4)
    plain = render(v3([front_photo(), {**band, "visible": False}], legibility="none"))
    baked = render(v3([front_photo(), band], legibility="none"))
    (photo,) = baked.layout.stack
    assert isinstance(photo, CoverPhoto) and [s.role for s in photo.baked] == ["front_element:band"]
    front = baked.layout.geometry.front
    before = sample(plain, front.x + 250, 350)
    after = sample(baked, front.x + 250, 350)
    assert near(after, tuple(round(0.4 * 255 + 0.6 * c) for c in before), 10)
    pdf = read_cover_facts(baked.pdf)
    assert len(pdf.images) == 1 and not pdf.base.pages[0].transparency


def test_unflattenable_translucency_is_reported_not_approximated():
    band = _rect("band", -40, 300, 300, 100, "#ffffff", opacity=0.5)
    photo = front_photo(box={"x": 0, "y": 0, "width": 300, "height": 792})
    assert "opacity_not_flattenable" in layout_codes(v3([photo, band]))
    with pytest.raises(CoverError) as error:
        render(v3([photo, band]))
    assert error.value.stage == "layout_validation"


def test_text_boxes_wrap_overflow_and_respect_safe_areas():
    box = {
        "id": "blurb",
        "type": "text",
        "region": "back",
        "box": {"x": 72, "y": 400, "width": 140, "height": 120},
    }
    text = "Puzzles for the long drive home.\nSixty grids, three levels."
    build = render(v3([{**box, "text": text, "size": 12}]))
    lines = [t for t in build.layout.texts if t.role == "back_element:blurb"]
    assert len(lines) >= 3 and all(
        t.bounds.right <= build.layout.geometry.back.x + 212 + 0.01 for t in lines
    )
    assert "Sixty grids, three levels." in [t.text for t in lines]  # Explicit break kept.
    assert "Puzzles for the long drive home." in PdfReader(io.BytesIO(build.pdf)).pages[
        0
    ].extract_text().replace("\n", " ")
    long = {**box, "text": " ".join(["word"] * 120), "size": 12}
    assert "text_box_overflow" in layout_codes(v3([long]))
    unbreakable = {**box, "text": "W" * 60, "size": 20}
    with pytest.raises(CoverError) as error:
        render(v3([unbreakable]), issues=True)
    assert error.value.issues[0].code == "text_overflow"
    edge = {**box, "box": {"x": 2, "y": 400, "width": 200, "height": 120}, "text": "Edge"}
    assert "unsafe_back_text" in layout_codes(v3([edge]))
    barcode = {**box, "box": {"x": 460, "y": 30, "width": 120, "height": 40}, "text": "Here"}
    assert "barcode_region_conflict" in layout_codes(v3([barcode]))
    over_title = {
        "id": "t",
        "type": "text",
        "region": "front",
        "box": {"x": 36, "y": 600, "width": 540, "height": 150},
        "text": "Over the title",
        "size": 40,
    }
    assert "text_overlap" in layout_codes(v3([over_title]))


def test_text_box_fonts_and_case_are_embedded_like_book_text():
    box = {
        "id": "t",
        "type": "text",
        "region": "back",
        "box": {"x": 72, "y": 300, "width": 300, "height": 80},
        "text": "Hello",
        "font": "serif-italic",
        "case": "upper",
        "letter_spacing": 2,
    }
    build = render(v3([box]))
    (line,) = [t for t in build.layout.texts if t.role == "back_element:t"]
    assert line.text == "HELLO" and line.face == "serif-italic" and line.tracking == 2


def test_several_photographs_each_report_resolution():
    small = {
        "id": "inset",
        "type": "photo",
        "region": "back",
        "image": image(OTHER, "cover-assets/other-2.jpg"),
        "box": {"x": 72, "y": 300, "width": 300, "height": 375},
    }
    build = render(v3([front_photo(), small]))
    assert [p.role for p in build.layout.photos] == ["front_element:photo", "back_element:inset"]
    assert len(read_cover_facts(build.pdf).images) == 2
    assert len(build.manifest["photos"]) == 2
    low = render(v3([front_photo(crop={"x": 0.5, "y": 0.5, "zoom": 4})]))
    assert low.layout.resolution.status == "image_low_effective_dpi"


def test_spine_rules_block_and_warn():
    outside = {
        "id": "s",
        "type": "rect",
        "region": "spine",
        "box": {"x": -10, "y": 100, "width": 40, "height": 100},
        "fill": RED,
    }
    assert "spine_element_outside" in layout_codes(v3([outside]), pages=300)
    band = {
        "id": "s",
        "type": "rect",
        "region": "spine",
        "box": {"x": 0, "y": 100, "width": 15, "height": 100},
        "fill": RED,
    }
    warned = render(v3([band], regions=regions(spine=CREAM)), pages=300)
    codes = {w.code for w in warned.layout.warnings}
    assert {"spine_color_at_fold", "spine_element_at_fold"} <= codes
    assert warned.layout_issues == ()


def test_barcode_warning_only_for_elements_under_the_box():
    g = render(v3()).layout.geometry
    x = g.barcode.x - g.back.x
    small = {
        "id": "dot",
        "type": "ellipse",
        "region": "back",
        "box": {"x": x + 20, "y": 30, "width": 40, "height": 40},
        "fill": RED,
    }
    assert [w.code for w in render(v3([small])).layout.warnings] == ["element_under_barcode"]
    background = {"id": "bg", "type": "photo", "region": "back", "image": image()}
    assert render(v3([background])).layout.warnings == ()


def test_outside_media_is_reported():
    far = _rect("far", 600, 300, 100, 100, RED)
    assert "element_outside_media" in layout_codes(v3([far]))


# ------------------------------------------------------------------ files, preflight, determinism


def _designed_project(tmp_path, elements):
    def mutate(data):
        cover = data["cover"]
        data["cover"] = {
            "version": 3,
            "regions": regions(spine=CREAM),
            "back_text": cover["back_text"],
            "elements": [
                {"id": "photo", "type": "photo", "region": "front", "image": cover["image"]},
                *elements,
            ],
        }

    return cover_project(tmp_path, mutate=mutate, puzzles=60)


def test_preflight_reports_design_notes(tmp_path):
    source, output = _designed_project(
        tmp_path,
        [
            {
                "id": "rule",
                "type": "line",
                "region": "back",
                "from": {"x": 72, "y": 600},
                "to": {"x": 540, "y": 600},
                "color": CREAM,
            }
        ],
    )
    from puzzlepress import load_project
    from puzzlepress.cover.build import build_cover, write_cover

    loaded = load_project(source).project
    write_cover(build_cover(loaded, source, output), output, source)
    report = preflight_cover(loaded, source, output)
    data = report.to_dict()
    outcomes = {r["code"]: r["outcome"] for r in data["rules"]}
    assert report.state == "current" and report.structurally_valid
    assert outcomes["kdp_spine_design"] == "failed" and outcomes["kdp_barcode_design"] == "passed"
    assert data["ruleset"]["version"] == 3
    assert "kdp_spine_design" in [f.rule.code for f in report.findings]


def test_legacy_cover_preflight_marks_design_rules_not_applicable(tmp_path):
    source, output = cover_project(tmp_path)
    from puzzlepress import load_project
    from puzzlepress.cover.build import build_cover, write_cover

    loaded = load_project(source).project
    write_cover(build_cover(loaded, source, output), output, source)
    outcomes = {
        r.rule.code: r.outcome.value for r in preflight_cover(loaded, source, output).results
    }
    assert outcomes["kdp_spine_design"] == outcomes["kdp_barcode_design"] == "not_applicable"


def test_designed_cover_bytes_repeat_across_processes(tmp_path):
    source, output = _designed_project(
        tmp_path,
        [
            _rect("band", 0, 500, 612, 80, "#ffffff", opacity=0.3),
            {
                "id": "t",
                "type": "text",
                "region": "back",
                "box": {"x": 72, "y": 300, "width": 300, "height": 80},
                "text": "Hello",
            },
        ],
    )
    from puzzlepress import load_project
    from puzzlepress.cover.build import build_cover

    build = build_cover(load_project(source).project, source, output)
    script = (
        "import hashlib,sys;from puzzlepress import load_project;"
        "from puzzlepress.cover.build import build_cover;"
        f"p=load_project({str(source)!r}).project;"
        f"print(hashlib.sha256(build_cover(p,__import__('pathlib').Path({str(source)!r}),"
        f"__import__('pathlib').Path({str(output)!r})).pdf).hexdigest())"
    )
    for seed in ("0", "4242"):
        result = subprocess.run(
            [sys.executable, "-c", script],
            capture_output=True,
            text=True,
            cwd=tmp_path,
            env={**os.environ, "PYTHONHASHSEED": seed, "PYTHONPATH": str(ROOT / "src")},
            check=True,
        )
        assert result.stdout.strip() == hashlib.sha256(build.pdf).hexdigest()


def test_designed_identity_tracks_elements_and_renderer(monkeypatch):
    rect = _rect("r", 100, 100, 100, 50, RED)
    base = render(v3([rect])).manifest["cover_identity"]
    assert render(v3([{**rect, "fill": CREAM}])).manifest["cover_identity"] != base
    assert render(v3([{**rect, "name": "Red block"}])).manifest["cover_identity"] == base
    monkeypatch.setattr(cover_build, "COVER_RENDERER_VERSION", 2)
    assert render(v3([rect])).manifest["cover_identity"] != base


def test_hidden_metadata_text_never_changes_book_details():
    cover = v3(text={"title": {"visible": False}})
    built = project(cover)
    build = render_cover(built, facts(), {})
    assert built.book.title == "Seaside Word Searches"
    assert build.manifest["display"]["title"] is None


def test_validate_project_accepts_version_3():
    data = demo_variant().to_dict()
    data["cover"] = v3([front_photo()])
    assert validate_project(data).valid
