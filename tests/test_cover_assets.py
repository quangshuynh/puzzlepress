"""Photo import, digest-pinned reads, decoding, EXIF orientation and normalization."""

import hashlib
import io

import pytest
from PIL import Image, ImageCms

from puzzlepress.cover import assets
from puzzlepress.cover.assets import (
    decode_photo,
    import_photo,
    inspect_photo,
    list_assets,
    read_asset,
)
from puzzlepress.cover.issues import CoverError
from puzzlepress.cover_config import CoverImage
from tests.cover_helpers import BLUE, GREEN, RED, WHITE, photo_bytes


def code(error: pytest.ExceptionInfo[CoverError]) -> str:
    assert error.value.stage == "asset"
    return error.value.issues[0].code


def near(actual, expected, tolerance=12):
    return all(abs(a - b) <= tolerance for a, b in zip(actual, expected, strict=True))


def corners(image):
    w, h = image.size
    return [image.getpixel((x, y)) for x, y in ((w // 4, h // 4), (3 * w // 4, h // 4))] + [
        image.getpixel((x, y)) for x, y in ((w // 4, 3 * h // 4), (3 * w // 4, 3 * h // 4))
    ]


@pytest.mark.parametrize("orientation", range(1, 9))
def test_every_exif_orientation_decodes_upright(orientation):
    data = photo_bytes(120, 80, orientation=orientation)
    info = inspect_photo(data)
    assert (info.width, info.height, info.orientation) == (120, 80, orientation)
    swapped = orientation in (5, 6, 7, 8)
    assert (info.stored_width, info.stored_height) == ((80, 120) if swapped else (120, 80))
    photo = decode_photo(data)
    assert photo.image.size == (120, 80) and photo.image.mode == "RGB"
    for actual, expected in zip(corners(photo.image), (RED, GREEN, BLUE, WHITE), strict=True):
        assert near(actual, expected)


def test_png_and_grayscale_are_normalized_to_rgb_without_metadata():
    png = decode_photo(photo_bytes(64, 48, fmt="PNG"))
    assert png.info.format == "png" and png.image.mode == "RGB"
    assert corners(png.image) == [RED, GREEN, BLUE, WHITE]
    gray = Image.linear_gradient("L").resize((40, 30))
    decoded = decode_photo(photo_bytes(image=gray, fmt="PNG"))
    assert decoded.info.color == "grayscale" and decoded.image.mode == "RGB"
    assert decoded.image.info == {} and png.image.info == {}


def test_private_metadata_is_never_carried_by_decoded_pixels():
    data = photo_bytes(private=True)
    assert all(marker in data for marker in (b"LEAKCAM", b"LEAKCOMMENT"))
    photo = decode_photo(data)
    assert photo.image.info == {}
    assert len(photo.image.getexif()) == 0


def test_embedded_icc_profile_is_converted_to_srgb():
    srgb = ImageCms.ImageCmsProfile(ImageCms.createProfile("sRGB")).tobytes()
    photo = decode_photo(photo_bytes(icc=srgb))
    assert photo.info.color == "icc_converted"
    assert near(corners(photo.image)[0], RED)
    with pytest.raises(CoverError) as error:
        decode_photo(photo_bytes(icc=b"not a profile"))
    assert code(error) == "unsupported_color_mode"


def test_opaque_alpha_is_dropped_and_transparency_rejected():
    opaque = Image.new("RGBA", (20, 20), (10, 20, 30, 255))
    assert decode_photo(photo_bytes(image=opaque, fmt="PNG")).image.mode == "RGB"
    clear = opaque.copy()
    clear.putpixel((3, 3), (10, 20, 30, 254))
    with pytest.raises(CoverError) as error:
        decode_photo(photo_bytes(image=clear, fmt="PNG"))
    assert code(error) == "transparency_not_supported"
    palette = Image.new("P", (10, 10), 0)
    palette.info["transparency"] = 0
    with pytest.raises(CoverError) as error:
        decode_photo(photo_bytes(image=palette, fmt="PNG"))
    assert code(error) == "transparency_not_supported"


def _encoded(image, fmt, **params):
    buffer = io.BytesIO()
    image.save(buffer, fmt, **params)
    return buffer.getvalue()


@pytest.mark.parametrize(
    ("data", "expected"),
    [
        (b"", "image_corrupt"),
        (b"plain text, not an image", "image_unsupported"),
        (_encoded(Image.new("RGB", (8, 8)), "GIF"), "image_unsupported"),
        (_encoded(Image.new("RGB", (8, 8)), "BMP"), "image_unsupported"),
        (_encoded(Image.new("CMYK", (8, 8)), "JPEG"), "unsupported_color_mode"),
        (_encoded(Image.new("I;16", (8, 8)), "PNG"), "unsupported_color_mode"),
        (_encoded(Image.new("1", (8, 8)), "PNG"), "unsupported_color_mode"),
        (photo_bytes(400, 300)[:900], "image_corrupt"),
    ],
)
def test_unusable_files_fail_with_structured_codes(data, expected):
    with pytest.raises(CoverError) as error:
        decode_photo(data)
    assert code(error) == expected


def test_size_limits_are_checked_before_decoding(monkeypatch):
    monkeypatch.setattr(assets, "MAX_PIXELS", 100 * 80 - 1)
    with pytest.raises(CoverError) as error:
        inspect_photo(photo_bytes(100, 80))
    assert code(error) == "image_unsupported"
    monkeypatch.setattr(assets, "MAX_PIXELS", 100 * 80)
    assert inspect_photo(photo_bytes(100, 80)).width == 100
    monkeypatch.setattr(assets, "MAX_ASSET_BYTES", 10)
    with pytest.raises(CoverError) as error:
        inspect_photo(photo_bytes())
    assert code(error) == "image_unsupported"


def test_import_copies_original_bytes_under_a_content_name(tmp_path):
    data = photo_bytes(private=True)
    digest = hashlib.sha256(data).hexdigest()
    imported = import_photo(tmp_path, data, r"C:\Users\me\Pictures\Harbour At Dawn!.JPG")
    assert imported.path == f"cover-assets/harbour-at-dawn-{digest[:12]}.jpg"
    assert not imported.reused and imported.info.sha256 == digest
    # The original stays byte-for-byte: privacy is enforced at rendering, not import.
    assert (tmp_path / imported.path).read_bytes() == data
    # Identical bytes under another name, even a traversal attempt, reuse the asset.
    again = import_photo(tmp_path, data, "../../escape.jpg")
    assert again.reused and again.path == imported.path
    same = import_photo(tmp_path, data, "Harbour at dawn.jpg")
    assert same.reused and same.path == imported.path
    assert [p.name for p in (tmp_path / "cover-assets").iterdir()] == [imported.path.split("/")[1]]
    png = import_photo(tmp_path, photo_bytes(fmt="PNG"), "日本.jpeg")
    assert png.path.startswith("cover-assets/photo-") and png.path.endswith(".png")


def test_import_never_overwrites_and_writes_nothing_for_bad_photos(tmp_path):
    data = photo_bytes()
    name = assets.asset_name("x.jpg", hashlib.sha256(data).hexdigest(), "jpg")
    (tmp_path / "cover-assets").mkdir()
    (tmp_path / "cover-assets" / name).write_bytes(b"someone else's file")
    with pytest.raises(CoverError) as error:
        import_photo(tmp_path, data, "x.jpg")
    assert code(error) == "asset_collision"
    assert (tmp_path / "cover-assets" / name).read_bytes() == b"someone else's file"
    with pytest.raises(CoverError):
        import_photo(tmp_path, b"not an image", "y.jpg")
    assert [p.name for p in (tmp_path / "cover-assets").iterdir()] == [name]


def test_import_refuses_a_cover_assets_file(tmp_path):
    (tmp_path / "cover-assets").write_text("not a directory")
    with pytest.raises(CoverError) as error:
        import_photo(tmp_path, photo_bytes(), "x.jpg")
    assert code(error) == "asset_unsafe"


def test_read_asset_verifies_presence_and_pinned_digest(tmp_path):
    data = photo_bytes()
    imported = import_photo(tmp_path, data, "a.jpg")
    reference = CoverImage(imported.path, imported.info.sha256)
    assert read_asset(tmp_path, reference) == data
    with pytest.raises(CoverError) as error:
        read_asset(tmp_path, CoverImage(imported.path, "0" * 64))
    assert code(error) == "asset_digest_mismatch"
    with pytest.raises(CoverError) as error:
        read_asset(tmp_path, CoverImage("cover-assets/gone.jpg", "0" * 64))
    assert code(error) == "image_missing"
    (tmp_path / imported.path).write_bytes(photo_bytes(fmt="PNG"))
    with pytest.raises(CoverError) as error:
        read_asset(tmp_path, reference)
    assert code(error) == "asset_digest_mismatch"


def test_list_assets_reports_photos_and_unreadable_files(tmp_path):
    assert list_assets(tmp_path) == ()
    imported = import_photo(tmp_path, photo_bytes(orientation=6), "side.jpg")
    (tmp_path / "cover-assets" / "broken.jpg").write_bytes(b"\xff\xd8 truncated")
    (tmp_path / "cover-assets" / "Ignored Name.jpg").write_bytes(b"x")
    (tmp_path / "cover-assets" / "notes.txt").write_text("x")
    entries = list_assets(tmp_path)
    assert [entry.path for entry in entries] == ["cover-assets/broken.jpg", imported.path]
    assert entries[0].info is None and entries[0].problem == "image_corrupt"
    info = entries[1].info
    assert info is not None and (info.width, info.height, info.orientation) == (120, 80, 6)
