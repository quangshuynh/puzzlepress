"""Rich text layout: styled runs to measured cover lines, deterministically.

Python decides every position: faces for bold and italic, the size and color of
each run, greedy word wrapping across style changes, list markers and their
indent, per-block alignment and spacing, and the underline boxes. The result is
ordinary `CoverText` lines (one per style segment), so validation, overlap and
safe-area checks, PDF inspection and Studio's text boxes work unchanged.

A document without formatting lays out exactly like its plain text: a line in a
single style becomes one `CoverText` anchored as the plain layout anchors it, and
the line pitch uses the same arithmetic. A face that has no bold or italic cut is
an explicit failure (`font_variant_unavailable`), never a substitution.
"""

from dataclasses import dataclass, replace

from ..cover_design import MIN_STROKE
from ..cover_richtext import BlockAlign, BlockType, ListKind, RichText, Run
from ..interior.issues import LayoutIssue
from ..interior.model import Anchor, Box
from .fonts import CoverFace, metrics, missing_characters, text_width
from .issues import CoverError
from .model import RGB, CoverText

HEADING_SCALE = 1.25
LIST_INDENT = 1.6  # Hanging indent of a list item, in multiples of its size.
MARKER_GAP = 0.35  # Space between a list marker and the item text, in multiples of its size.
UNDERLINE_DROP = 0.1  # Top of the underline below the baseline, per point of size.
UNDERLINE_WEIGHT = 0.06  # Thickness per point of size, never below KDP's 0.75 pt line.
BULLET = "•"

# (family, bold, italic) -> bundled face. Missing combinations are not substituted.
_BUNDLED: dict[tuple[str, bool, bool], str] = {
    ("sans", False, False): CoverFace.SANS,
    ("sans", True, False): CoverFace.SANS_BOLD,
    ("sans", False, True): CoverFace.SANS_ITALIC,
    ("serif", False, False): CoverFace.SERIF,
    ("serif", False, True): CoverFace.SERIF_ITALIC,
    ("serif-display", False, False): CoverFace.SERIF_DISPLAY,
}
_FAMILY_OF: dict[str, tuple[str, bool, bool]] = {face: key for key, face in _BUNDLED.items()}
# Family names as authors and Studio show them.
FAMILY_NAMES = {"sans": "Vera Sans", "serif": "Newsreader", "serif-display": "Newsreader Display"}


def family_of(face: str) -> tuple[str, bool, bool]:
    """The family, weight and style a face key stands for (an imported face is its own family)."""
    return _FAMILY_OF.get(face, (face, False, False))


def variants() -> dict[str, list[str]]:
    """For Studio: the bundled families and the variants each has (regular, bold, italic)."""
    table: dict[str, list[str]] = {}
    for (family, bold, italic), _ in _BUNDLED.items():
        table.setdefault(family, []).append("bold" if bold else "italic" if italic else "regular")
    return table


@dataclass(frozen=True)
class Base:
    """What a document inherits from the text box or layer that holds it."""

    face: str  # A resolved face key (bundled CoverFace value or imported registered name).
    size: float
    color: RGB
    pitch: float  # Line spacing as a multiple of size.
    tracking: float
    upper: bool
    align: BlockAlign


@dataclass(frozen=True)
class _Style:
    face: str
    size: float
    color: RGB
    underline: bool


@dataclass(frozen=True)
class _Piece:
    text: str
    style: _Style


@dataclass(frozen=True)
class _Line:
    pieces: tuple[_Piece, ...]
    style: _Style  # The block's own style, for an empty line's metrics.
    pitch: float
    gap_extra: float  # Block spacing added before this line.
    area: Box  # Where the line is aligned (indented for list items).
    align: BlockAlign
    marker: _Piece | None = None


def _fail(code: str, message: str, region: str, actual: str | None = None) -> CoverError:
    return CoverError("layout", (LayoutIssue(code, message, region=region, actual=actual),))


def _rgb(value: str) -> RGB:
    return (int(value[1:3], 16) / 255, int(value[3:5], 16) / 255, int(value[5:7], 16) / 255)


def _face(base: Base, run: Run, heading: bool, keys: dict[str, str], region: str) -> str:
    family, bold, italic = family_of(base.face)
    if run.font is not None:
        # A bundled family by name, or an imported font's id (its registered face).
        family, bold, italic = keys.get(run.font, run.font), False, False
    if heading and run.bold is None and run.font is None:
        # Headings use the family's display or bold cut, as Studio describes them.
        if family == "sans":
            bold = True
        elif family == "serif" and not italic:
            family = "serif-display"
    bold = bold if run.bold is None else run.bold
    italic = italic if run.italic is None else run.italic
    if family in {"sans", "serif", "serif-display"}:
        face = _BUNDLED.get((family, bold, italic))
        if face is None:
            wanted = " ".join(w for w, on in (("bold", bold), ("italic", italic)) if on)
            raise _fail(
                "font_variant_unavailable",
                f"{FAMILY_NAMES[family]} has no {wanted} face here. Choose another font or remove "
                f"the {wanted} formatting; PuzzlePress never imitates a missing face.",
                region,
                actual=f"{FAMILY_NAMES[family]} {wanted}",
            )
        return str(face)
    if bold or italic:
        raise _fail(
            "font_variant_unavailable",
            "An imported font is a single face: it has no bold or italic variant here. Import "
            "the variant as its own font, or remove the formatting.",
            region,
        )
    return family


def _style(base: Base, run: Run, heading: bool, keys: dict[str, str], region: str) -> _Style:
    size = run.size if run.size is not None else base.size
    if heading and run.size is None:
        size = round(base.size * HEADING_SCALE, 2)
    color = _rgb(run.color) if run.color is not None else base.color
    return _Style(_face(base, run, heading, keys, region), size, color, run.underline)


def _segments(pieces: tuple[_Piece, ...]) -> list[_Piece]:
    merged: list[_Piece] = []
    for piece in pieces:
        if merged and merged[-1].style == piece.style:
            merged[-1] = _Piece(merged[-1].text + piece.text, piece.style)
        else:
            merged.append(piece)
    return merged


def _width(pieces: tuple[_Piece, ...], tracking: float) -> float:
    segments = _segments(pieces)
    total = sum(text_width(s.text, s.style.face, s.style.size, tracking) for s in segments)
    return total + tracking * max(0, len(segments) - 1)


def _tokens(runs: list[tuple[str, _Style]]) -> list[tuple[str, tuple[_Piece, ...]]]:
    """Words (pieces across style changes), single spaces and explicit breaks."""
    tokens: list[tuple[str, tuple[_Piece, ...]]] = []
    word: list[_Piece] = []

    def finish() -> None:
        if word:
            tokens.append(("word", tuple(word)))
            word.clear()

    for text, style in runs:
        for char in text:
            if char == "\n":
                finish()
                tokens.append(("break", ()))
            elif char == " ":
                finish()
                tokens.append(("space", (_Piece(" ", style),)))
            elif word and word[-1].style == style:
                word[-1] = _Piece(word[-1].text + char, style)
            else:
                word.append(_Piece(char, style))
    finish()
    return tokens


def _wrap(
    tokens: list[tuple[str, tuple[_Piece, ...]]], measure: float, tracking: float, region: str
) -> list[tuple[_Piece, ...]]:
    """Greedy wrap as the plain layout does: single spaces, authored breaks kept."""
    lines: list[tuple[_Piece, ...]] = []
    current: tuple[_Piece, ...] = ()
    space: tuple[_Piece, ...] = ()
    for kind, pieces in tokens:
        if kind == "break":
            lines.append(current)
            current, space = (), ()
        elif kind == "space":
            if current and not space:
                space = pieces
        else:
            if _width(pieces, tracking) > measure:
                raise _fail(
                    "text_overflow",
                    "A word in this text is wider than its box; widen it or set a smaller size.",
                    region,
                    actual="".join(p.text for p in pieces),
                )
            candidate = (*current, *space, *pieces) if current else pieces
            if current and _width(candidate, tracking) > measure:
                lines.append(current)
                current = pieces
            else:
                current = candidate
            space = ()
    lines.append(current)
    return lines


def _metrics(line: _Line) -> tuple[float, float, float]:
    """Ascent, descent and the gap before this line, in points."""
    styles = [p.style for p in line.pieces] or [line.style]
    if line.marker is not None:
        styles.append(line.marker.style)
    if len({(s.face, s.size) for s in styles}) == 1:
        style = styles[0]
        m = metrics(style.face)
        within = max(0.0, (line.pitch - m.ascent - m.descent) * style.size)
        return m.ascent * style.size, m.descent * style.size, within
    ascent = max(metrics(s.face).ascent * s.size for s in styles)
    descent = max(metrics(s.face).descent * s.size for s in styles)
    biggest = max(s.size for s in styles)
    return ascent, descent, max(0.0, line.pitch * biggest - ascent - descent)


def _anchor(area: Box, align: BlockAlign) -> tuple[float, Anchor]:
    if align is BlockAlign.CENTER:
        return area.x + area.width / 2, Anchor.MIDDLE
    if align is BlockAlign.RIGHT:
        return area.right, Anchor.END
    return area.x, Anchor.START


def _text(
    role: str,
    piece: _Piece,
    x: float,
    baseline: float,
    anchor: Anchor,
    tracking: float,
) -> CoverText:
    style = piece.style
    width = text_width(piece.text, style.face, style.size, tracking)
    m = metrics(style.face)
    left = {Anchor.START: x, Anchor.MIDDLE: x - width / 2, Anchor.END: x - width}[anchor]
    bounds = Box(
        left, baseline - m.descent * style.size, width, (m.ascent + m.descent) * style.size
    )
    underline = None
    if style.underline and piece.text.strip():
        weight = max(MIN_STROKE, UNDERLINE_WEIGHT * style.size)
        top = baseline - UNDERLINE_DROP * style.size
        low = max(bounds.y, top - weight)
        underline = Box(left, low, width, top - low)
    return CoverText(
        role,
        piece.text,
        style.face,
        style.size,
        (x, baseline),
        anchor,
        False,
        bounds,
        style.color,
        tracking,
        underline,
    )


def _lines(
    document: RichText,
    base: Base,
    frame: Box,
    keys: dict[str, str],
    region: str,
) -> list[_Line]:
    lines: list[_Line] = []
    number = 0
    previous_after = 0.0
    for index, block in enumerate(document.blocks):
        heading = block.type is BlockType.HEADING
        number = number + 1 if block.list is ListKind.NUMBER else 0
        styled = [(run, _style(base, run, heading, keys, region)) for run in block.runs]
        block_style = _style(base, Run(" "), heading, keys, region)
        runs = [(run.text.upper() if base.upper else run.text, style) for run, style in styled]
        for text, style in runs:
            missing = missing_characters(text, style.face)
            if missing:
                listed = ", ".join(f"U+{ord(c):04X}" for c in missing)
                raise _fail(
                    "unsupported_character",
                    f"The cover font cannot draw: {listed}.",
                    region,
                    actual=listed,
                )
        area, marker = frame, None
        if block.list is not None:
            first = styled[0][1] if styled else block_style
            indent = LIST_INDENT * first.size
            area = Box(frame.x + indent, frame.y, max(1.0, frame.width - indent), frame.height)
            label = BULLET if block.list is ListKind.BULLET else f"{number}."
            if missing_characters(label, first.face):
                raise _fail(
                    "unsupported_character",
                    "The cover font cannot draw the list marker.",
                    region,
                )
            marker = _Piece(label, replace(first, underline=False))
        pitch = block.line_spacing if block.line_spacing is not None else base.pitch
        align = block.align or base.align
        gap = (previous_after + block.space_before) if index else 0.0
        wrapped = _wrap(_tokens(runs), area.width, base.tracking, region)
        for position, pieces in enumerate(wrapped):
            lines.append(
                _Line(
                    pieces,
                    block_style,
                    pitch,
                    gap if position == 0 else 0.0,
                    area,
                    align,
                    marker if position == 0 else None,
                )
            )
        previous_after = block.space_after
    return lines


def layout_rich(
    document: RichText,
    base: Base,
    frame: Box,
    top: float,
    role: str,
    keys: dict[str, str],
    region: str,
) -> tuple[list[CoverText], float]:
    """Lines from `top` down inside `frame`; returns the texts and the block height.

    `keys` maps imported font ids to their registered face keys. Lines that do
    not fit below are still placed; the caller's validation reports overflow.
    """
    placed: list[CoverText] = []
    cursor = top
    tracking = base.tracking
    for index, line in enumerate(_lines(document, base, frame, keys, region)):
        ascent, descent, within = _metrics(line)
        if index:
            cursor -= within + line.gap_extra
        baseline = cursor - ascent
        cursor = baseline - descent
        segments = _segments(tuple(_trim(line.pieces)))
        if line.marker is not None:
            marker_x = line.area.x - MARKER_GAP * line.marker.style.size
            placed.append(_text(role, line.marker, marker_x, baseline, Anchor.END, 0.0))
        if not segments:
            continue
        if len(segments) == 1:
            x, anchor = _anchor(line.area, line.align)
            placed.append(_text(role, segments[0], x, baseline, anchor, tracking))
            continue
        total = _width(tuple(segments), tracking)
        left = {
            BlockAlign.LEFT: line.area.x,
            BlockAlign.CENTER: line.area.x + (line.area.width - total) / 2,
            BlockAlign.RIGHT: line.area.right - total,
        }[line.align]
        for segment in segments:
            text = _text(role, segment, left, baseline, Anchor.START, tracking)
            placed.append(text)
            left = text.bounds.right + tracking
    return placed, top - cursor


def _trim(pieces: tuple[_Piece, ...]) -> list[_Piece]:
    """A wrapped line never starts or ends with a space (as in the plain layout)."""
    items = list(pieces)
    while items and items[0].text == " ":
        items.pop(0)
    while items and items[-1].text == " ":
        items.pop()
    return items
