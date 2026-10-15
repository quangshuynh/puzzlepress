"""Cover version 3: independent back, spine and front regions and design elements.

A version 3 cover replaces version 1/2's single layout, photograph and fill with
three regions (each with its own background) and an ordered stack of elements:
photographs, rectangles, ellipses, lines and text boxes. Book-detail text
(title, subtitle, author, back text, imprint, spine text) keeps version 2's
preset layout and overrides and is always drawn above the elements.

Element positions are authored PDF points relative to the bottom-left corner of
their region's trim box (x right, y up), so a front element stays put when the
spine width changes. Regions themselves are never authored: they come from the
cover geometry of the built interior. `locked` and `name` are editing aids and
never affect output.
"""

from dataclasses import dataclass, field
from enum import StrEnum

from .cover_config import CoverImage, Crop, LayerAlign, LetterCase

MAX_ELEMENTS = 24
MAX_PHOTO_ELEMENTS = 4
MAX_ELEMENT_TEXT = 600
MAX_ELEMENT_NAME = 60
MAX_COORDINATE = 1500.0  # Points; wider than any supported wrap.
MIN_STROKE = 0.75  # KDP's minimum line weight for print (interior rule, applied here too).
MAX_STROKE = 72.0
MIN_OPACITY = 0.05


class Region(StrEnum):
    """Where an element lives. `wrap` spans back, spine and front (photographs only)."""

    BACK = "back"
    SPINE = "spine"
    FRONT = "front"
    WRAP = "wrap"


PANEL_REGIONS = (Region.BACK, Region.SPINE, Region.FRONT)


class GradientDirection(StrEnum):
    VERTICAL = "vertical"  # From `color` at the top to `to` at the bottom.
    HORIZONTAL = "horizontal"  # From `color` at the left to `to` at the right.


class ElementType(StrEnum):
    PHOTO = "photo"
    RECT = "rect"
    ELLIPSE = "ellipse"
    LINE = "line"
    TEXT = "text"


@dataclass(frozen=True)
class Gradient:
    to: str  # #rrggbb
    direction: GradientDirection = GradientDirection.VERTICAL

    def to_dict(self) -> dict[str, object]:
        return {"to": self.to, "direction": self.direction.value}


@dataclass(frozen=True)
class RegionStyle:
    color: str  # #rrggbb, the region's solid background.
    gradient: Gradient | None = None

    def to_dict(self) -> dict[str, object]:
        data: dict[str, object] = {"color": self.color}
        if self.gradient is not None:
            data["gradient"] = self.gradient.to_dict()
        return data


@dataclass(frozen=True)
class CoverRegions:
    back: RegionStyle
    spine: RegionStyle
    front: RegionStyle

    def style(self, region: Region) -> RegionStyle:
        return {Region.BACK: self.back, Region.SPINE: self.spine, Region.FRONT: self.front}[region]

    def uniform(self) -> bool:
        """One solid color everywhere: drawn as a single background fill."""
        styles = (self.back, self.spine, self.front)
        return all(s.gradient is None and s.color == self.back.color for s in styles)

    def to_dict(self) -> dict[str, object]:
        return {
            "back": self.back.to_dict(),
            "spine": self.spine.to_dict(),
            "front": self.front.to_dict(),
        }


@dataclass(frozen=True)
class ElementBox:
    """Authored rectangle in region coordinates (bottom-left corner, points)."""

    x: float
    y: float
    width: float
    height: float

    def to_dict(self) -> dict[str, object]:
        return {"x": self.x, "y": self.y, "width": self.width, "height": self.height}


@dataclass(frozen=True)
class Point:
    x: float
    y: float

    def to_dict(self) -> dict[str, object]:
        return {"x": self.x, "y": self.y}


@dataclass(frozen=True)
class ElementBase:
    id: str
    region: Region
    visible: bool = True
    locked: bool = False  # Editing aid only; excluded from the cover identity.
    name: str | None = None  # Accessible name; excluded from the cover identity.

    def _common(self, kind: ElementType) -> dict[str, object]:
        data: dict[str, object] = {"id": self.id, "type": kind.value, "region": self.region.value}
        if not self.visible:
            data["visible"] = False
        if self.locked:
            data["locked"] = True
        if self.name is not None:
            data["name"] = self.name
        return data


@dataclass(frozen=True)
class PhotoElement(ElementBase):
    """A photograph cropped into a box, or into the whole region (bleed included)."""

    image: CoverImage = CoverImage("", "")
    crop: Crop = field(default_factory=Crop)
    box: ElementBox | None = None  # None: the region's full printed area.

    def to_dict(self) -> dict[str, object]:
        data = self._common(ElementType.PHOTO)
        data["image"] = self.image.to_dict()
        data["crop"] = self.crop.to_dict()
        if self.box is not None:
            data["box"] = self.box.to_dict()
        return data


@dataclass(frozen=True)
class ShapeElement(ElementBase):
    """A rectangle or ellipse. Strokes are drawn inside the box as filled outlines."""

    kind: ElementType = ElementType.RECT
    box: ElementBox | None = None  # None: the region's full printed area.
    fill: str | None = "#ffffff"
    stroke: str | None = None
    stroke_width: float = 1.0
    opacity: float = 1.0  # Below 1 is flattened by Python (no PDF transparency).
    rotation: float = 0.0  # Degrees counterclockwise about the box centre.

    def to_dict(self) -> dict[str, object]:
        data = self._common(self.kind)
        if self.box is not None:
            data["box"] = self.box.to_dict()
        data["fill"] = self.fill
        data["stroke"] = self.stroke
        if self.stroke is not None:
            data["stroke_width"] = self.stroke_width
        if self.opacity != 1.0:
            data["opacity"] = self.opacity
        if self.rotation:
            data["rotation"] = self.rotation
        return data


@dataclass(frozen=True)
class LineElement(ElementBase):
    start: Point = Point(0.0, 0.0)
    end: Point = Point(72.0, 0.0)
    color: str = "#ffffff"
    width: float = 1.0

    def to_dict(self) -> dict[str, object]:
        data = self._common(ElementType.LINE)
        data |= {
            "from": self.start.to_dict(),
            "to": self.end.to_dict(),
            "color": self.color,
            "width": self.width,
        }
        return data


@dataclass(frozen=True)
class TextBoxElement(ElementBase):
    """The author's own text, wrapped to the box width; overflow is never truncated."""

    box: ElementBox = ElementBox(0.0, 0.0, 144.0, 72.0)
    text: str = ""
    font: str | None = None
    size: float = 12.0
    color: str = "#ffffff"
    align: LayerAlign = LayerAlign.LEFT
    line_spacing: float = 1.3
    letter_spacing: float = 0.0
    case: LetterCase = LetterCase.AS_WRITTEN

    def to_dict(self) -> dict[str, object]:
        data = self._common(ElementType.TEXT)
        data |= {"box": self.box.to_dict(), "text": self.text, "size": self.size}
        if self.font is not None:
            data["font"] = self.font
        data |= {
            "color": self.color,
            "align": self.align.value,
            "line_spacing": self.line_spacing,
        }
        if self.letter_spacing:
            data["letter_spacing"] = self.letter_spacing
        if self.case is not LetterCase.AS_WRITTEN:
            data["case"] = self.case.value
        return data


Element = PhotoElement | ShapeElement | LineElement | TextBoxElement

# Fields that are editing aids, removed from the semantic (identity) form.
EDITING_FIELDS = ("locked", "name")
