"""Cover version 3 regions and elements. Collects independent issues; never repairs.

Schema checks only: shapes of values, bounds, references to imported fonts and
the per-type rules (no photographs or text boxes on the spine, no stroke on a
translucent shape). Whether an element fits its region, stays in a safe area or
can be flattened is decided by the layout engine and reported as layout issues.
"""

import math
from typing import NamedTuple

from .content_validation import _Reader
from .cover_config import (
    LETTER_SPACING,
    LINE_SPACING,
    MAX_TEXT_SIZE,
    MIN_TEXT_SIZE,
    LayerAlign,
    LetterCase,
)
from .cover_design import (
    MAX_COORDINATE,
    MAX_ELEMENT_NAME,
    MAX_ELEMENT_TEXT,
    MAX_ELEMENTS,
    MAX_PHOTO_ELEMENTS,
    MAX_STROKE,
    MIN_OPACITY,
    MIN_STROKE,
    CoverRegions,
    Element,
    ElementBox,
    ElementType,
    Gradient,
    GradientDirection,
    LineElement,
    PhotoElement,
    Point,
    Region,
    RegionStyle,
    ShapeElement,
    TextBoxElement,
)
from .cover_richtext import RichText, read_rich
from .cover_validation import (
    BUNDLED_FACES,
    HEX_COLOR,
    LAYER_ID,
    _bounded,
    _choice,
    _crop,
    _image,
)

REGION_FIELDS = {"color", "gradient"}
COMMON = {"id", "type", "region", "visible", "locked", "name"}
FIELDS = {
    ElementType.PHOTO: COMMON | {"image", "crop", "box"},
    ElementType.RECT: COMMON | {"box", "fill", "stroke", "stroke_width", "opacity", "rotation"},
    ElementType.ELLIPSE: COMMON | {"box", "fill", "stroke", "stroke_width", "opacity", "rotation"},
    ElementType.LINE: COMMON | {"from", "to", "color", "width"},
    ElementType.TEXT: COMMON
    | {
        "box",
        "text",
        "rich",
        "font",
        "size",
        "color",
        "align",
        "line_spacing",
        "letter_spacing",
        "case",
    },
}
REGIONS = {
    ElementType.PHOTO: (Region.WRAP, Region.BACK, Region.FRONT),
    ElementType.RECT: tuple(Region),
    ElementType.ELLIPSE: tuple(Region),
    ElementType.LINE: tuple(Region),
    ElementType.TEXT: (Region.BACK, Region.FRONT),
}


class _Common(NamedTuple):
    id: str
    region: Region
    visible: bool
    locked: bool
    name: str | None


def _color(reader: _Reader, raw: object, path: str, nullable: bool = False) -> str | None:
    if raw is None and nullable:
        return None
    if not isinstance(raw, str) or not HEX_COLOR.fullmatch(raw):
        reader.issue(path, "color", "Use a #RRGGBB sRGB color." + (" Or null." if nullable else ""))
        return None
    return raw.lower()


def read_regions(reader: _Reader, raw: object, path: str) -> CoverRegions | None:
    data = reader.mapping(raw, path, {"back", "spine", "front"})
    styles: dict[str, RegionStyle] = {}
    for name in ("back", "spine", "front"):
        if name not in data:
            reader.issue(f"{path}.{name}", "required", f"State the {name} background color.")
            continue
        item = f"{path}.{name}"
        region = reader.mapping(data[name], item, REGION_FIELDS)
        color = _color(reader, region.get("color"), f"{item}.color")
        gradient: Gradient | None = None
        if "gradient" in region:
            spec = reader.mapping(region["gradient"], f"{item}.gradient", {"to", "direction"})
            to = _color(reader, spec.get("to"), f"{item}.gradient.to")
            direction = _choice(
                reader,
                spec.get("direction", "vertical"),
                f"{item}.gradient.direction",
                GradientDirection,
            )
            gradient = Gradient(to, direction) if to else None
        if color is not None:
            styles[name] = RegionStyle(color, gradient)
    if len(styles) != 3:
        return None
    return CoverRegions(styles["back"], styles["spine"], styles["front"])


def _coordinate(reader: _Reader, raw: object, path: str) -> float:
    return _bounded(reader, raw, path, -MAX_COORDINATE, MAX_COORDINATE) or 0.0


def _box(reader: _Reader, raw: object, path: str, minimum: float = 1.0) -> ElementBox | None:
    data = reader.mapping(raw, path, {"x", "y", "width", "height"})
    for key in ("x", "y", "width", "height"):
        if key not in data:
            reader.issue(f"{path}.{key}", "required", f"State the box {key} in points.")
    if any(key not in data for key in ("x", "y", "width", "height")):
        return None
    width = _bounded(reader, data["width"], f"{path}.width", minimum, 2 * MAX_COORDINATE)
    height = _bounded(reader, data["height"], f"{path}.height", minimum, 2 * MAX_COORDINATE)
    box = ElementBox(
        _coordinate(reader, data["x"], f"{path}.x"),
        _coordinate(reader, data["y"], f"{path}.y"),
        width or minimum,
        height or minimum,
    )
    return box if width is not None and height is not None else None


def _point(reader: _Reader, raw: object, path: str) -> Point:
    data = reader.mapping(raw, path, {"x", "y"})
    return Point(
        _coordinate(reader, data.get("x", 0), f"{path}.x"),
        _coordinate(reader, data.get("y", 0), f"{path}.y"),
    )


def _flag(reader: _Reader, raw: object, path: str, default: bool) -> bool:
    if raw is None:
        return default
    if not isinstance(raw, bool):
        reader.issue(path, "type", "Expected true or false.")
        return default
    return raw


def _name(reader: _Reader, raw: object, path: str) -> str | None:
    if raw is None:
        return None
    if (
        not isinstance(raw, str)
        or not raw.strip()
        or len(raw) > MAX_ELEMENT_NAME
        or any(ord(c) < 32 or ord(c) == 127 for c in raw)
    ):
        reader.issue(path, "text", f"Expected 1..{MAX_ELEMENT_NAME} characters on one line.")
        return None
    return raw.strip()


def _text(reader: _Reader, raw: object, path: str) -> str:
    if (
        not isinstance(raw, str)
        or not raw.strip()
        or len(raw) > MAX_ELEMENT_TEXT
        or any(0xD800 <= ord(c) <= 0xDFFF for c in raw)
        or any((ord(c) < 32 and c != "\n") or ord(c) == 127 for c in raw)
    ):
        reader.issue(
            path,
            "text",
            f"Expected 1..{MAX_ELEMENT_TEXT} characters of plain text; line breaks are allowed.",
        )
        return ""
    return raw.strip("\n").rstrip()


def read_elements(
    reader: _Reader, raw: object, path: str, font_ids: set[str]
) -> tuple[Element, ...]:
    elements: list[Element] = []
    seen: set[str] = set()
    photos = 0
    for index, entry in enumerate(reader.sequence(raw, path, MAX_ELEMENTS, 0)):
        item = f"{path}.{index}"
        if not isinstance(entry, dict):
            reader.mapping(entry, item, set())
            continue
        kind_raw = entry.get("type")
        if not isinstance(kind_raw, str) or kind_raw not in {k.value for k in ElementType}:
            reader.issue(
                f"{item}.type",
                "choice",
                f"Use one of: {', '.join(k.value for k in ElementType)}.",
            )
            continue
        kind = ElementType(kind_raw)
        data = reader.mapping(entry, item, FIELDS[kind])
        element_id = data.get("id")
        if (
            not isinstance(element_id, str)
            or len(element_id) > 40
            or not LAYER_ID.fullmatch(element_id)
        ):
            reader.issue(f"{item}.id", "id", "Use 1..40 lowercase letters, digits and hyphens.")
            element_id = f"element-{index}"
        elif element_id in seen:
            reader.issue(f"{item}.id", "duplicate", f"Element id {element_id!r} is used twice.")
        seen.add(element_id)
        region = _choice(reader, data.get("region"), f"{item}.region", Region)
        if region not in REGIONS[kind]:
            allowed = ", ".join(r.value for r in REGIONS[kind])
            reader.issue(
                f"{item}.region",
                "region_not_allowed",
                f"A {kind.value} element can be placed on: {allowed}.",
            )
        common = _Common(
            element_id,
            region,
            _flag(reader, data.get("visible"), f"{item}.visible", True),
            _flag(reader, data.get("locked"), f"{item}.locked", False),
            _name(reader, data.get("name"), f"{item}.name"),
        )
        if kind is ElementType.PHOTO:
            photos += 1
            image = _image(reader, data.get("image"), f"{item}.image", "image" in data)
            crop = _crop(reader, data.get("crop", {}), f"{item}.crop")
            box = _box(reader, data["box"], f"{item}.box", 9.0) if "box" in data else None
            if image is not None:
                elements.append(PhotoElement(*common, image=image, crop=crop, box=box))
        elif kind in (ElementType.RECT, ElementType.ELLIPSE):
            elements.append(_shape(reader, data, item, kind, common))
        elif kind is ElementType.LINE:
            start = _point(reader, data.get("from", {}), f"{item}.from")
            end = _point(reader, data.get("to", {}), f"{item}.to")
            if math.hypot(end.x - start.x, end.y - start.y) < 1.0:
                reader.issue(f"{item}.to", "line_too_short", "A line must be at least 1 pt long.")
            color = _color(reader, data.get("color", "#ffffff"), f"{item}.color") or "#ffffff"
            width = _bounded(
                reader, data.get("width", 1.0), f"{item}.width", MIN_STROKE, MAX_STROKE
            )
            elements.append(
                LineElement(
                    *common,
                    start=start,
                    end=end,
                    color=color,
                    width=width or MIN_STROKE,
                )
            )
        else:
            elements.append(_text_box(reader, data, item, common, font_ids))
    if photos > MAX_PHOTO_ELEMENTS:
        reader.issue(
            path, "too_many_photos", f"A cover can place at most {MAX_PHOTO_ELEMENTS} photographs."
        )
    return tuple(elements)


def _shape(
    reader: _Reader,
    data: dict[str, object],
    item: str,
    kind: ElementType,
    common: _Common,
) -> ShapeElement:
    box = _box(reader, data["box"], f"{item}.box") if "box" in data else None
    fill = _color(reader, data.get("fill", "#ffffff"), f"{item}.fill", nullable=True)
    stroke = _color(reader, data.get("stroke"), f"{item}.stroke", nullable=True)
    width = _bounded(
        reader, data.get("stroke_width", 1.0), f"{item}.stroke_width", MIN_STROKE, MAX_STROKE
    )
    opacity = _bounded(reader, data.get("opacity", 1.0), f"{item}.opacity", MIN_OPACITY, 1.0)
    rotation = _bounded(reader, data.get("rotation", 0.0), f"{item}.rotation", -180.0, 180.0)
    if fill is None and stroke is None and data.get("fill", "#ffffff") is None:
        reader.issue(f"{item}.fill", "shape_invisible", "Give the shape a fill, a stroke or both.")
    if opacity is not None and opacity < 1 and stroke is not None:
        reader.issue(
            f"{item}.opacity",
            "opacity_with_stroke",
            "A translucent shape cannot have a stroke; remove the stroke or set opacity to 1.",
        )
    if box is None and rotation:
        reader.issue(
            f"{item}.rotation", "rotation_needs_box", "Only a shape with a box can be rotated."
        )
    return ShapeElement(
        *common,
        kind=kind,
        box=box,
        fill=fill,
        stroke=stroke,
        stroke_width=width or MIN_STROKE,
        opacity=opacity if opacity is not None else 1.0,
        rotation=rotation or 0.0,
    )


def _text_box(
    reader: _Reader,
    data: dict[str, object],
    item: str,
    common: _Common,
    font_ids: set[str],
) -> TextBoxElement:
    if "box" not in data:
        reader.issue(f"{item}.box", "required", "A text box needs a box: x, y, width, height.")
    box = _box(reader, data.get("box", {}), f"{item}.box", 6.0) if "box" in data else None
    rich: RichText | None = None
    if "rich" in data and "text" in data:
        reader.issue(
            f"{item}.rich", "text_and_rich", "A text box holds plain text or rich text, not both."
        )
    if "rich" in data:
        rich = read_rich(reader, data["rich"], f"{item}.rich", font_ids, MAX_ELEMENT_TEXT)
        text = rich.plain() if rich is not None else ""
    elif "text" not in data:
        reader.issue(f"{item}.text", "required", "A text box needs its text.")
        text = ""
    else:
        text = _text(reader, data.get("text"), f"{item}.text")
    font = data.get("font")
    if font is not None and (
        not isinstance(font, str) or (font not in BUNDLED_FACES and font not in font_ids)
    ):
        reader.issue(
            f"{item}.font",
            "unknown_font",
            f"Use a bundled face ({', '.join(BUNDLED_FACES)}) or the id of a font in cover.fonts.",
        )
        font = None
    size = _bounded(reader, data.get("size", 12.0), f"{item}.size", MIN_TEXT_SIZE, MAX_TEXT_SIZE)
    color = _color(reader, data.get("color", "#ffffff"), f"{item}.color") or "#ffffff"
    align = _choice(reader, data.get("align", "left"), f"{item}.align", LayerAlign)
    case = _choice(reader, data.get("case", "as_written"), f"{item}.case", LetterCase)
    line = _bounded(reader, data.get("line_spacing", 1.3), f"{item}.line_spacing", *LINE_SPACING)
    letter = _bounded(
        reader, data.get("letter_spacing", 0.0), f"{item}.letter_spacing", *LETTER_SPACING
    )
    return TextBoxElement(
        *common,
        box=box or ElementBox(0.0, 0.0, 144.0, 72.0),
        text=text,
        font=font if isinstance(font, str) else None,
        size=size or 12.0,
        color=color,
        align=align,
        line_spacing=line or 1.3,
        letter_spacing=letter or 0.0,
        case=case,
        rich=rich,
    )
