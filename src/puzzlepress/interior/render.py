"""PDF renderer: draws an InteriorLayout exactly, deciding no positions itself.

ReportLab's invariant mode fixes timestamps and the document ID, so identical
layouts produce identical bytes. Ink is DeviceGray only; nothing is transparent.
No annotations, outlines, marks or links are written.
"""

import io
import math

from reportlab.pdfgen.canvas import Canvas

from .. import __version__
from .fonts import font_name
from .model import Anchor, Face, InteriorLayout, LetterGrid, Rule, TextLine


def render_pdf(layout: InteriorLayout) -> bytes:
    buffer = io.BytesIO()
    size = (layout.spec.trim.width, layout.spec.trim.height)
    # A TrueType initial font keeps ReportLab from adding an unembedded Helvetica.
    canvas = Canvas(
        buffer,
        pagesize=size,
        invariant=True,
        pageCompression=True,
        initialFontName=font_name(Face.REGULAR),  # type: ignore[arg-type]  # stub says float
    )
    # KDP asks for no metadata: write empty descriptive fields, not library defaults.
    canvas.setTitle("")
    canvas.setAuthor("")
    canvas.setSubject("")
    canvas.setKeywords("")
    canvas.setCreator(f"PuzzlePress {__version__}")
    for page in layout.pages:
        media, trim = page.frame.media, page.frame.trim
        canvas.setPageSize((media.width, media.height))
        canvas.setTrimBox((trim.x, trim.y, trim.right, trim.top))
        for element in page.elements:
            if isinstance(element, TextLine):
                _text(canvas, element)
            elif isinstance(element, Rule):
                _rule(canvas, element)
            else:
                _grid(canvas, element)
        canvas.showPage()
    canvas.save()
    return buffer.getvalue()


def _text(canvas: Canvas, line: TextLine) -> None:
    canvas.setFont(font_name(line.face), line.size)
    canvas.setFillGray(line.gray)
    draw = {
        Anchor.START: canvas.drawString,
        Anchor.MIDDLE: canvas.drawCentredString,
        Anchor.END: canvas.drawRightString,
    }[line.anchor]
    draw(line.x, line.baseline, line.text)


def _rule(canvas: Canvas, rule: Rule) -> None:
    canvas.setStrokeGray(rule.gray)
    canvas.setLineWidth(rule.width)
    canvas.line(rule.x1, rule.y1, rule.x2, rule.y2)


def _grid(canvas: Canvas, grid: LetterGrid) -> None:
    canvas.setStrokeGray(0)
    canvas.setLineWidth(grid.frame_width)
    frame = grid.frame
    canvas.rect(frame.x, frame.y, frame.width, frame.height, stroke=1, fill=0)
    for row, letters in enumerate(grid.rows):
        for column, letter in enumerate(letters):
            emphasized = (column, row) in grid.emphasized
            face = grid.emphasized_face if emphasized else grid.face
            canvas.setFont(font_name(face), grid.letter_size)
            canvas.setFillGray(0 if emphasized or not grid.marks else grid.muted_gray)
            x, y = grid.center(column, row)
            canvas.drawCentredString(x, y - grid.baseline_offset, letter)
    for mark in grid.marks:
        (x1, y1), (x2, y2) = mark.start, mark.end
        length = math.hypot(x2 - x1, y2 - y1)
        radius = mark.radius
        canvas.saveState()
        canvas.setLineWidth(mark.line_width)
        canvas.translate(x1, y1)
        canvas.rotate(math.degrees(math.atan2(y2 - y1, x2 - x1)))
        canvas.roundRect(
            -radius, -radius, length + 2 * radius, 2 * radius, radius, stroke=1, fill=0
        )
        canvas.restoreState()
