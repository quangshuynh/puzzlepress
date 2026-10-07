"""Cover-fit cropping: the single source of crop math for layout, preview and PDF.

The photograph scales uniformly (never stretched) until it covers the region,
then `zoom` enlarges it further. The window of source pixels that maps onto the
region is centered on the authored focal point, clamped so it stays inside the
photo. Source coordinates are pixels of the upright photo with y downward.
"""

import math
from dataclasses import dataclass

from ..cover_config import Crop
from ..interior.model import Box

POINTS_PER_INCH = 72
_EPSILON = 1e-6


@dataclass(frozen=True)
class CropWindow:
    photo_width: int
    photo_height: int
    left: float  # Source pixels.
    top: float
    width: float
    height: float
    scale: float  # Points per source pixel, equal on both axes.
    fit_scale: float  # The cover-fit scale at zoom 1.

    @property
    def effective_dpi(self) -> float:
        """Source pixels actually printed per physical inch."""
        return POINTS_PER_INCH / self.scale

    @property
    def max_dpi(self) -> float:
        """The best resolution any crop of this photo reaches in this region (zoom 1)."""
        return POINTS_PER_INCH / self.fit_scale

    @property
    def center(self) -> tuple[float, float]:
        """The applied focal point, normalized, after clamping."""
        return (
            (self.left + self.width / 2) / self.photo_width,
            (self.top + self.height / 2) / self.photo_height,
        )

    def normalized(self) -> tuple[float, float, float, float]:
        """The visible window as (left, top, right, bottom) fractions of the photo."""
        return (
            self.left / self.photo_width,
            self.top / self.photo_height,
            (self.left + self.width) / self.photo_width,
            (self.top + self.height) / self.photo_height,
        )

    def pixel_bounds(self) -> tuple[int, int, int, int]:
        """Whole source pixels covering the window: (x0, y0, x1, y1), end exclusive."""
        return (
            max(0, math.floor(self.left + _EPSILON)),
            max(0, math.floor(self.top + _EPSILON)),
            min(self.photo_width, math.ceil(self.left + self.width - _EPSILON)),
            min(self.photo_height, math.ceil(self.top + self.height - _EPSILON)),
        )


def crop_window(photo_width: int, photo_height: int, region: Box, crop: Crop) -> CropWindow:
    if photo_width < 1 or photo_height < 1 or region.width <= 0 or region.height <= 0:
        raise ValueError("Photo and region must have positive extent")
    fit = max(region.width / photo_width, region.height / photo_height)
    scale = fit * crop.zoom
    width = min(region.width / scale, photo_width)
    height = min(region.height / scale, photo_height)
    cx = min(max(crop.x * photo_width, width / 2), photo_width - width / 2)
    cy = min(max(crop.y * photo_height, height / 2), photo_height - height / 2)
    return CropWindow(
        photo_width, photo_height, cx - width / 2, cy - height / 2, width, height, scale, fit
    )


def image_placement(window: CropWindow, region: Box) -> Box:
    """Where the whole-pixel crop is drawn so the window lands exactly on `region`.

    The drawn image extends at most one source pixel beyond the region on each
    side and is clipped to it; scaling is uniform.
    """
    x0, y0, x1, y1 = window.pixel_bounds()
    s = window.scale
    width, height = (x1 - x0) * s, (y1 - y0) * s
    left = region.x - (window.left - x0) * s
    top = region.top + (window.top - y0) * s
    return Box(left, top - height, width, height)
