"""Cover layout engine: semantic configuration plus interior facts to CoverLayout.

Pure apart from font metrics. It decides the photo window, every text position,
spine eligibility and the legibility treatment. It never moves text outside its
safe area, squeezes type below its preset minimum or invents copy: front text is
the book's title, subtitle and author; back text is only what the cover authors.
"""

import math
from dataclasses import dataclass

from ..cover_config import (
    CoverConfig,
    CoverLayoutKind,
    CoverStyle,
    Legibility,
    SpineText,
    TextAlign,
    TextTone,
    TitlePosition,
)
from ..interior.issues import LayoutIssue
from ..interior.model import Anchor, Box
from ..interior.spec import KDP_COVER, inches
from ..models import Project
from .assets import PhotoInfo
from .crop import crop_window, image_placement
from .fonts import CoverFace, metrics, missing_characters, text_width
from .geometry import CoverGeometry
from .issues import CoverError
from .model import (
    RGB,
    CoverLayout,
    CoverPhoto,
    CoverText,
    Fill,
    ImageResolution,
    ShadeBand,
    SpineStatus,
)

LIGHT: RGB = (1.0, 1.0, 1.0)
DARK: RGB = (0.106, 0.118, 0.11)
TITLE_LINES = 3
SUBTITLE_LINES = 3
AUTHOR_LINES = 2
TITLE_STEP = 2.0
BACK_MEASURE = inches(5.5)
FRONT_GAP = inches(0.25)  # Minimum space between the title block and the author.
BACK_GAP = inches(0.25)  # Back text keeps this far above the barcode area and imprint.
PANEL_PAD = inches(0.3)
SHADE_PAD = inches(0.35)
SHADE_FADE = inches(1.5)
EDGE_SNAP = inches(1.5)  # Shade reaches the media edge when text is this close to it.
SHADE_STRENGTH = {TextTone.LIGHT: 0.5, TextTone.DARK: 0.55}
SHADE_TOWARD = {TextTone.LIGHT: (0, 0, 0), TextTone.DARK: (255, 255, 255)}


@dataclass(frozen=True)
class Preset:
    title_face: CoverFace
    title_max: float
    title_min: float
    title_pitch: float  # Line pitch as a multiple of size (never tighter than the face).
    upper: bool  # Title, author and spine text in capitals.
    subtitle_face: CoverFace
    subtitle_size: float
    author_face: CoverFace
    author_size: float
    spine_face: CoverFace
    spine_max: float
    body_face: CoverFace
    body_size: float
    body_pitch: float
    imprint_face: CoverFace
    imprint_size: float


PRESETS = {
    CoverStyle.EDITORIAL: Preset(
        CoverFace.SERIF_DISPLAY, 62, 36, 1.02, False,
        CoverFace.SERIF_ITALIC, 20,
        CoverFace.SERIF, 17,
        CoverFace.SERIF, 14,
        CoverFace.SERIF, 12.5, 1.42,
        CoverFace.SERIF_ITALIC, 10.5,
    ),
    CoverStyle.BOLD: Preset(
        CoverFace.SANS_BOLD, 60, 34, 1.0, True,
        CoverFace.SANS, 17,
        CoverFace.SANS_BOLD, 14,
        CoverFace.SANS_BOLD, 13,
        CoverFace.SANS, 11.5, 1.5,
        CoverFace.SANS, 9.5,
    ),
    CoverStyle.MINIMAL: Preset(
        CoverFace.SANS, 42, 28, 1.1, False,
        CoverFace.SANS, 14,
        CoverFace.SANS, 12.5,
        CoverFace.SANS, 12,
        CoverFace.SANS, 11, 1.55,
        CoverFace.SANS, 9,
    ),
}  # fmt: skip


@dataclass(frozen=True)
class CoverCopy:
    """Every word a cover prints: book metadata plus the authored back text."""

    title: str
    subtitle: str | None
    author: str | None
    imprint: str | None
    back_text: str | None

    @classmethod
    def from_project(cls, project: Project) -> "CoverCopy":
        book, cover = project.book, project.cover
        return cls(
            book.title,
            book.subtitle,
            book.author,
            book.imprint,
            cover.back_text if cover else None,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "title": self.title,
            "subtitle": self.subtitle,
            "author": self.author,
            "imprint": self.imprint,
            "back_text": self.back_text,
        }


def _fail(
    code: str, message: str, region: str, actual: str | None = None, required: str | None = None
) -> CoverError:
    return CoverError(
        "layout", (LayoutIssue(code, message, region=region, actual=actual, required=required),)
    )


def _check_glyphs(text: str, face: CoverFace, region: str) -> None:
    missing = missing_characters(text, face)
    if missing:
        listed = ", ".join(f"U+{ord(c):04X}" for c in missing)
        raise _fail(
            "unsupported_character",
            f"The cover font cannot draw: {listed}.",
            region,
            actual=listed,
            required="Latin-1 text",
        )


def wrap(text: str, face: CoverFace, size: float, measure: float) -> list[str] | None:
    """Greedy wrap keeping authored line breaks; None if a word is wider than the measure."""
    lines: list[str] = []
    for paragraph in text.split("\n"):
        words = [word for word in paragraph.split(" ") if word]
        current = ""
        for word in words:
            if text_width(word, face, size) > measure:
                return None
            candidate = f"{current} {word}" if current else word
            if current and text_width(candidate, face, size) > measure:
                lines.append(current)
                current = word
            else:
                current = candidate
        lines.append(current)
    return lines


@dataclass(frozen=True)
class _Line:
    role: str
    text: str
    face: CoverFace
    size: float
    gap_before: float  # Space between this line box and the previous one.


def _group(
    role: str, lines: list[str], face: CoverFace, size: float, pitch: float, gap: float
) -> list[_Line]:
    m = metrics(face)
    within = max(0.0, (pitch - m.ascent - m.descent) * size)
    return [
        _Line(role, text, face, size, gap if index == 0 else within)
        for index, text in enumerate(lines)
    ]


def _height(lines: list[_Line]) -> float:
    total = 0.0
    for index, line in enumerate(lines):
        m = metrics(line.face)
        total += (m.ascent + m.descent) * line.size + (line.gap_before if index else 0.0)
    return total


def _place(lines: list[_Line], top: float, x: float, anchor: Anchor, color: RGB) -> list[CoverText]:
    placed: list[CoverText] = []
    cursor = top
    for index, line in enumerate(lines):
        m = metrics(line.face)
        if index:
            cursor -= line.gap_before
        baseline = cursor - m.ascent * line.size
        cursor = baseline - m.descent * line.size
        if line.text:
            placed.append(
                _text(line.role, line.text, line.face, line.size, x, baseline, anchor, color)
            )
    return placed


def _text(
    role: str,
    text: str,
    face: CoverFace,
    size: float,
    x: float,
    baseline: float,
    anchor: Anchor,
    color: RGB,
) -> CoverText:
    width = text_width(text, face, size)
    m = metrics(face)
    left = {Anchor.START: x, Anchor.MIDDLE: x - width / 2, Anchor.END: x - width}[anchor]
    bounds = Box(left, baseline - m.descent * size, width, (m.ascent + m.descent) * size)
    return CoverText(role, text, face, size, (x, baseline), anchor, False, bounds, color)


def _spine_text(
    role: str,
    text: str,
    face: CoverFace,
    size: float,
    x: float,
    y: float,
    anchor: Anchor,
    color: RGB,
) -> CoverText:
    """A line turned 90 degrees clockwise; `x` is the baseline, `y` the anchor point."""
    length = text_width(text, face, size)
    m = metrics(face)
    start = y - length if anchor is Anchor.START else y
    bounds = Box(x - m.descent * size, start, (m.ascent + m.descent) * size, length)
    return CoverText(role, text, face, size, (x, y), anchor, True, bounds, color)


def _front(
    copy: CoverCopy, preset: Preset, config: CoverConfig, area: Box, color: RGB
) -> tuple[list[CoverText], Box, Box | None]:
    """Front texts, the title block's bounds and the author block's bounds."""
    title = copy.title.upper() if preset.upper else copy.title
    _check_glyphs(title, preset.title_face, "cover.title")
    title_lines: list[str] | None = None
    size = preset.title_max
    while size >= preset.title_min - 1e-9:
        title_lines = wrap(title, preset.title_face, size, area.width)
        if title_lines is not None and len(title_lines) <= TITLE_LINES:
            break
        title_lines = None
        size -= TITLE_STEP
    if title_lines is None:
        raise _fail(
            "text_overflow",
            f"The title does not fit {TITLE_LINES} lines of the front cover at "
            f"{preset.title_min:g} pt or larger.",
            "cover.title",
            required=f"{TITLE_LINES} lines",
        )
    block = _group("title", title_lines, preset.title_face, size, preset.title_pitch, 0.0)
    if copy.subtitle:
        _check_glyphs(copy.subtitle, preset.subtitle_face, "cover.subtitle")
        lines = wrap(copy.subtitle, preset.subtitle_face, preset.subtitle_size, area.width)
        if lines is None or len(lines) > SUBTITLE_LINES:
            raise _fail(
                "text_overflow",
                f"The subtitle does not fit {SUBTITLE_LINES} lines of the front cover.",
                "cover.subtitle",
            )
        block += _group(
            "subtitle", lines, preset.subtitle_face, preset.subtitle_size, 1.3, 0.45 * size
        )
    author: list[_Line] = []
    if copy.author:
        name = copy.author.upper() if preset.upper else copy.author
        _check_glyphs(name, preset.author_face, "cover.author")
        lines = wrap(name, preset.author_face, preset.author_size, area.width)
        if lines is None or len(lines) > AUTHOR_LINES:
            raise _fail(
                "text_overflow", "The author line does not fit the front cover.", "cover.author"
            )
        author = _group("author", lines, preset.author_face, preset.author_size, 1.3, 0.0)
    center = config.type.align is TextAlign.CENTER
    x, anchor = (area.x + area.width / 2, Anchor.MIDDLE) if center else (area.x, Anchor.START)
    height, author_height = _height(block), _height(author)
    position = config.type.position
    if position is TitlePosition.BOTTOM:
        top, author_top = area.y + height, area.top
    elif position is TitlePosition.MIDDLE:
        top, author_top = area.y + (area.height + height) / 2, area.y + author_height
    else:
        top, author_top = area.top, area.y + author_height
    title_box = Box(area.x, top - height, area.width, height)
    author_box = Box(area.x, author_top - author_height, area.width, author_height)
    if author and title_box.overlaps(_grow(author_box, 0, FRONT_GAP), 0):
        raise _fail(
            "text_overflow",
            "The title block and author do not both fit the front cover.",
            "cover.front",
        )
    texts = _place(block, top, x, anchor, color) + _place(author, author_top, x, anchor, color)
    return texts, title_box, author_box if author else None


def _grow(box: Box, dx: float, dy: float) -> Box:
    return Box(box.x - dx, box.y - dy, box.width + 2 * dx, box.height + 2 * dy)


def _spine(
    copy: CoverCopy, preset: Preset, config: CoverConfig, geometry: CoverGeometry, color: RGB
) -> tuple[list[CoverText], SpineStatus]:
    allowed = geometry.spine_text_allowed
    if config.spine_text is SpineText.NONE:
        return [], SpineStatus(allowed, False, "authored", None)
    if not allowed:
        return [], SpineStatus(False, False, "page_count", None)
    safe = geometry.spine_safe
    m = metrics(preset.spine_face)
    across = m.ascent + m.descent
    size = min(preset.spine_max, math.floor(safe.width / across * 2) / 2)
    if size < KDP_COVER.min_font_size:
        return [], SpineStatus(True, False, "spine_too_narrow", None)
    title = copy.title.upper() if preset.upper else copy.title
    author = (copy.author.upper() if preset.upper else copy.author) if copy.author else None
    _check_glyphs(title + (author or ""), preset.spine_face, "cover.spine")
    while True:
        gap = max(2 * size, inches(0.5))
        length = text_width(title, preset.spine_face, size)
        if author:
            length += gap + text_width(author, preset.spine_face, size)
        if length <= safe.height:
            break
        if size - 0.5 < KDP_COVER.min_font_size:
            raise _fail(
                "spine_text_overflow",
                "Spine text does not fit the spine at 7 pt; shorten the title or "
                "set spine_text to none.",
                "cover.spine_text",
                actual=f"{length / 72:.3f} in",
                required=f"at most {safe.height / 72:.3f} in",
            )
        size -= 0.5
    baseline = safe.x + safe.width / 2 - (m.ascent - m.descent) / 2 * size
    texts = [
        _spine_text(
            "spine_title", title, preset.spine_face, size, baseline, safe.top, Anchor.START, color
        )
    ]
    if author:
        texts.append(
            _spine_text(
                "spine_author", author, preset.spine_face, size, baseline, safe.y, Anchor.END, color
            )
        )
    return texts, SpineStatus(True, True, None, size)


def _back(
    copy: CoverCopy, preset: Preset, config: CoverConfig, geometry: CoverGeometry, color: RGB
) -> tuple[list[CoverText], Box | None, Box | None]:
    area = geometry.back_design
    texts: list[CoverText] = []
    imprint_box: Box | None = None
    floor = geometry.barcode_keep_clear.top + BACK_GAP
    if copy.imprint:
        _check_glyphs(copy.imprint, preset.imprint_face, "cover.imprint")
        m = metrics(preset.imprint_face)
        line = _text(
            "imprint",
            copy.imprint,
            preset.imprint_face,
            preset.imprint_size,
            area.x,
            area.y + m.descent * preset.imprint_size,
            Anchor.START,
            color,
        )
        if line.bounds.right > geometry.barcode_keep_clear.x - BACK_GAP:
            raise _fail(
                "text_overflow", "The imprint is too long for the back cover.", "cover.imprint"
            )
        texts.append(line)
        imprint_box = line.bounds
        floor = max(floor, line.bounds.top + BACK_GAP)
    if not copy.back_text:
        return texts, None, imprint_box
    _check_glyphs(copy.back_text, preset.body_face, "cover.back_text")
    measure = min(area.width, BACK_MEASURE)
    lines = wrap(copy.back_text, preset.body_face, preset.body_size, measure)
    if lines is None:
        raise _fail(
            "text_overflow", "A word in the back-cover text is too wide.", "cover.back_text"
        )
    block = _group("back_text", lines, preset.body_face, preset.body_size, preset.body_pitch, 0.0)
    height = _height(block)
    if area.top - height < floor - 1e-6:
        raise _fail(
            "text_overflow",
            "The back-cover text is too long to stay clear of the barcode area.",
            "cover.back_text",
            actual=f"{height / 72:.2f} in",
            required=f"at most {(area.top - floor) / 72:.2f} in",
        )
    center = config.type.align is TextAlign.CENTER
    x, anchor = (area.x + area.width / 2, Anchor.MIDDLE) if center else (area.x, Anchor.START)
    left = x - measure / 2 if center else x
    texts = _place(block, area.top, x, anchor, color) + texts
    return texts, Box(left, area.top - height, measure, height), imprint_box


def _band(
    x0: float, x1: float, box: Box, media: Box, tone: TextTone, pad: float = SHADE_PAD
) -> ShadeBand:
    low, high = box.y - pad, box.top + pad
    if low - media.y <= EDGE_SNAP:
        low = media.y
    if media.top - high <= EDGE_SNAP:
        high = media.top
    return ShadeBand(x0, x1, (low, high), SHADE_FADE, SHADE_STRENGTH[tone], SHADE_TOWARD[tone])


def _panel(role: str, x0: float, x1: float, box: Box, media: Box, color: RGB) -> Fill:
    low = max(media.y, box.y - PANEL_PAD)
    high = min(media.top, box.top + PANEL_PAD)
    return Fill(role, Box(x0, low, x1 - x0, high - low), color)


def layout_cover(
    book_id: str,
    copy: CoverCopy,
    config: CoverConfig,
    geometry: CoverGeometry,
    photo: PhotoInfo,
) -> CoverLayout:
    """Raises CoverError(stage 'layout') when authored text cannot be set safely."""
    preset = PRESETS[config.type.style]
    color = LIGHT if config.type.tone is TextTone.LIGHT else DARK
    media = geometry.media
    full = config.layout is CoverLayoutKind.FULL_WRAP
    region = (
        media
        if full
        else Box(geometry.front.x, media.y, media.right - geometry.front.x, media.height)
    )
    window = crop_window(photo.width, photo.height, region, config.crop)
    front, title_box, author_box = _front(copy, preset, config, geometry.front_design, color)
    spine, spine_status = _spine(copy, preset, config, geometry, color)
    back, back_box, imprint_box = _back(copy, preset, config, geometry, color)

    fill = config.rgb()
    panels: list[Fill] = []
    bands: list[ShadeBand] = []
    tone = config.type.tone
    # (x range, text bounds) for every text group printed over the photograph.
    over_photo: list[tuple[str, float, float, Box]] = [
        ("front_title", geometry.front.x, media.right, title_box)
    ]
    if author_box is not None:
        over_photo.append(("front_author", geometry.front.x, media.right, author_box))
    if full:
        if back_box is not None:
            over_photo.append(("back_text", media.x, geometry.back.right, back_box))
        if imprint_box is not None:
            over_photo.append(("imprint", media.x, geometry.barcode_keep_clear.x, imprint_box))
    if config.legibility is Legibility.PANEL:
        panels = [
            _panel(f"panel_{role}", x0, x1, box, media, fill) for role, x0, x1, box in over_photo
        ]
        if full and spine:
            panels.append(Fill("panel_spine", geometry.spine, fill))
    elif config.legibility is Legibility.SHADE:
        # Across a full wrap, bands span the whole photo so no band edge lands mid-image.
        span = (region.x, region.right)
        bands = [
            _band(*(span if full else (x0, x1)), box, media, tone) for _, x0, x1, box in over_photo
        ]
        if full and spine:
            bands.append(
                ShadeBand(
                    geometry.spine.x,
                    geometry.spine.right,
                    (media.y, media.top),
                    0.0,
                    SHADE_STRENGTH[tone],
                    SHADE_TOWARD[tone],
                )
            )
    # In front_photo layouts the back and spine are the solid fill: no treatment.

    photo_element = CoverPhoto(
        photo.sha256,
        region,
        image_placement(window, region),
        window,
        window.pixel_bounds(),
        tuple(bands),
    )
    resolution = ImageResolution(
        (photo.width, photo.height),
        (window.width, window.height),
        (region.width / 72, region.height / 72),
        window.effective_dpi,
        window.max_dpi,
        KDP_COVER.min_image_dpi,
    )
    return CoverLayout(
        book_id=book_id,
        config=config,
        geometry=geometry,
        background=Fill("background", media, fill),
        photo=photo_element,
        panels=tuple(panels),
        texts=tuple(front + spine + back),
        spine=spine_status,
        resolution=resolution,
    )
