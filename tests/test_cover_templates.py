"""Cover templates: the eight built-ins, application, bindings, slots and the custom store."""

import copy
import hashlib
import json
import os
from dataclasses import replace

import pytest

from puzzlepress.cover.build import render_cover
from puzzlepress.cover.geometry import cover_geometry
from puzzlepress.cover_config import TextRole
from puzzlepress.cover_design import PhotoElement, ShapeElement, TextBoxElement
from puzzlepress.cover_template import (
    MAX_TEMPLATE_BYTES,
    PhotoNeed,
    TemplateCategory,
    TemplateError,
    apply_template,
    parse_template,
    read_template,
    template_bytes,
    template_from_cover,
    template_values,
)
from puzzlepress.cover_template_store import (
    BUILTIN_ORDER,
    builtin_templates,
    check_assets,
    custom_templates,
    delete_template,
    find_template,
    save_template,
    unique_id,
)
from puzzlepress.interior.spec import Paper, inches
from tests.test_cover_design import OTHER, PHOTO, facts, image, project, regions

TRIM = (inches(8.5), inches(11))
BACK = "Twenty word searches from harbour walls and lighthouse paths."
PROVENANCE_WORDS = ("logo", "trademark", "isbn", "testimonial", "rating", "bestseller")


def spine(pages: int = 95, paper: Paper = Paper.WHITE) -> float:
    return cover_geometry(pages, *TRIM, paper).spine_width


def book(photo: bool = True, **fields):
    cover = {"version": 3, "regions": regions(), "elements": [], "back_text": BACK}
    if photo:
        cover["elements"] = [{"id": "photo", "type": "photo", "region": "front", "image": image()}]
    cover.update(fields.pop("cover", {}))
    return project(cover, **fields)


def applied(template, built, pages=95, paper=Paper.WHITE):
    return replace(built, cover=apply_template(template, built, spine(pages, paper), TRIM).cover)


def build(built, pages=95, paper=Paper.WHITE):
    photos = {PHOTO.info.sha256: PHOTO, OTHER.info.sha256: OTHER}
    return render_cover(built, facts(pages, paper), photos, allow_layout_issues=True)


def builtin(template_id: str):
    return find_template(None, template_id)


def raw(template_id: str = "photographic-editorial") -> dict:
    return builtin(template_id).to_dict()


# ------------------------------------------------------------------ the built-ins


def test_eight_original_builtins_load_in_gallery_order():
    templates = builtin_templates()
    assert tuple(t.id for t in templates) == BUILTIN_ORDER
    assert len({t.name for t in templates}) == 8
    assert {t.category for t in templates} == set(TemplateCategory) - {TemplateCategory.CUSTOM}
    for template in templates:
        assert template.builtin and not template.fonts
        assert template.provenance and "original" in template.provenance.lower()
        assert (template.photo is PhotoNeed.NONE) == (not template.slots())
        text = json.dumps(dict(template.design)).lower()
        assert not any(word in text for word in PROVENANCE_WORDS)
        # Templates hold no book identity, photograph or attestation.
        assert '"image"' not in text and 'back_text": "' not in text
        assert template.design.get("text", {}).get("title", {}).get("text") is None
        assert parse_template(template_bytes(template), builtin=True) == template


def test_photographic_editorial_leads_and_keeps_the_barcode_clear():
    lead = builtin_templates()[0]
    assert lead.id == "photographic-editorial" and lead.photo is PhotoNeed.REQUIRED
    result = build(applied(lead, book()))
    assert not result.layout_issues and not result.layout.warnings


@pytest.mark.parametrize("template_id", BUILTIN_ORDER)
@pytest.mark.parametrize(
    ("pages", "paper"),
    [(24, Paper.WHITE), (95, Paper.WHITE), (300, Paper.CREAM), (550, Paper.WHITE)],
)
def test_every_builtin_renders_cleanly_for_any_page_count_and_paper(template_id, pages, paper):
    built = applied(builtin(template_id), book(), pages, paper)
    result = build(built, pages, paper)
    assert result.layout_issues == ()
    assert result.layout.warnings == ()


@pytest.mark.parametrize("template_id", BUILTIN_ORDER)
def test_every_builtin_renders_cleanly_without_a_photo_or_author(template_id):
    built = applied(builtin(template_id), book(photo=False, author=None, imprint=None))
    result = build(built)
    assert result.layout_issues == () and result.layout.warnings == ()


def test_templates_follow_the_spine_and_scale_coordinates_to_the_trim():
    template = builtin("technical-blueprint")
    data = copy.deepcopy(template.to_dict())
    data["id"] = "spine-band"
    data["design"]["elements"].append(
        {
            "id": "spine-band",
            "type": "rect",
            "region": "spine",
            "box": {"x": 0, "y": 300, "width": "spine", "height": 40},
            "fill": "#e6eef7",
            "stroke": None,
        }
    )
    band = read_template(data)
    for pages in (95, 300):
        cover = apply_template(band, book(), spine(pages), TRIM).cover
        (element,) = [e for e in cover.elements if e.id == "spine-band"]
        assert element.box.width == pytest.approx(spine(pages), abs=0.005)
    half = apply_template(band, book(), spine(), (TRIM[0] / 2, TRIM[1] / 2)).cover
    full = apply_template(band, book(), spine(), TRIM).cover
    first = next(e for e in full.elements if e.id == "front-frame")
    scaled = next(e for e in half.elements if e.id == "front-frame")
    assert scaled.box.width == pytest.approx(first.box.width / 2, abs=0.01)


# ------------------------------------------------------------------ applying


def test_applying_keeps_book_identity_overrides_back_text_extras_and_photos():
    built = book(
        cover={
            "text": {
                "subtitle": {"visible": False},
                "author": {"text": "PuzzlePress Examples", "size": 19},
            },
            "extra": [{"id": "note", "text": "Large print", "panel": "front"}],
        }
    )
    before = built.to_dict()
    result = apply_template(builtin("bold-garage"), built, spine(), TRIM)
    assert built.to_dict() == before  # Nothing is saved or mutated.
    cover = result.cover
    assert cover.version == 3 and cover.back_text == BACK
    assert cover.layer(TextRole.SUBTITLE).visible is False
    author = cover.layer(TextRole.AUTHOR)
    assert author.text == "PuzzlePress Examples" and author.size is None  # Style replaced.
    assert [layer.id for layer in cover.extra] == ["note"]
    photos = [e for e in cover.elements if isinstance(e, PhotoElement)]
    assert [p.image.sha256 for p in photos] == [PHOTO.info.sha256]
    assert any("Region backgrounds" in line for line in result.replaced)
    assert any("title, subtitle, author and imprint" in line for line in result.kept)
    assert any("photograph" in line for line in result.kept)
    # The rest of the project is untouched: only the cover changes.
    after = applied(builtin("bold-garage"), built).to_dict()
    assert {k: v for k, v in after.items() if k != "cover"} == {
        k: v for k, v in before.items() if k != "cover"
    }


def test_rich_back_text_is_kept_as_rich():
    rich = {"rich": 1, "blocks": [{"runs": [{"text": "Bold words", "bold": True}]}]}
    built = book(cover={"back_text": rich, "text": {"back_text": {"font": "sans"}}})
    cover = apply_template(builtin("modern-minimal"), built, spine(), TRIM).cover
    assert cover.back_rich is not None and cover.back_rich.plain() == "Bold words"


def test_a_missing_required_photo_becomes_a_placeholder_never_another_picture():
    built = book(photo=False)
    result = apply_template(builtin("photographic-editorial"), built, spine(), TRIM)
    assert result.missing_slots == (1,)
    (placeholder,) = [e for e in result.cover.elements if e.id == "photo-slot-1"]
    assert isinstance(placeholder, ShapeElement) and placeholder.name == "Photo placeholder 1"
    assert result.cover.images() == ()
    assert not build(replace(built, cover=result.cover)).layout_issues


def test_an_optional_photo_and_its_frame_are_left_out_when_there_is_none():
    result = apply_template(builtin("vintage-motoring"), book(photo=False), spine(), TRIM)
    ids = {e.id for e in result.cover.elements}
    assert result.missing_slots == () and "front-photo" not in ids and "photo-keyline" not in ids
    with_photo = apply_template(builtin("vintage-motoring"), book(), spine(), TRIM)
    assert {"front-photo", "photo-keyline"} <= {e.id for e in with_photo.cover.elements}


def test_a_version_1_cover_carries_its_photograph_and_focal_point_into_the_template():
    cover = {
        "version": 1,
        "layout": "front_photo",
        "image": image(),
        "crop": {"x": 0.3, "y": 0.6, "zoom": 1.5},
        "back_text": BACK,
    }
    built = project(cover)
    result = apply_template(builtin("photographic-editorial"), built, spine(), TRIM)
    (photo,) = [e for e in result.cover.elements if isinstance(e, PhotoElement)]
    assert (photo.crop.x, photo.crop.y) == (0.3, 0.6) and photo.crop.zoom == 1.0
    assert any("single-photo layout" in line for line in result.replaced)


def test_bindings_resolve_from_the_book_and_absent_values_are_left_out():
    built = book()
    values = template_values(built)
    assert values["title"] == built.book.title
    assert values["puzzle_count"] == str(len(built.word_search.puzzles))
    assert "theme_count" not in values or int(values["theme_count"]) >= 2
    cover = apply_template(builtin("bold-garage"), built, spine(), TRIM).cover
    (highlights,) = [e for e in cover.elements if e.id == "back-highlights"]
    assert isinstance(highlights, TextBoxElement) and highlights.rich is not None
    plain = highlights.rich.plain()
    assert f"{values['puzzle_count']} puzzles" in plain and "{" not in plain
    if "theme_count" not in values:
        assert "themes" not in plain


def test_application_is_deterministic():
    first = apply_template(builtin("premium-editorial"), book(), spine(), TRIM)
    second = apply_template(builtin("premium-editorial"), book(), spine(), TRIM)
    assert first == second
    built = replace(book(), cover=first.cover)
    assert build(built).pdf == build(built).pdf


# ------------------------------------------------------------------ format and refusals


def refused(data, code=None) -> set[str]:
    with pytest.raises(TemplateError) as caught:
        read_template(data)
    codes = {issue.code for issue in caught.value.issues} | {caught.value.code}
    if code is not None:
        assert code in codes, codes
    return codes


def test_template_refusals():
    data = raw()
    data["template_version"] = 2
    refused(data, "template_version")
    data = raw()
    data["script"] = "alert(1)"
    refused(data, "unknown_field")
    data = raw()
    data["design"]["elements"][0]["image"] = image()
    refused(data, "template_photo")
    data = raw()
    data["design"]["elements"][0]["slot"] = 3
    refused(data, "slot")
    data = raw()
    data["design"]["elements"].append({"id": "x", "type": "video", "region": "front"})
    refused(data)
    data = raw()
    data["design"]["elements"][2]["text"] = "{isbn}"
    refused(data, "unknown_binding")
    data = raw()
    data["design"]["text"] = {"title": {"text": "Another Title"}}
    refused(data, "book_specific")
    data = raw()
    data["design"]["elements"][1]["onclick"] = "x"
    refused(data, "unknown_field")
    data = raw()
    data["id"] = "../escape"
    refused(data, "id")
    data = raw("bold-garage")
    data["design"]["elements"][1]["box"]["width"] = "spine"
    refused(data, "spine_width")
    data = raw()
    data["fonts"] = [{"id": "f", "path": "../../etc/passwd", "sha256": "0" * 64}]
    refused(data)
    data = raw()
    data["design"]["elements"][2]["font"] = "comic"
    refused(data, "unknown_font")


def test_parse_is_bounded_and_never_executes():
    with pytest.raises(TemplateError) as caught:
        parse_template(b" " * (MAX_TEMPLATE_BYTES + 1))
    assert caught.value.code == "template_too_large"
    with pytest.raises(TemplateError) as caught:
        parse_template(b"{not json")
    assert caught.value.code == "template_unreadable"
    with pytest.raises(TemplateError):
        parse_template(b"\xff\xfe")


# ------------------------------------------------------------------ custom templates


def test_saving_a_cover_as_a_template_drops_the_book_identity(tmp_path):
    built = book(
        title="Harbour Word Search",
        cover={
            "elements": [
                {"id": "photo", "type": "photo", "region": "front", "image": image()},
                {
                    "id": "tag",
                    "type": "text",
                    "region": "front",
                    "box": {"x": 36, "y": 300, "width": 300, "height": 40},
                    "text": "Harbour Word Search, volume one",
                },
            ],
            "text": {"title": {"text": "Harbour Word Search", "color": "#f4efe4"}},
        },
    )
    template = template_from_cover(built, "harbour", "Harbour", "From my cover.", spine())
    data = template.to_dict()
    text = json.dumps(data)
    assert "Harbour Word Search" not in text and BACK not in text and '"image"' not in text
    assert data["design"]["text"] == {"title": {"color": "#f4efe4"}}
    tag = next(e for e in data["design"]["elements"] if e["id"] == "tag")
    assert tag["text"] == "{title}, volume one"
    assert template.photo is PhotoNeed.REQUIRED and template.slots() == (1,)
    assert template.category is TemplateCategory.CUSTOM and not template.builtin
    # Applying it to another book fills the bindings with that book's words.
    other = book(title="Garden Word Search")
    cover = apply_template(template, other, spine(), TRIM).cover
    (tag,) = [e for e in cover.elements if e.id == "tag"]
    assert tag.text == "Garden Word Search, volume one"


def test_custom_store_save_duplicate_rename_and_delete(tmp_path):
    template = template_from_cover(book(), "mine", "Mine", "", spine())
    saved = save_template(tmp_path, template)
    assert (tmp_path / "cover-templates" / "mine.json").read_bytes() == template_bytes(saved)
    with pytest.raises(TemplateError) as caught:
        save_template(tmp_path, template)
    assert caught.value.code == "template_exists"
    copy_id = unique_id(tmp_path, "mine")
    assert copy_id == "mine-2"
    save_template(tmp_path, replace(saved, id=copy_id, name="Mine (copy)"))
    renamed = save_template(tmp_path, replace(saved, name="Renamed"), saved.identity())
    with pytest.raises(TemplateError) as caught:
        save_template(tmp_path, replace(saved, name="Stale"), saved.identity())
    assert caught.value.code == "source_changed"
    listed, problems = custom_templates(tmp_path)
    assert [t.name for t in listed] == ["Mine (copy)", "Renamed"] and problems == ()
    assert find_template(tmp_path, "mine") == renamed
    with pytest.raises(TemplateError) as caught:
        delete_template(tmp_path, "mine", saved.identity())
    assert caught.value.code == "source_changed"
    delete_template(tmp_path, "mine", renamed.identity())
    assert [t.id for t in custom_templates(tmp_path)[0]] == ["mine-2"]


def test_builtins_are_protected(tmp_path):
    template = replace(builtin("bold-garage"), builtin=False)
    with pytest.raises(TemplateError) as caught:
        save_template(tmp_path, template)
    assert caught.value.code == "template_builtin"
    with pytest.raises(TemplateError) as caught:
        delete_template(tmp_path, "bold-garage", template.identity())
    assert caught.value.code == "template_builtin"
    assert unique_id(tmp_path, "bold-garage") == "bold-garage-2"


def test_broken_custom_files_are_listed_not_hidden(tmp_path):
    folder = tmp_path / "cover-templates"
    folder.mkdir()
    (folder / "broken.json").write_text("{")
    (folder / "wrong.json").write_bytes(template_bytes(replace(builtin("bold-garage"), id="other")))
    templates, problems = custom_templates(tmp_path)
    assert templates == ()
    assert {(p.file, p.code) for p in problems} == {
        ("cover-templates/broken.json", "template_unreadable"),
        ("cover-templates/wrong.json", "id_mismatch"),
    }


@pytest.mark.skipif(os.name == "nt", reason="symlinks need privileges on Windows")
def test_symlinked_templates_are_refused(tmp_path):
    folder = tmp_path / "cover-templates"
    folder.mkdir()
    target = tmp_path / "elsewhere.json"
    target.write_bytes(template_bytes(replace(builtin("bold-garage"), id="link")))
    (folder / "link.json").symlink_to(target)
    _, problems = custom_templates(tmp_path)
    assert [p.code for p in problems] == ["not_file"]
    with pytest.raises(TemplateError) as caught:
        save_template(tmp_path, replace(builtin("bold-garage"), id="link", builtin=False))
    assert caught.value.code == "not_file"


def test_template_fonts_must_be_this_projects_files(tmp_path):
    font = tmp_path / "cover-assets" / "fonts" / "face.ttf"
    font.parent.mkdir(parents=True)
    font.write_bytes(b"font bytes")
    digest = hashlib.sha256(b"font bytes").hexdigest()
    data = raw("bold-garage")
    data["id"] = "with-font"
    data["fonts"] = [{"id": "face", "path": "cover-assets/fonts/face.ttf", "sha256": digest}]
    data["design"]["text"]["title"]["font"] = "face"
    template = read_template(data)
    assert "face" in template.faces()
    check_assets(template, tmp_path)
    font.write_bytes(b"other bytes")
    with pytest.raises(TemplateError) as caught:
        check_assets(template, tmp_path)
    assert caught.value.code == "template_font_missing"
