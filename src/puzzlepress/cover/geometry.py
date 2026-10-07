"""Full-wrap paperback cover geometry from authoritative interior facts.

Coordinates are PDF points with the origin at the bottom-left corner of the
media box (the outer bleed edge) and y upward. Left to right the wrap is:
bleed | back cover | spine | front cover | bleed. Every value derives from the
built interior's page count and print profile; nothing is authored or guessed.
"""

from dataclasses import dataclass

from ..interior.model import Box
from ..interior.spec import KDP_COVER, SUPPORTED_TRIMS, TOLERANCE, Paper, inches, to_inches
from .issues import cover_error

# PuzzlePress recommendations, stricter than KDP's 0.125 in safe area: front and
# back type stays half an inch from every panel edge (trim and fold).
DESIGN_INSET = inches(0.5)
# Where KDP is expected to print its barcode: KDP states the 2 x 1.2 in size and
# the lower-right corner of the back cover, not offsets for paperbacks. These
# offsets follow KDP's hardcover guidance (0.25 in from the spine) and are a
# PuzzlePress assumption; the keep-clear region extends to the trim and the fold.
BARCODE_OFFSET = inches(0.25)
BARCODE_CLEARANCE = inches(0.125)
# Spine type keeps this far from the top and bottom trim (KDP text safe area).
SPINE_END_INSET = KDP_COVER.text_safe_inset


@dataclass(frozen=True)
class CoverGeometry:
    page_count: int
    paper: Paper
    bleed: float
    spine_width: float
    media: Box  # Full wrap including bleed.
    trim: Box  # Back + spine + front at final size.
    back: Box
    spine: Box
    front: Box
    back_safe: Box  # KDP: text at least 0.125 in inside trim and fold lines.
    front_safe: Box
    spine_safe: Box  # KDP: 0.0625 in from each fold; 0.125 in from top and bottom trim.
    back_design: Box  # PuzzlePress: 0.5 in from every panel edge.
    front_design: Box
    barcode: Box  # Expected barcode position (assumption, see BARCODE_OFFSET).
    barcode_keep_clear: Box  # Lower-right back corner reserved for the barcode.
    spine_text_allowed: bool  # KDP page-count eligibility only.

    def to_dict(self) -> dict[str, object]:
        def box(value: Box) -> dict[str, float]:
            return {k: round(getattr(value, k), 4) for k in ("x", "y", "width", "height")}

        regions = (
            "media",
            "trim",
            "back",
            "spine",
            "front",
            "back_safe",
            "front_safe",
            "spine_safe",
            "back_design",
            "front_design",
            "barcode",
            "barcode_keep_clear",
        )
        return {
            "page_count": self.page_count,
            "paper": self.paper.value,
            "bleed_in": round(to_inches(self.bleed), 6),
            "spine_width_in": round(to_inches(self.spine_width), 6),
            "spine_width_pt": round(self.spine_width, 4),
            "width_in": round(to_inches(self.media.width), 6),
            "height_in": round(to_inches(self.media.height), 6),
            "spine_text_allowed": self.spine_text_allowed,
            "regions": {name: box(getattr(self, name)) for name in regions},
        }


def inset(box: Box, left: float, bottom: float, right: float, top: float) -> Box:
    return Box(box.x + left, box.y + bottom, box.width - left - right, box.height - bottom - top)


def cover_geometry(
    page_count: int, trim_width: float, trim_height: float, paper: Paper
) -> CoverGeometry:
    """Wrap geometry for an interior. Raises CoverError(stage 'geometry')."""
    if page_count < 1:
        raise cover_error("geometry", "invalid_page_count", "The interior has no pages.")
    if not any(
        abs(trim_width - s.width) <= TOLERANCE and abs(trim_height - s.height) <= TOLERANCE
        for s in SUPPORTED_TRIMS
    ):
        raise cover_error(
            "geometry",
            "unsupported_trim_size",
            "The interior trim has no cover template.",
            actual=f"{to_inches(trim_width):g}x{to_inches(trim_height):g} in",
            required=", ".join(s.name for s in SUPPORTED_TRIMS),
        )
    bleed = KDP_COVER.bleed
    spine = KDP_COVER.spine_width(page_count, paper)
    media = Box(0.0, 0.0, 2 * bleed + 2 * trim_width + spine, 2 * bleed + trim_height)
    trim = Box(bleed, bleed, 2 * trim_width + spine, trim_height)
    back = Box(bleed, bleed, trim_width, trim_height)
    spine_box = Box(back.right, bleed, spine, trim_height)
    front = Box(spine_box.right, bleed, trim_width, trim_height)
    safe = KDP_COVER.text_safe_inset
    clear = KDP_COVER.spine_text_clearance
    barcode = Box(
        back.right - BARCODE_OFFSET - KDP_COVER.barcode_width,
        back.y + BARCODE_OFFSET,
        KDP_COVER.barcode_width,
        KDP_COVER.barcode_height,
    )
    keep_left = barcode.x - BARCODE_CLEARANCE
    keep_clear = Box(
        keep_left, back.y, back.right - keep_left, barcode.top + BARCODE_CLEARANCE - back.y
    )
    return CoverGeometry(
        page_count=page_count,
        paper=paper,
        bleed=bleed,
        spine_width=spine,
        media=media,
        trim=trim,
        back=back,
        spine=spine_box,
        front=front,
        back_safe=inset(back, safe, safe, safe, safe),
        front_safe=inset(front, safe, safe, safe, safe),
        spine_safe=inset(spine_box, clear, SPINE_END_INSET, clear, SPINE_END_INSET),
        back_design=inset(back, DESIGN_INSET, DESIGN_INSET, DESIGN_INSET, DESIGN_INSET),
        front_design=inset(front, DESIGN_INSET, DESIGN_INSET, DESIGN_INSET, DESIGN_INSET),
        barcode=barcode,
        barcode_keep_clear=keep_clear,
        spine_text_allowed=page_count >= KDP_COVER.spine_text_min_pages,
    )


def trim_name(trim_width: float, trim_height: float) -> str:
    for size in SUPPORTED_TRIMS:
        if (
            abs(trim_width - size.width) <= TOLERANCE
            and abs(trim_height - size.height) <= TOLERANCE
        ):
            return size.name
    return f"{to_inches(trim_width):g}x{to_inches(trim_height):g}"
