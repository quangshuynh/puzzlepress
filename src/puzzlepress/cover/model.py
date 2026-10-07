"""Immutable cover layout consumed by the cover renderer and its preview.

Coordinates are PDF points, origin at the bottom-left of the media box (outer
bleed corner), y upward. The layout engine decides every position and every
pixel used from the photograph; the renderer draws exactly these elements.
"""

from dataclasses import dataclass

from ..cover_config import CoverConfig
from ..interior.model import Anchor, Box
from .crop import CropWindow
from .fonts import CoverFace
from .geometry import CoverGeometry

RGB = tuple[float, float, float]


@dataclass(frozen=True)
class Fill:
    """An opaque rectangle (background, spine or legibility panel)."""

    role: str
    box: Box
    color: RGB


@dataclass(frozen=True)
class CoverText:
    """One measured line. Spine lines turn 90 degrees clockwise (read top to bottom).

    `origin` is the anchor point on the baseline; `bounds` covers the font's full
    ascent and descent in page coordinates after rotation.
    """

    role: str
    text: str
    face: CoverFace
    size: float
    origin: tuple[float, float]
    anchor: Anchor
    rotated: bool
    bounds: Box
    color: RGB


@dataclass(frozen=True)
class ShadeBand:
    """Pixels behind text pulled toward `toward`, baked into the photograph.

    Full `strength` between `core` (y range in points), fading linearly to zero
    over `fade` points beyond it, within the band's x range. No PDF transparency.
    """

    x0: float
    x1: float
    core: tuple[float, float]
    fade: float
    strength: float
    toward: tuple[int, int, int]

    def weight(self, y: float) -> float:
        low, high = self.core
        distance = low - y if y < low else y - high if y > high else 0.0
        if distance <= 0:
            return self.strength
        if self.fade <= 0 or distance >= self.fade:
            return 0.0
        return self.strength * (1 - distance / self.fade)


@dataclass(frozen=True)
class CoverPhoto:
    """The photograph: the source window shown in `region`, drawn at `placement`."""

    sha256: str
    region: Box  # Clip: exactly the area the photo prints in.
    placement: Box  # Whole-pixel crop drawn here, overhanging the region by < 1 px.
    window: CropWindow
    pixels: tuple[int, int, int, int]  # (x0, y0, x1, y1) of the upright photo.
    shade: tuple[ShadeBand, ...] = ()


@dataclass(frozen=True)
class ImageResolution:
    source_pixels: tuple[int, int]  # Upright photo.
    used_pixels: tuple[float, float]  # Source pixels inside the visible window.
    printed_inches: tuple[float, float]  # Physical size of the photo region.
    effective_dpi: float
    max_dpi: float  # With no zoom: the most this photo can deliver here.
    minimum_dpi: float  # KDP minimum.

    @property
    def sufficient(self) -> bool:
        return self.effective_dpi + 1e-9 >= self.minimum_dpi

    @property
    def status(self) -> str:
        """`ok`, `image_low_effective_dpi` (zoom out to fix) or `image_too_small`."""
        if self.sufficient:
            return "ok"
        if self.max_dpi + 1e-9 >= self.minimum_dpi:
            return "image_low_effective_dpi"
        return "image_too_small"

    def to_dict(self) -> dict[str, object]:
        return {
            "source_pixels": list(self.source_pixels),
            "used_pixels": [round(v, 2) for v in self.used_pixels],
            "printed_inches": [round(v, 4) for v in self.printed_inches],
            "effective_dpi": round(self.effective_dpi, 2),
            "max_dpi": round(self.max_dpi, 2),
            "minimum_dpi": self.minimum_dpi,
            "status": self.status,
        }


@dataclass(frozen=True)
class SpineStatus:
    allowed_by_page_count: bool
    rendered: bool
    reason: str | None  # Why spine text is absent: authored, page_count, spine_too_narrow.
    size: float | None  # Point size when rendered.

    def to_dict(self) -> dict[str, object]:
        return {
            "allowed_by_page_count": self.allowed_by_page_count,
            "rendered": self.rendered,
            "reason": self.reason,
            "size": self.size,
        }


@dataclass(frozen=True)
class CoverLayout:
    book_id: str
    config: CoverConfig
    geometry: CoverGeometry
    background: Fill
    photo: CoverPhoto
    panels: tuple[Fill, ...]  # Drawn over the photo, under the text.
    texts: tuple[CoverText, ...]
    spine: SpineStatus
    resolution: ImageResolution
