"""Imported cover fonts: validation, embedding permissions, import, PDF embedding."""

import hashlib
import io

import pytest
from pypdf import PdfReader

from puzzlepress.cover.build import build_cover, write_cover
from puzzlepress.cover.font_assets import (
    MAX_FONT_BYTES,
    import_font,
    inspect_font,
    list_fonts,
    load_cover_fonts,
    read_font,
)
from puzzlepress.cover.issues import CoverError
from puzzlepress.cover.preflight import preflight_cover
from puzzlepress.cover_config import CoverFont
from puzzlepress.interior import build_interior, print_profile, write_interior
from puzzlepress.project import load_project
from puzzlepress.validation import validate_project
from puzzlepress.yaml_io import dump_project
from tests.cover_helpers import cover_project
from tests.font_helpers import (
    ITALIC,
    bundled,
    cff_signature,
    collection,
    renamed_table,
    with_fs_type,
)


def code(data: bytes) -> str:
    with pytest.raises(CoverError) as error:
        inspect_font(data)
    return error.value.issues[0].code


def test_static_truetype_font_is_read_from_memory():
    info, ttf = inspect_font(bundled())
    assert info.postscript_name == "Newsreader16pt-Regular"
    assert info.family == "Newsreader 16pt" and info.style == "Regular"
    assert info.embedding == "installable" and info.glyphs > 200
    assert info.sha256 == hashlib.sha256(bundled()).hexdigest()
    assert ord("A") in ttf.face.charToGlyph


@pytest.mark.parametrize(
    ("fs_type", "embedding"),
    [(0x0000, "installable"), (0x0004, "preview_print"), (0x0008, "editable")],
)
def test_embeddable_permissions_are_accepted_and_named(fs_type, embedding):
    assert inspect_font(with_fs_type(fs_type))[0].embedding == embedding


@pytest.mark.parametrize("fs_type", [0x0002, 0x0100, 0x0200, 0x0104, 0x0001])
def test_restricted_or_unsubsettable_fonts_are_refused(fs_type):
    assert code(with_fs_type(fs_type)) == "font_embedding_restricted"


@pytest.mark.parametrize(
    ("data", "expected"),
    [
        (b"", "font_corrupt"),
        (b"\x00\x01\x00\x00", "font_corrupt"),
        (bundled()[:4000], "font_corrupt"),
        (b"not a font at all", "font_corrupt"),
        (cff_signature(), "font_unsupported_outlines"),
        (collection(), "font_collection_unsupported"),
        (b"wOFF" + bundled()[4:], "font_unsupported"),
        (renamed_table(b"DSIG", b"fvar"), "font_variable_unsupported"),
        (renamed_table(b"OS/2", b"XXXX"), "font_corrupt"),
        (bundled()[:-200] + b"\0" * 200, "font_corrupt"),
    ],
    ids=[
        "empty",
        "header-only",
        "truncated",
        "text",
        "cff",
        "collection",
        "woff",
        "variable",
        "no-os2",
        "bad-checksum",
    ],
)
def test_unsupported_and_damaged_fonts_fail_safely(data, expected):
    assert code(data) == expected


def test_oversized_font_is_refused_before_parsing():
    assert code(b"\0\1\0\0" + b"\0" * MAX_FONT_BYTES) == "font_unsupported"


def test_import_copies_bytes_reuses_identical_files_and_never_overwrites(tmp_path):
    data = bundled(ITALIC)
    first = import_font(tmp_path, data, "My Display.TTF")
    assert first.path.startswith("cover-assets/fonts/my-display-") and not first.reused
    assert (tmp_path / first.path).read_bytes() == data
    again = import_font(tmp_path, data, "other-name.ttf")
    assert again.reused and again.path == first.path
    with pytest.raises(CoverError) as error:
        import_font(tmp_path, b"junk", "bad.ttf")
    assert error.value.issues[0].code == "font_corrupt"
    with pytest.raises(CoverError):
        import_font(tmp_path, data, "font.woff2")
    assert [entry.path for entry in list_fonts(tmp_path)] == [first.path]


def test_restricted_font_is_never_written(tmp_path):
    with pytest.raises(CoverError):
        import_font(tmp_path, with_fs_type(0x0002), "locked.ttf")
    assert not (tmp_path / "cover-assets" / "fonts").exists() or not any(
        p for p in (tmp_path / "cover-assets" / "fonts").iterdir() if not p.name.startswith(".")
    )


def test_reading_a_configured_font_checks_its_digest_and_boundary(tmp_path):
    imported = import_font(tmp_path, bundled(ITALIC), "italic.ttf")
    font = CoverFont("italic", imported.path, imported.info.sha256)
    assert read_font(tmp_path, font) == bundled(ITALIC)
    (tmp_path / imported.path).write_bytes(bundled())
    with pytest.raises(CoverError) as error:
        read_font(tmp_path, font)
    assert error.value.issues[0].code == "asset_digest_mismatch"
    missing = CoverFont("gone", "cover-assets/fonts/gone-1.ttf", "0" * 64)
    with pytest.raises(CoverError) as error:
        read_font(tmp_path, missing)
    assert error.value.issues[0].code == "font_missing"


def _font_cover(tmp_path, *, license=None, text=None):
    """A built interior beside a version 2 cover whose title uses an imported font."""
    source, output = cover_project(tmp_path, build_interior=False)
    imported = import_font(source, bundled(ITALIC), "display.ttf")
    project = load_project(source / "book.yaml").project.to_dict()
    project["cover"]["version"] = 2
    project["cover"]["fonts"] = [
        {
            "id": "display",
            "path": imported.path,
            "sha256": imported.info.sha256,
            **({"license": license, "source": "Test fixture"} if license else {}),
        }
    ]
    project["cover"]["text"] = text or {"title": {"font": "display"}}
    valid = validate_project(project).require_project()
    (source / "book.yaml").write_text(dump_project(valid), encoding="utf-8")
    write_interior(build_interior(valid, print_profile("paperback-8.5x11")), output, source)
    return source, output, valid


def test_imported_font_is_embedded_as_a_subset_in_the_final_pdf(tmp_path):
    source, output, project = _font_cover(tmp_path, license="SIL Open Font License 1.1")
    build = build_cover(project, source, output)
    page = PdfReader(io.BytesIO(build.pdf)).pages[0]
    fonts = {str(f["/BaseFont"]) for f in page["/Resources"]["/Font"].values()}
    assert any(name.endswith("+Newsreader16pt-Italic") for name in fonts)
    descriptors = [
        f["/FontDescriptor"] for f in page["/Resources"]["/Font"].values() if "Italic" in str(f)
    ]
    assert all("/FontFile2" in d for d in descriptors)
    assert build.layout.fonts == ("Newsreader16pt-Italic",)
    assert any(
        t.role == "title" and t.face.startswith("PuzzlePressFont-") for t in build.layout.texts
    )
    again = build_cover(project, source, output)
    assert again.pdf == build.pdf and again.manifest == build.manifest
    write_cover(build, output, source)
    report = preflight_cover(project, source, output)
    outcomes = {r.rule.code: r.outcome.value for r in report.results}
    assert outcomes["cover_fonts"] == "passed"
    assert outcomes["cover_font_license"] == "passed"
    assert report.structurally_valid


def test_unknown_font_license_is_a_warning_not_a_block(tmp_path):
    source, output, project = _font_cover(tmp_path)
    write_cover(build_cover(project, source, output), output, source)
    report = preflight_cover(project, source, output)
    findings = [f for f in report.findings if f.rule.code == "cover_font_license"]
    assert findings and findings[0].severity.value == "warning"
    assert report.structurally_valid


def test_a_font_changed_on_disk_blocks_the_build_and_preflight(tmp_path):
    source, output, project = _font_cover(tmp_path, license="OFL")
    assert project.cover is not None
    font_path = source / project.cover.fonts[0].path
    font_path.write_bytes(bundled())
    with pytest.raises(CoverError) as error:
        build_cover(project, source, output)
    assert error.value.issues[0].code == "asset_digest_mismatch"
    report = preflight_cover(project, source, output)
    outcomes = {r.rule.code: r.outcome.value for r in report.results}
    assert outcomes["cover_fonts"] == "failed"
    assert outcomes["cover_buildable"] == "not_evaluated"


def test_missing_glyphs_in_an_imported_font_are_reported(tmp_path):
    source, output, project = _font_cover(
        tmp_path, license="OFL", text={"title": {"font": "display", "text": "Ωmega Puzzles"}}
    )
    with pytest.raises(CoverError) as error:
        build_cover(project, source, output)
    issue = error.value.issues[0]
    assert issue.code == "unsupported_character" and issue.actual == "U+03A9"
    assert issue.required == "characters the chosen font contains"


def test_cover_fonts_load_only_named_project_files(tmp_path):
    source, _, project = _font_cover(tmp_path, license="OFL")
    assert project.cover is not None
    loaded = load_cover_fonts(source, project.cover)
    assert set(loaded.by_id) == {"display"}
    assert loaded.key("display").startswith("PuzzlePressFont-")
