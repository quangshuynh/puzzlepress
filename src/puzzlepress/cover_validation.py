"""Schema-v1 optional cover section. Collects independent issues; never repairs."""

import math
import re
from typing import TypeVar

from .composition_validation import _body
from .content_validation import _Reader
from .cover_config import (
    ASSET_DIRECTORY,
    COVER_VERSION,
    CROP_DECIMALS,
    MAX_BACK_TEXT,
    MAX_ZOOM,
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
from .errors import ValidationIssue

# A portable asset reference: one level below cover-assets, lowercase, no traversal.
ASSET_PATH = re.compile(rf"{ASSET_DIRECTORY}/[a-z0-9]+(?:-[a-z0-9]+)*\.(?:jpg|png)")
MAX_ASSET_PATH = 160
SHA256 = re.compile(r"[0-9a-f]{64}")
HEX_COLOR = re.compile(r"#[0-9a-fA-F]{6}")
Choice = TypeVar(
    "Choice",
    CoverLayoutKind,
    CoverStyle,
    TitlePosition,
    TextAlign,
    TextTone,
    Legibility,
    SpineText,
)
FIELDS = {
    "version",
    "layout",
    "image",
    "crop",
    "type",
    "legibility",
    "background",
    "spine_text",
    "back_text",
}


def validate_cover(
    value: object, has_composition: bool
) -> tuple[CoverConfig | None, tuple[ValidationIssue, ...]]:
    """Validate the cover section; `has_composition` states whether one is declared."""
    reader = _Reader()
    path = "cover"
    data = reader.mapping(value, path, FIELDS)
    if not isinstance(value, dict):
        return None, tuple(reader.issues)
    if not has_composition:
        reader.issue(
            path,
            "requires_composition",
            "A cover requires a book composition: its spine is sized by the built interior.",
        )
    version = data.get("version")
    if type(version) is not int or version != COVER_VERSION:
        reader.issue(
            f"{path}.version",
            "unsupported_version",
            f"Cover version {version!r} is not supported. Supported versions: {COVER_VERSION}.",
        )
        return None, tuple(reader.issues)
    image = _image(reader, data.get("image"), f"{path}.image", "image" in data)
    crop = _crop(reader, data.get("crop", {}), f"{path}.crop")
    kind = _choice(reader, data.get("layout", "full_wrap"), f"{path}.layout", CoverLayoutKind)
    cover_type = _type(reader, data.get("type", {}), f"{path}.type")
    legibility = _choice(reader, data.get("legibility", "shade"), f"{path}.legibility", Legibility)
    spine = _choice(reader, data.get("spine_text", "auto"), f"{path}.spine_text", SpineText)
    background = data.get("background", CoverConfig.background)
    if not isinstance(background, str) or not HEX_COLOR.fullmatch(background):
        reader.issue(f"{path}.background", "color", "Use a #RRGGBB sRGB color.")
        background = CoverConfig.background
    back_text = None
    if "back_text" in data:
        back_text = _body(reader, data["back_text"], f"{path}.back_text")
        if len(back_text) > MAX_BACK_TEXT:
            reader.issue(
                f"{path}.back_text", "text", f"Back-cover text is limited to {MAX_BACK_TEXT}."
            )
    if reader.issues or image is None:
        return None, tuple(reader.issues)
    return (
        CoverConfig(
            image=image,
            layout=kind,
            crop=crop,
            type=cover_type,
            legibility=legibility,
            background=background.lower(),
            spine_text=spine,
            back_text=back_text,
        ),
        (),
    )


def _choice(reader: _Reader, value: object, path: str, enum: type[Choice]) -> Choice:
    names = [member.value for member in enum]
    if not isinstance(value, str) or value not in names:
        reader.issue(path, "choice", f"Use one of: {', '.join(names)}.")
        return next(iter(enum))
    return enum(value)


def _image(reader: _Reader, raw: object, path: str, present: bool) -> CoverImage | None:
    if not present:
        reader.issue(path, "required", "Choose a photograph from cover-assets.")
        return None
    data = reader.mapping(raw, path, {"path", "sha256"})
    asset = data.get("path")
    digest = data.get("sha256")
    valid = True
    if not isinstance(asset, str) or len(asset) > MAX_ASSET_PATH or not ASSET_PATH.fullmatch(asset):
        reader.issue(
            f"{path}.path",
            "asset_path",
            f"Use {ASSET_DIRECTORY}/<lowercase-name>.jpg or .png inside the project.",
        )
        valid = False
    if not isinstance(digest, str) or not SHA256.fullmatch(digest):
        reader.issue(f"{path}.sha256", "digest", "Expected the photo's 64-character SHA-256.")
        valid = False
    if not valid:
        return None
    assert isinstance(asset, str) and isinstance(digest, str)
    return CoverImage(asset, digest)


def _number(reader: _Reader, raw: object, path: str, low: float, high: float, code: str) -> float:
    if not isinstance(raw, int | float) or isinstance(raw, bool) or not math.isfinite(raw):
        reader.issue(path, "crop_invalid", "Expected a number.")
        return low
    value = round(float(raw), CROP_DECIMALS)
    if not low <= value <= high:
        reader.issue(path, code, f"Expected a value from {low:g} to {high:g}.")
        return low
    return value


def _crop(reader: _Reader, raw: object, path: str) -> Crop:
    data = reader.mapping(raw, path, {"x", "y", "zoom"})
    return Crop(
        _number(reader, data.get("x", 0.5), f"{path}.x", 0.0, 1.0, "crop_out_of_bounds"),
        _number(reader, data.get("y", 0.5), f"{path}.y", 0.0, 1.0, "crop_out_of_bounds"),
        _number(reader, data.get("zoom", 1.0), f"{path}.zoom", 1.0, MAX_ZOOM, "crop_invalid"),
    )


def _type(reader: _Reader, raw: object, path: str) -> CoverType:
    data = reader.mapping(raw, path, {"style", "position", "align", "tone"})
    return CoverType(
        _choice(reader, data.get("style", "editorial"), f"{path}.style", CoverStyle),
        _choice(reader, data.get("position", "top"), f"{path}.position", TitlePosition),
        _choice(reader, data.get("align", "center"), f"{path}.align", TextAlign),
        _choice(reader, data.get("tone", "light"), f"{path}.tone", TextTone),
    )
