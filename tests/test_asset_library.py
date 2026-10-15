"""Asset library: references, duplicates, reversible removal and filesystem boundaries."""

import hashlib
import os
from dataclasses import replace

import pytest

from puzzlepress import asset_library as library_module
from puzzlepress import load_project
from puzzlepress.asset_library import (
    AssetError,
    asset_uses,
    library,
    list_trash,
    purge_asset,
    restore_asset,
    trash_asset,
    unmanaged,
)
from puzzlepress.cover.assets import import_photo
from puzzlepress.cover.build import cover_identity, cover_inputs
from puzzlepress.cover.font_assets import import_font
from puzzlepress.identity import build_identity
from puzzlepress.validation import validate_project
from tests.cover_helpers import cover_project, photo_bytes
from tests.font_helpers import bundled as font_bytes


def _sha(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


@pytest.fixture
def project(tmp_path):
    source, _ = cover_project(tmp_path, build_interior=False)
    spare = import_photo(source, photo_bytes(600, 400), "spare.jpg")
    return source, load_project(source).project, spare


def test_library_lists_assets_with_their_uses(project):
    source, saved, spare = project
    entries = {e.path: e for e in library(source, saved)}
    used = entries[saved.cover.image.path]
    assert used.in_use if hasattr(used, "in_use") else used.uses
    assert [u.label for u in used.uses] == ["Cover photograph"]
    assert entries[spare.path].uses == () and entries[spare.path].sha256 == spare.info.sha256
    assert entries[spare.path].to_dict()["facts"]["pixels"] == [600, 400]


def test_duplicate_imports_reuse_the_same_file(project):
    source, _, spare = project
    data = (source / spare.path).read_bytes()
    again = import_photo(source, data, "another-name.jpg")
    assert again.reused and again.path == spare.path
    names = [p.name for p in (source / "cover-assets").iterdir() if p.is_file()]
    assert len([n for n in names if spare.info.sha256[:12] in n]) == 1


def test_unused_photo_moves_to_trash_and_restores(project):
    source, saved, spare = project
    before = (source / spare.path).read_bytes()
    moved = trash_asset(source, spare.path, spare.info.sha256, saved)
    assert not (source / spare.path).exists()
    assert (source / moved.trashed).read_bytes() == before
    assert spare.path not in {e.path for e in library(source, saved)}
    (entry,) = list_trash(source)
    assert entry.restores_to == spare.path and entry.sha256 == spare.info.sha256
    assert restore_asset(source, entry.trashed) == spare.path
    assert (source / spare.path).read_bytes() == before and list_trash(source) == ()


def test_purge_needs_the_confirmed_digest(project):
    source, saved, spare = project
    moved = trash_asset(source, spare.path, spare.info.sha256, saved)
    with pytest.raises(AssetError) as error:
        purge_asset(source, moved.trashed, "0" * 64)
    assert error.value.code == "asset_changed" and (source / moved.trashed).exists()
    purge_asset(source, moved.trashed, spare.info.sha256)
    assert not (source / moved.trashed).exists()


def test_referenced_assets_are_never_removed(project):
    source, saved, spare = project
    photo = saved.cover.image
    with pytest.raises(AssetError) as error:
        trash_asset(source, photo.path, photo.sha256, saved)
    assert error.value.code == "asset_in_use" and error.value.uses[0].source == "saved"
    assert (source / photo.path).exists()
    data = saved.to_dict()
    data["cover"]["image"] = {"path": spare.path, "sha256": spare.info.sha256}
    draft = validate_project(data).require_project()
    with pytest.raises(AssetError) as error:
        trash_asset(source, spare.path, spare.info.sha256, saved, draft)
    assert error.value.code == "asset_in_use"
    assert [u.source for u in error.value.uses] == ["draft"]


def test_every_reference_kind_is_found(tmp_path):
    source, _ = cover_project(tmp_path, build_interior=False)
    saved = load_project(source).project
    font = import_font(source, font_bytes(), "display.ttf")
    other = import_photo(source, photo_bytes(800, 600), "inset.jpg")
    data = saved.to_dict()
    cover = data["cover"]
    data["cover"] = {
        "version": 3,
        "regions": {k: {"color": "#112233"} for k in ("back", "spine", "front")},
        "fonts": [{"id": "display", "path": font.path, "sha256": font.info.sha256}],
        "elements": [
            {"id": "front", "type": "photo", "region": "front", "image": cover["image"]},
            {
                "id": "inset",
                "type": "photo",
                "region": "back",
                "visible": False,
                "image": {"path": other.path, "sha256": other.info.sha256},
                "box": {"x": 72, "y": 300, "width": 200, "height": 150},
            },
        ],
    }
    data["interior"] = {
        "version": 1,
        "title_page": {
            "layout": "photo_feature",
            "photo": {"image": {"path": other.path, "sha256": other.info.sha256}},
        },
    }
    designed = validate_project(data).require_project()
    assert [u.path for u in asset_uses(other.path, designed)] == [
        "cover.elements.1.image",
        "interior.title_page.photo.image",
    ]
    assert "(hidden)" in asset_uses(other.path, designed)[0].label
    assert [u.path for u in asset_uses(font.path, designed)] == ["cover.fonts.0"]
    with pytest.raises(AssetError):
        trash_asset(source, font.path, font.info.sha256, designed)


def test_unused_fonts_trash_and_restore(tmp_path):
    source, _ = cover_project(tmp_path, build_interior=False)
    saved = load_project(source).project
    font = import_font(source, font_bytes(), "display.ttf")
    moved = trash_asset(source, font.path, font.info.sha256, saved)
    assert moved.trashed.startswith("cover-assets/.trash/fonts/")
    assert [e.restores_to for e in list_trash(source)] == [font.path]


@pytest.mark.parametrize(
    "reference",
    [
        "cover-assets/../book.yaml",
        "../outside.jpg",
        "/etc/passwd",
        "cover-assets/fonts/../../book.yaml",
        "cover-assets/Vera.ttf",
        "cover-assets/fonts/Vera.ttf",
        "cover-assets/.trash/spare-1.jpg",
        "book.yaml",
        "cover-assets\\spare.jpg",
    ],
)
def test_unsafe_references_are_refused(project, reference):
    source, saved, _ = project
    with pytest.raises(AssetError) as error:
        trash_asset(source, reference, "0" * 64, saved)
    assert error.value.code in ("asset_unsafe", "asset_missing")
    assert (source / "book.yaml").exists()


def test_changed_bytes_are_not_moved(project):
    source, saved, spare = project
    with pytest.raises(AssetError) as error:
        trash_asset(source, spare.path, "f" * 64, saved)
    assert error.value.code == "asset_changed" and (source / spare.path).exists()


def test_interrupted_move_leaves_the_asset_in_place(project, monkeypatch):
    source, saved, spare = project

    def fail(*args, **kwargs):
        raise OSError("disk unplugged")

    monkeypatch.setattr(library_module.os, "replace", fail)
    with pytest.raises(OSError):
        trash_asset(source, spare.path, spare.info.sha256, saved)
    assert (source / spare.path).read_bytes()
    assert list_trash(source) == ()


def test_restore_never_overwrites(project):
    source, saved, spare = project
    data = (source / spare.path).read_bytes()
    moved = trash_asset(source, spare.path, spare.info.sha256, saved)
    import_photo(source, data, "spare.jpg")  # The same bytes imported again meanwhile.
    with pytest.raises(AssetError) as error:
        restore_asset(source, moved.trashed)
    assert error.value.code == "asset_collision"


def test_unused_asset_operations_change_no_identity(tmp_path):
    source, output = cover_project(tmp_path)
    saved = load_project(source).project
    spare = import_photo(source, photo_bytes(600, 400), "spare.jpg")
    from puzzlepress.cover.build import read_interior_facts

    facts = read_interior_facts(output, saved)
    before = (build_identity(saved), cover_identity(cover_inputs(saved, saved.cover, facts)))
    trash_asset(source, spare.path, spare.info.sha256, saved)
    after_project = load_project(source).project
    assert after_project == saved
    after = (
        build_identity(after_project),
        cover_identity(cover_inputs(after_project, after_project.cover, facts)),
    )
    assert before == after


def test_unmanaged_files_are_reported_not_touched(project):
    source, saved, _ = project
    stray = source / "cover-assets" / "Holiday Photo.PNG"
    stray.write_bytes(photo_bytes(40, 30, fmt="PNG"))
    assert unmanaged(source) == ("Holiday Photo.PNG",)
    assert "cover-assets/Holiday Photo.PNG" not in {e.path for e in library(source, saved)}


def test_symlinked_asset_directories_are_refused(tmp_path):
    source, _ = cover_project(tmp_path / "a", build_interior=False)
    saved = load_project(source).project
    spare = import_photo(source, photo_bytes(600, 400), "spare.jpg")
    outside = tmp_path / "outside"
    outside.mkdir()
    try:
        os.symlink(outside, source / "cover-assets" / ".trash", target_is_directory=True)
    except OSError:
        pytest.skip("Creating symlinks requires OS permission on this host")
    with pytest.raises(AssetError) as error:
        trash_asset(source, spare.path, spare.info.sha256, saved)
    assert error.value.code == "asset_unsafe" and (source / spare.path).exists()
    assert list(outside.iterdir()) == []


def test_replace_keeps_project_frozen(project):
    _, saved, _ = project
    assert replace(saved) == saved
