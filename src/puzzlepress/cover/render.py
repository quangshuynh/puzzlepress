"""Cover renderer: draws a CoverLayout exactly, deciding no positions itself.

The photograph is cropped to the layout's whole-pixel window, any shade bands
are baked into those pixels, and the result is encoded once as a baseline JPEG
(quality 95, no chroma subsampling) built from bare pixels, so no EXIF, GPS,
XMP, ICC or comment data can reach the PDF. It is embedded as DCTDecode
DeviceRGB, clipped to its region. Fills and text are DeviceRGB. Nothing is
transparent or stroked. ReportLab's invariant mode fixes dates and the ID.
"""

import hashlib
import io
import math
from typing import Any

from PIL import Image
from reportlab.pdfbase import pdfdoc
from reportlab.pdfgen.canvas import Canvas

from .. import __version__
from ..interior.model import Anchor, Box
from .assets import Photo
from .fonts import CoverFace, font_name
from .model import CoverLayout, CoverPhoto, CoverText, ShadeBand

JPEG_QUALITY = 95


def _apply_shade(image: Image.Image, photo: CoverPhoto, band: ShadeBand) -> Image.Image:
    """Blend pixels toward the band's color by a per-row weight, inside its columns."""
    placement, scale = photo.placement, photo.window.scale
    width, height = image.size
    first = max(0, math.ceil((band.x0 - placement.x) / scale - 0.5))
    last = min(width - 1, math.floor((band.x1 - placement.x) / scale - 0.5))
    if last < first:
        return image
    rows = bytes(
        round(255 * band.weight(placement.top - (row + 0.5) * scale)) for row in range(height)
    )
    if not any(rows):
        return image
    strip = Image.frombytes("L", (1, height), rows).resize(
        (last - first + 1, height), Image.Resampling.NEAREST
    )
    mask = Image.new("L", (width, height), 0)
    mask.paste(strip, (first, 0))
    return Image.composite(Image.new("RGB", (width, height), band.toward), image, mask)


def prepare_photo(photo: Photo, layout: CoverPhoto) -> tuple[bytes, tuple[int, int]]:
    """JPEG bytes of exactly the pixels the layout prints, and their pixel size."""
    if photo.info.sha256 != layout.sha256:
        raise ValueError("The decoded photo is not the one the layout was made for")
    image = photo.image.crop(layout.pixels)
    for band in layout.shade:
        image = _apply_shade(image, layout, band)
    bare = Image.frombytes("RGB", image.size, image.tobytes())  # No info dictionary at all.
    buffer = io.BytesIO()
    bare.save(
        buffer, "JPEG", quality=JPEG_QUALITY, subsampling=0, optimize=False, progressive=False
    )
    return buffer.getvalue(), bare.size


def _draw_jpeg(canvas: Canvas, jpeg: bytes, size: tuple[int, int], box: Box) -> None:
    """Embed JPEG bytes unchanged as one DCTDecode image XObject (no ASCII85 wrapper).

    Mirrors Canvas.drawImage's registration without decoding the image to name it.
    """
    name = "PPCoverPhoto" + hashlib.sha256(jpeg).hexdigest()[:16]
    # ReportLab's private registration API (pinned 5.0.x; untyped in the stubs).
    raw: Any = canvas
    image: Any = pdfdoc.PDFImageXObject(name)
    image.width, image.height = size
    image.bitsPerComponent = 8
    image.colorSpace = "DeviceRGB"
    image.streamContent = jpeg
    image._filters = ("DCTDecode",)
    image.mask = None
    registered = raw._doc.getXObjectName(name)
    raw._setXObjects(image)
    raw._doc.Reference(image, registered)
    raw._doc.addForm(name, image)
    canvas.saveState()
    canvas.translate(box.x, box.y)
    canvas.scale(box.width, box.height)
    raw._code.append(f"/{registered} Do")
    canvas.restoreState()
    raw._formsinuse.append(name)


def _rect(canvas: Canvas, box: Box, color: tuple[float, float, float]) -> None:
    canvas.setFillColorRGB(*color)
    canvas.rect(box.x, box.y, box.width, box.height, stroke=0, fill=1)


def _text(canvas: Canvas, line: CoverText) -> None:
    canvas.setFont(font_name(line.face), line.size)
    canvas.setFillColorRGB(*line.color)
    draw = {
        Anchor.START: canvas.drawString,
        Anchor.MIDDLE: canvas.drawCentredString,
        Anchor.END: canvas.drawRightString,
    }[line.anchor]
    if line.tracking:  # Only horizontal lines are letter-spaced.
        # They start at their measured left edge; Tc adds the spacing.
        canvas.drawString(line.bounds.x, line.origin[1], line.text, charSpace=line.tracking)
        return
    if line.rotated:
        canvas.saveState()
        canvas.translate(*line.origin)
        canvas.rotate(-90)  # Spine text reads top to bottom.
        draw(0, 0, line.text)
        canvas.restoreState()
    else:
        draw(line.origin[0], line.origin[1], line.text)


def render_cover_pdf(layout: CoverLayout, jpeg: bytes, size: tuple[int, int]) -> bytes:
    g = layout.geometry
    buffer = io.BytesIO()
    canvas = Canvas(
        buffer,
        pagesize=(g.media.width, g.media.height),
        invariant=True,
        pageCompression=True,
        initialFontName=font_name(CoverFace.SANS),  # type: ignore[arg-type]  # stub says float
    )
    # KDP asks for no metadata: write empty descriptive fields, not library defaults.
    canvas.setTitle("")
    canvas.setAuthor("")
    canvas.setSubject("")
    canvas.setKeywords("")
    canvas.setCreator(f"PuzzlePress {__version__}")
    trim = g.trim
    canvas.setTrimBox((trim.x, trim.y, trim.right, trim.top))
    canvas.setBleedBox((g.media.x, g.media.y, g.media.right, g.media.top))
    _rect(canvas, layout.background.box, layout.background.color)
    region = layout.photo.region
    canvas.saveState()
    path = canvas.beginPath()
    path.rect(region.x, region.y, region.width, region.height)
    canvas.clipPath(path, stroke=0, fill=0)
    _draw_jpeg(canvas, jpeg, size, layout.photo.placement)
    canvas.restoreState()
    for panel in layout.panels:
        _rect(canvas, panel.box, panel.color)
    for line in layout.texts:
        _text(canvas, line)
    canvas.showPage()
    canvas.save()
    return buffer.getvalue()
