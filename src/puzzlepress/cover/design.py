"""Version 3 cover design: region geometry, element placement and flattening.

Pure geometry: authored element boxes (region coordinates) become page boxes,
photographs get their crop windows, shapes and lines their painted outlines,
and translucent shapes are flattened, because a KDP cover may not use PDF
transparency. A translucent shape is either blended with the one solid region
color beneath it or baked into the pixels of the one photograph beneath it;
anything else is reported (`opacity_not_flattenable`) instead of approximated.
Text boxes are set by the layout engine; book text is never placed here.
"""

import math
from dataclasses import dataclass, replace

from ..cover_config import CoverConfig, hex_rgb
from ..cover_design import (
    CoverRegions,
    Element,
    ElementBox,
    LineElement,
    PhotoElement,
    Region,
    ShapeElement,
)
from ..interior.issues import LayoutIssue
from ..interior.model import Box
from ..interior.spec import KDP_COVER
from .assets import PhotoInfo
from .crop import crop_window, image_placement
from .geometry import CoverGeometry
from .model import RGB, CoverPhoto, CoverShape, Fill, ImageResolution

TOLERANCE = 0.01
# A design element is "under the barcode" when this share of it lies in KDP's box.
BARCODE_SHARE = 0.5


def element_role(element: Element) -> str:
    return f"{element.region.value}_element:{element.id}"


def region_origin(g: CoverGeometry, region: Region) -> Box:
    """The trim box an element's coordinates are measured from."""
    return {Region.WRAP: g.trim, Region.BACK: g.back, Region.SPINE: g.spine, Region.FRONT: g.front}[
        region
    ]


def region_area(g: CoverGeometry, region: Region) -> Box:
    """What a region prints, bleed included: the folds divide the media box."""
    m = g.media
    if region is Region.BACK:
        return Box(m.x, m.y, g.back.right - m.x, m.height)
    if region is Region.SPINE:
        return Box(g.spine.x, m.y, g.spine.width, m.height)
    if region is Region.FRONT:
        return Box(g.front.x, m.y, m.right - g.front.x, m.height)
    return m


def page_box(g: CoverGeometry, region: Region, box: ElementBox | None) -> Box:
    if box is None:
        return region_area(g, region)
    origin = region_origin(g, region)
    return Box(origin.x + box.x, origin.y + box.y, box.width, box.height)


def _rgb(value: str | None) -> RGB | None:
    return None if value is None else hex_rgb(value)


def region_fills(g: CoverGeometry, regions: CoverRegions) -> tuple[Fill, tuple[Fill, ...]]:
    """The background and, when regions differ, one fill per region."""
    background = Fill("background", g.media, hex_rgb(regions.back.color))
    if regions.uniform():
        return background, ()
    fills = []
    for region in (Region.BACK, Region.SPINE, Region.FRONT):
        style = regions.style(region)
        gradient = (
            None
            if style.gradient is None
            else (hex_rgb(style.gradient.to), style.gradient.direction.value)
        )
        fills.append(
            Fill(f"region_{region.value}", region_area(g, region), hex_rgb(style.color), gradient)
        )
    return background, tuple(fills)


def _rotated_bounds(box: Box, rotation: float, ellipse: bool) -> Box:
    if not rotation:
        return box
    angle = math.radians(rotation)
    cos, sin = abs(math.cos(angle)), abs(math.sin(angle))
    if ellipse:
        half_w = math.hypot(box.width / 2 * cos, box.height / 2 * sin)
        half_h = math.hypot(box.width / 2 * sin, box.height / 2 * cos)
    else:
        half_w = (box.width * cos + box.height * sin) / 2
        half_h = (box.width * sin + box.height * cos) / 2
    cx, cy = box.x + box.width / 2, box.y + box.height / 2
    return Box(cx - half_w, cy - half_h, 2 * half_w, 2 * half_h)


def shape(g: CoverGeometry, element: ShapeElement | LineElement) -> CoverShape:
    role = element_role(element)
    if isinstance(element, LineElement):
        origin = region_origin(g, element.region)
        x1, y1 = origin.x + element.start.x, origin.y + element.start.y
        x2, y2 = origin.x + element.end.x, origin.y + element.end.y
        length = math.hypot(x2 - x1, y2 - y1)
        cx, cy = (x1 + x2) / 2, (y1 + y2) / 2
        box = Box(cx - length / 2, cy - element.width / 2, length, element.width)
        rotation = math.degrees(math.atan2(y2 - y1, x2 - x1))
        return CoverShape(
            role,
            "line",
            box,
            rotation,
            hex_rgb(element.color),
            None,
            element.width,
            _rotated_bounds(box, rotation, False),
        )
    box = page_box(g, element.region, element.box)
    ellipse = element.kind.value == "ellipse"
    return CoverShape(
        role,
        element.kind.value,
        box,
        element.rotation,
        _rgb(element.fill),
        _rgb(element.stroke),
        element.stroke_width,
        _rotated_bounds(box, element.rotation, ellipse),
        element.opacity,
    )


@dataclass(frozen=True)
class PlacedPhoto:
    photo: CoverPhoto
    resolution: ImageResolution


def photo(g: CoverGeometry, element: PhotoElement, info: PhotoInfo) -> PlacedPhoto:
    region = page_box(g, element.region, element.box)
    window = crop_window(info.width, info.height, region, element.crop)
    placed = CoverPhoto(
        info.sha256,
        region,
        image_placement(window, region),
        window,
        window.pixel_bounds(),
        (),
        element_role(element),
    )
    resolution = ImageResolution(
        (info.width, info.height),
        (window.width, window.height),
        (region.width / 72, region.height / 72),
        window.effective_dpi,
        window.max_dpi,
        KDP_COVER.min_image_dpi,
    )
    return PlacedPhoto(placed, resolution)


def _blend(color: RGB, under: RGB, opacity: float) -> RGB:
    return (
        opacity * color[0] + (1 - opacity) * under[0],
        opacity * color[1] + (1 - opacity) * under[1],
        opacity * color[2] + (1 - opacity) * under[2],
    )


def _bounds(item: object) -> Box:
    if isinstance(item, CoverPhoto):
        return item.region
    if isinstance(item, CoverShape):
        return item.bounds
    box = getattr(item, "box", None)
    assert isinstance(box, Box)
    return box


def flatten(stack: list[object], g: CoverGeometry, regions: CoverRegions) -> list[object]:
    """Resolve translucent shapes; a shape that cannot be flattened keeps its opacity.

    Python decides once, here: blended with the single solid region color under
    it, or baked into the single photograph under it (whose printed area must
    contain it). Validation reports any shape still below full opacity.
    """
    result: list[object] = []
    for item in stack:
        if not isinstance(item, CoverShape) or item.opacity >= 1 or item.fill is None:
            result.append(item)
            continue
        below = [other for other in result if _bounds(other).overlaps(item.bounds, TOLERANCE)]
        if not below:
            colors = {
                regions.style(region)
                for region in (Region.BACK, Region.SPINE, Region.FRONT)
                if region_area(g, region).overlaps(item.bounds, TOLERANCE)
            }
            if len(colors) == 1:
                (style,) = colors
                if style.gradient is None and g.media.contains(item.bounds, TOLERANCE):
                    blended = _blend(item.fill, hex_rgb(style.color), item.opacity)
                    result.append(replace(item, fill=blended, opacity=1.0))
                    continue
        elif (
            len(below) == 1
            and isinstance(below[0], CoverPhoto)
            and below[0].region.contains(item.bounds, TOLERANCE)
        ):
            target = below[0]
            index = result.index(target)
            result[index] = replace(target, baked=(*target.baked, item))
            continue
        result.append(item)
    return result


def design_issues(stack: tuple[object, ...], g: CoverGeometry) -> list[LayoutIssue]:
    """Blocking element problems: outside the media, off the spine, not flattenable."""
    issues: list[LayoutIssue] = []
    for item in stack:
        role = getattr(item, "role", "element")
        if role == "photo":  # Versions 1 and 2: checked by the photo placement rules.
            continue
        bounds = _bounds(item)
        if not g.media.contains(bounds, TOLERANCE):
            issues.append(
                LayoutIssue(
                    "element_outside_media",
                    "A design element extends past the bleed edge, where nothing prints.",
                    region=f"cover.{role}",
                )
            )
        if role.startswith("spine_element:") and (
            bounds.x < g.spine.x - TOLERANCE or bounds.right > g.spine.right + TOLERANCE
        ):
            issues.append(
                LayoutIssue(
                    "spine_element_outside",
                    "A spine element must stay between the two folds.",
                    region=f"cover.{role}",
                )
            )
        if isinstance(item, CoverShape) and item.opacity < 1:
            issues.append(
                LayoutIssue(
                    "opacity_not_flattenable",
                    "A translucent shape must lie over a single solid region color, or entirely "
                    "inside one photograph with nothing between them: KDP covers cannot use "
                    "PDF transparency.",
                    region=f"cover.{role}",
                )
            )
    return issues


def design_warnings(
    config: CoverConfig, stack: tuple[object, ...], g: CoverGeometry
) -> list[LayoutIssue]:
    """Non-blocking manufacturing notes: fold variance and elements under the barcode."""
    regions = config.regions
    assert regions is not None
    warnings: list[LayoutIssue] = []
    clear = KDP_COVER.spine_text_clearance
    for side, neighbor in (("back", regions.back), ("front", regions.front)):
        if neighbor != regions.spine:
            warnings.append(
                LayoutIssue(
                    "spine_color_at_fold",
                    f"The spine and {side} backgrounds differ at the fold. Binding can shift a "
                    f"fold by up to {clear / 72:g} in, so a little of either color may show on "
                    "the other side.",
                    region=f"cover.regions.spine.{side}",
                )
            )
    folds = (g.spine.x, g.spine.right)
    for item in stack:
        role = getattr(item, "role", "")
        if not isinstance(item, CoverShape):
            continue
        bounds = item.bounds
        if role.startswith("spine_element:") and any(
            abs(edge - fold) < clear - TOLERANCE
            for edge in (bounds.x, bounds.right)
            for fold in folds
        ):
            warnings.append(
                LayoutIssue(
                    "spine_element_at_fold",
                    f"This spine element ends within {clear / 72:g} in of a fold, where binding "
                    "variance can move it onto a cover or leave a sliver of background.",
                    region=f"cover.{role}",
                )
            )
    for item in stack:
        if not isinstance(item, CoverShape | CoverPhoto) or getattr(item, "role", "") == "photo":
            continue
        bounds = _bounds(item)
        if bounds.overlaps(g.barcode, TOLERANCE):
            inside = _intersection(bounds, g.barcode)
            area = bounds.width * bounds.height
            if area > 0 and inside / area >= BARCODE_SHARE:
                warnings.append(
                    LayoutIssue(
                        "element_under_barcode",
                        "Most of this element lies where KDP prints its white barcode box, "
                        "which will cover it.",
                        region=f"cover.{item.role}",
                    )
                )
    return warnings


def _intersection(a: Box, b: Box) -> float:
    width = min(a.right, b.right) - max(a.x, b.x)
    height = min(a.top, b.top) - max(a.y, b.y)
    return max(0.0, width) * max(0.0, height)
