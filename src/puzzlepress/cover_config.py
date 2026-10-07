"""Authored paperback cover configuration: semantic choices, never coordinates.

The cover is presentation of the printed edition, so it is excluded from the
project build identity (an edited crop never stales the interior). Its own
cover identity covers it instead. Cover text comes from `book` metadata; only
the optional back-cover text is authored here.
"""

from dataclasses import dataclass, field
from enum import StrEnum

COVER_VERSION = 1
# Project-relative directory for imported photographs, beside book.yaml.
ASSET_DIRECTORY = "cover-assets"
MAX_BACK_TEXT = 1200
MAX_ZOOM = 4.0
# Crop values are normalized to this many decimal places.
CROP_DECIMALS = 4


class CoverLayoutKind(StrEnum):
    FULL_WRAP = "full_wrap"  # One photograph across back, spine and front, bleed to bleed.
    FRONT_PHOTO = "front_photo"  # Photograph on the front; spine and back in the fill color.


class CoverStyle(StrEnum):
    EDITORIAL = "editorial"  # Newsreader serif.
    BOLD = "bold"  # Uppercase Vera Sans Bold.
    MINIMAL = "minimal"  # Restrained Vera Sans.


class TitlePosition(StrEnum):
    TOP = "top"
    MIDDLE = "middle"
    BOTTOM = "bottom"


class TextAlign(StrEnum):
    CENTER = "center"
    LEFT = "left"


class TextTone(StrEnum):
    LIGHT = "light"
    DARK = "dark"


class Legibility(StrEnum):
    NONE = "none"
    SHADE = "shade"  # Photo pixels behind text are darkened (or lightened) toward it.
    PANEL = "panel"  # An opaque band of the fill color behind text.


class SpineText(StrEnum):
    AUTO = "auto"  # Title and author when KDP's page count and the spine width allow.
    NONE = "none"


@dataclass(frozen=True)
class CoverImage:
    """A photograph in the project's cover-assets directory, pinned by content."""

    path: str  # Project-relative, forward slashes: cover-assets/<name>.jpg
    sha256: str

    def to_dict(self) -> dict[str, object]:
        return {"path": self.path, "sha256": self.sha256}


@dataclass(frozen=True)
class Crop:
    """Focal point (0..1 of the upright photo; y downward) and zoom beyond cover-fit."""

    x: float = 0.5
    y: float = 0.5
    zoom: float = 1.0

    def to_dict(self) -> dict[str, object]:
        return {"x": self.x, "y": self.y, "zoom": self.zoom}


@dataclass(frozen=True)
class CoverType:
    style: CoverStyle = CoverStyle.EDITORIAL
    position: TitlePosition = TitlePosition.TOP
    align: TextAlign = TextAlign.CENTER
    tone: TextTone = TextTone.LIGHT

    def to_dict(self) -> dict[str, object]:
        return {
            "style": self.style.value,
            "position": self.position.value,
            "align": self.align.value,
            "tone": self.tone.value,
        }


@dataclass(frozen=True)
class CoverConfig:
    image: CoverImage
    layout: CoverLayoutKind = CoverLayoutKind.FULL_WRAP
    crop: Crop = field(default_factory=Crop)
    type: CoverType = field(default_factory=CoverType)
    legibility: Legibility = Legibility.SHADE
    background: str = "#26302b"  # sRGB fill wherever the photograph does not print.
    spine_text: SpineText = SpineText.AUTO
    back_text: str | None = None
    version: int = COVER_VERSION

    def to_dict(self) -> dict[str, object]:
        data: dict[str, object] = {
            "version": self.version,
            "layout": self.layout.value,
            "image": self.image.to_dict(),
            "crop": self.crop.to_dict(),
            "type": self.type.to_dict(),
            "legibility": self.legibility.value,
            "background": self.background,
            "spine_text": self.spine_text.value,
        }
        if self.back_text is not None:
            data["back_text"] = self.back_text
        return data

    def rgb(self) -> tuple[float, float, float]:
        return hex_rgb(self.background)


def hex_rgb(value: str) -> tuple[float, float, float]:
    return (int(value[1:3], 16) / 255, int(value[3:5], 16) / 255, int(value[5:7], 16) / 255)
