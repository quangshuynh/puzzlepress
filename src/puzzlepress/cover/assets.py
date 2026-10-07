"""Cover photographs: import, boundary-checked reads, decoding and normalization.

Originals are kept byte-for-byte in the project's `cover-assets/` directory under
content-addressed names and are never rewritten; crops are configuration. Decoding
normalizes once, in one place, for layout, preview and PDF alike: EXIF orientation
is applied, an embedded ICC profile is converted to sRGB (otherwise sRGB is
assumed), and the result is 8-bit RGB without alpha or metadata. Camera, location
and other EXIF/XMP data are never read beyond the orientation tag.
"""

import hashlib
import io
import os
import re
import tempfile
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, ImageCms, ImageOps, UnidentifiedImageError

from ..cover_config import ASSET_DIRECTORY, CoverImage
from .issues import CoverError, cover_error

MAX_ASSET_BYTES = 64 * 1024 * 1024
MAX_PIXELS = 80_000_000
FORMATS = {"JPEG": "jpg", "PNG": "png"}
ORIENTATION_TAG = 0x0112
_TRANSPOSED = {5, 6, 7, 8}  # EXIF orientations that swap width and height.
_SIGNATURES = (b"\xff\xd8", b"\x89PNG\r\n\x1a\n")  # JPEG and PNG file signatures.
_ASSET_NAME = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*\.(?:jpg|png)")


@dataclass(frozen=True)
class PhotoInfo:
    sha256: str
    format: str  # "jpeg" or "png".
    bytes: int
    stored_width: int  # Pixels as encoded.
    stored_height: int
    width: int  # Pixels upright, after EXIF orientation.
    height: int
    orientation: int  # EXIF orientation applied (1: none).
    color: str  # "srgb_assumed", "icc_converted" (to sRGB) or "grayscale".

    def to_dict(self) -> dict[str, object]:
        return {
            "sha256": self.sha256,
            "format": self.format,
            "bytes": self.bytes,
            "stored_pixels": [self.stored_width, self.stored_height],
            "pixels": [self.width, self.height],
            "orientation": self.orientation,
            "color": self.color,
        }


@dataclass(frozen=True, eq=False)
class Photo:
    """A decoded photograph: upright 8-bit sRGB pixels with no metadata attached."""

    info: PhotoInfo
    image: Image.Image


def _asset_error(code: str, message: str, **detail: str) -> CoverError:
    return cover_error("asset", code, message, region="cover.image", **detail)


def _open(data: bytes) -> tuple[Image.Image, str]:
    if not data:
        raise _asset_error("image_corrupt", "The photograph file is empty.")
    if len(data) > MAX_ASSET_BYTES:
        raise _asset_error(
            "image_unsupported",
            "The photograph file is too large.",
            actual=f"{len(data)} bytes",
            required=f"at most {MAX_ASSET_BYTES} bytes",
        )
    try:
        image = Image.open(io.BytesIO(data), formats=tuple(FORMATS))
    except UnidentifiedImageError as error:
        if data.startswith(_SIGNATURES):
            raise _asset_error(
                "image_corrupt", "The photograph is damaged or incomplete."
            ) from error
        raise _asset_error(
            "image_unsupported", "Use a JPEG or PNG photograph.", required="JPEG or PNG"
        ) from error
    except (OSError, ValueError, SyntaxError) as error:
        raise _asset_error("image_corrupt", f"The photograph cannot be read: {error}") from error
    if image.format not in FORMATS:
        raise _asset_error("image_unsupported", "Use a JPEG or PNG photograph.")
    width, height = image.size
    if width < 1 or height < 1 or width * height > MAX_PIXELS:
        raise _asset_error(
            "image_unsupported",
            "The photograph has too many pixels to process safely.",
            actual=f"{width}x{height}",
            required=f"at most {MAX_PIXELS} pixels",
        )
    return image, FORMATS[image.format]


def _orientation(image: Image.Image) -> int:
    try:
        value = image.getexif().get(ORIENTATION_TAG, 1)
    except (OSError, ValueError, SyntaxError):
        return 1
    return value if isinstance(value, int) and 1 <= value <= 8 else 1


def inspect_photo(data: bytes) -> PhotoInfo:
    """Header-level facts without decoding pixels. Raises CoverError(stage 'asset')."""
    image, kind = _open(data)
    orientation = _orientation(image)
    width, height = image.size
    upright = (height, width) if orientation in _TRANSPOSED else (width, height)
    color = (
        "grayscale"
        if image.mode in ("L", "LA")
        else "icc_converted"
        if image.info.get("icc_profile")
        else "srgb_assumed"
    )
    return PhotoInfo(
        hashlib.sha256(data).hexdigest(),
        "jpeg" if kind == "jpg" else "png",
        len(data),
        width,
        height,
        upright[0],
        upright[1],
        orientation,
        color,
    )


def _opaque(image: Image.Image) -> Image.Image:
    """Drop an alpha channel only when every pixel is fully opaque."""
    if image.mode == "P":
        image = image.convert("RGBA" if "transparency" in image.info else "RGB")
    if image.mode in ("RGBA", "LA", "PA"):
        low, _ = image.getchannel("A").getextrema()
        if low < 255:  # type: ignore[operator]
            raise _asset_error(
                "transparency_not_supported",
                "The photograph has transparent pixels; KDP covers must be flattened.",
            )
        image = image.convert("L" if image.mode == "LA" else "RGB")
    if image.mode not in ("RGB", "L"):
        raise _asset_error(
            "unsupported_color_mode",
            "Use an 8-bit RGB or grayscale photograph.",
            actual=image.mode,
            required="RGB or L (8-bit)",
        )
    return image


def _to_srgb(image: Image.Image, icc: bytes | None) -> Image.Image:
    if icc:
        try:
            source = ImageCms.ImageCmsProfile(io.BytesIO(icc))
            converted = ImageCms.profileToProfile(
                image,
                source,
                ImageCms.createProfile("sRGB"),
                renderingIntent=ImageCms.Intent.PERCEPTUAL,
                outputMode="RGB",
            )
        except (OSError, ValueError, ImageCms.PyCMSError) as error:
            raise _asset_error(
                "unsupported_color_mode",
                f"The photograph's embedded color profile cannot be applied: {error}",
            ) from error
        assert converted is not None
        image = converted
    return image.convert("RGB")


def decode_photo(data: bytes) -> Photo:
    """Decode and normalize. Raises CoverError(stage 'asset') for expected failures."""
    info = inspect_photo(data)
    image, _ = _open(data)
    icc = image.info.get("icc_profile")
    try:
        image.load()
        upright = ImageOps.exif_transpose(image)
        assert upright is not None
        rgb = _to_srgb(_opaque(upright), icc if isinstance(icc, bytes) else None)
    except CoverError:
        raise
    except (OSError, ValueError, SyntaxError, Image.DecompressionBombError) as error:
        raise _asset_error("image_corrupt", f"The photograph cannot be decoded: {error}") from error
    if rgb.size != (info.width, info.height):
        raise _asset_error("image_corrupt", "The photograph's orientation data is inconsistent.")
    rgb.info = {}  # Never carry comments, EXIF, XMP or ICC data toward the PDF.
    return Photo(info, rgb)


def asset_directory(project_directory: Path) -> Path:
    return project_directory / ASSET_DIRECTORY


def _checked_directory(project_directory: Path, create: bool) -> Path:
    """The real cover-assets directory directly inside the resolved project folder."""
    project = project_directory.resolve()
    directory = asset_directory(project)
    if directory.is_symlink() or (directory.exists() and not directory.is_dir()):
        raise _asset_error("asset_unsafe", f"{ASSET_DIRECTORY} must be a real directory.")
    if create:
        directory.mkdir(exist_ok=True)
    if directory.exists() and directory.resolve().parent != project:
        raise _asset_error("asset_unsafe", f"{ASSET_DIRECTORY} resolves outside the project.")
    return directory


def read_asset(project_directory: Path, image: CoverImage) -> bytes:
    """Read the configured photo inside cover-assets and verify its pinned digest."""
    directory = _checked_directory(project_directory, create=False)
    name = image.path.removeprefix(f"{ASSET_DIRECTORY}/")
    path = directory / name
    if not _ASSET_NAME.fullmatch(name) or path.is_symlink():
        raise _asset_error("asset_unsafe", "The photograph reference is not a project asset.")
    try:
        if not path.is_file():
            raise _asset_error(
                "image_missing", f"The photograph {image.path} is missing from the project."
            )
        if path.stat().st_size > MAX_ASSET_BYTES:
            raise _asset_error("image_unsupported", "The photograph file is too large.")
        data = path.read_bytes()
    except OSError as error:
        raise _asset_error("image_missing", f"Cannot read {image.path}: {error}") from error
    actual = hashlib.sha256(data).hexdigest()
    if actual != image.sha256:
        raise _asset_error(
            "asset_digest_mismatch",
            f"{image.path} changed since it was chosen; re-select it to accept the new photo.",
            actual=actual,
            required=image.sha256,
        )
    return data


def asset_name(original_name: str, sha256: str, extension: str) -> str:
    stem = Path(original_name.replace("\\", "/").rsplit("/", 1)[-1]).stem.lower()
    stem = re.sub(r"[^a-z0-9]+", "-", stem).strip("-")[:40].strip("-") or "photo"
    return f"{stem}-{sha256[:12]}.{extension}"


@dataclass(frozen=True)
class ImportedPhoto:
    path: str  # Project-relative reference for the cover configuration.
    info: PhotoInfo
    reused: bool  # The identical bytes were already in cover-assets.


def import_photo(project_directory: Path, data: bytes, original_name: str) -> ImportedPhoto:
    """Copy a validated photograph into cover-assets without overwriting anything.

    The name is content-addressed, so importing the same bytes twice reuses the
    existing file; a different file under that name is refused, never replaced.
    """
    photo = decode_photo(data)  # Validate fully before anything is written.
    info = photo.info
    name = asset_name(original_name, info.sha256, "jpg" if info.format == "jpeg" else "png")
    directory = _checked_directory(project_directory, create=True)
    target = directory / name
    reference = f"{ASSET_DIRECTORY}/{name}"

    def existing() -> ImportedPhoto:
        if target.is_symlink() or not target.is_file() or target.read_bytes() != data:
            raise _asset_error(
                "asset_collision", f"{reference} already exists with different content."
            )
        return ImportedPhoto(reference, info, True)

    if target.exists() or target.is_symlink():
        return existing()
    suffix = name[name.rindex("-") :]
    for candidate in sorted(directory.glob(f"*{suffix}")):
        # The same photo imported earlier under another original name.
        if (
            _ASSET_NAME.fullmatch(candidate.name)
            and not candidate.is_symlink()
            and candidate.is_file()
            and candidate.read_bytes() == data
        ):
            return ImportedPhoto(f"{ASSET_DIRECTORY}/{candidate.name}", info, True)
    handle, staged_name = tempfile.mkstemp(prefix=".cover-import-", suffix=".tmp", dir=directory)
    staged = Path(staged_name)
    try:
        with os.fdopen(handle, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        if staged.read_bytes() != data:
            raise _asset_error("write_failed", "The staged photograph does not match.")
        try:
            os.link(staged, target)  # Atomic and never replaces an existing file.
        except FileExistsError:
            return existing()
    except OSError as error:
        raise _asset_error("write_failed", f"Cannot import the photograph: {error}") from error
    finally:
        staged.unlink(missing_ok=True)
    return ImportedPhoto(reference, info, False)


@dataclass(frozen=True)
class AssetEntry:
    path: str
    info: PhotoInfo | None
    problem: str | None = None


def list_assets(project_directory: Path) -> tuple[AssetEntry, ...]:
    """Photographs in cover-assets with header facts; unreadable files are reported."""
    directory = _checked_directory(project_directory, create=False)
    if not directory.is_dir():
        return ()
    entries: list[AssetEntry] = []
    for path in sorted(directory.iterdir(), key=lambda p: p.name):
        if not _ASSET_NAME.fullmatch(path.name) or path.is_symlink() or not path.is_file():
            continue
        reference = f"{ASSET_DIRECTORY}/{path.name}"
        try:
            entries.append(AssetEntry(reference, inspect_photo(path.read_bytes())))
        except CoverError as error:
            entries.append(AssetEntry(reference, None, error.issues[0].code))
        except OSError:
            entries.append(AssetEntry(reference, None, "image_missing"))
    return tuple(entries)
