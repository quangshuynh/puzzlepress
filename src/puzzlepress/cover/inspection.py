"""Independent cover PDF inspection with pypdf: observed facts, then contract checks.

Builds on the interior's `read_pdf_facts` (boxes, fonts, transparency,
annotations, metadata) and adds what a photographic cover needs: the image
XObjects with their filters and the JPEG segments they carry, the content
operators used (no stroked guides or marks) and the XMP metadata stream.
"""

import io
import re
from dataclasses import dataclass

from pypdf import PdfReader
from pypdf.errors import PyPdfError
from pypdf.generic import ContentStream, DictionaryObject

from ..interior.inspection import PdfFacts, read_pdf_facts, same_box
from ..interior.issues import LayoutIssue
from .fonts import BUNDLED_FAMILIES
from .model import CoverLayout

STROKE_OPERATORS = frozenset({"S", "s", "B", "B*", "b", "b*"})
# JPEG segments that may carry camera, location, color-profile or comment data.
PRIVATE_SEGMENTS = frozenset({f"APP{n}" for n in range(1, 16)} | {"COM"})
_SUBSET = re.compile(r"^/?[A-Z]{6}\+")


@dataclass(frozen=True)
class PdfImage:
    width: int
    height: int
    filters: tuple[str, ...]
    color_space: str
    segments: tuple[str, ...]  # JPEG marker segments, for DCTDecode images.


@dataclass(frozen=True)
class CoverPdfFacts:
    base: PdfFacts
    images: tuple[PdfImage, ...]
    operators: frozenset[str]
    xmp_metadata: bool


def jpeg_segments(data: bytes) -> tuple[str, ...]:
    """Marker segment names up to the start of scan; ('INVALID',) if malformed."""
    if not data.startswith(b"\xff\xd8"):
        return ("INVALID",)
    names: list[str] = []
    position = 2
    while position + 4 <= len(data):
        if data[position] != 0xFF:
            return (*names, "INVALID")
        marker = data[position + 1]
        length = int.from_bytes(data[position + 2 : position + 4], "big")
        if 0xE0 <= marker <= 0xEF:
            names.append(f"APP{marker - 0xE0}")
        elif marker == 0xFE:
            names.append("COM")
        elif marker == 0xDA:
            names.append("SOS")
            return tuple(names)
        else:
            names.append(f"{marker:02X}")
        position += 2 + length
    return (*names, "INVALID")


def read_cover_facts(data: bytes) -> CoverPdfFacts | LayoutIssue:
    base = read_pdf_facts(data)
    if isinstance(base, LayoutIssue):
        return base
    try:
        reader = PdfReader(io.BytesIO(data), strict=True)
        images: list[PdfImage] = []
        operators: set[str] = set()
        for page in reader.pages:
            resources = page.get("/Resources")
            resources = resources.get_object() if resources is not None else DictionaryObject()
            xobjects = resources.get("/XObject")
            for item in xobjects.get_object().values() if xobjects is not None else []:
                image = item.get_object()
                if image.get("/Subtype") != "/Image":
                    continue
                raw = image.get("/Filter")
                filters = tuple(
                    str(f) for f in (raw if isinstance(raw, list) else [raw] if raw else [])
                )
                stream = image.get_data() if filters == ("/DCTDecode",) else b""
                images.append(
                    PdfImage(
                        int(image["/Width"]),
                        int(image["/Height"]),
                        filters,
                        str(image.get("/ColorSpace")),
                        jpeg_segments(stream) if stream else (),
                    )
                )
            contents = page.get_contents()
            if contents is not None:
                for _, operator in ContentStream(contents, reader).operations:
                    operators.add(operator.decode("latin-1"))
        return CoverPdfFacts(
            base, tuple(images), frozenset(operators), "/Metadata" in reader.root_object
        )
    except (PyPdfError, ValueError, KeyError, TypeError, AttributeError, OSError) as error:
        return LayoutIssue("pdf_unreadable", f"The cover PDF does not parse: {error}")


def _family(name: str) -> str:
    return _SUBSET.sub("", name.lstrip("/"))


def cover_contract_issues(
    facts: CoverPdfFacts,
    layout: CoverLayout,
    image_sizes: tuple[tuple[int, int], ...] | None,
) -> tuple[LayoutIssue, ...]:
    """The PDF faithfully carries `layout`; `image_sizes` are each photograph's pixels."""
    issues: list[LayoutIssue] = []

    def fail(code: str, message: str) -> None:
        issues.append(LayoutIssue(code, message, physical_page=1, region="cover.pdf"))

    base, g = facts.base, layout.geometry
    if base.encrypted:
        fail("pdf_encrypted", "The cover must not be encrypted.")
    if base.page_count != 1:
        fail("pdf_page_count", f"The cover has {base.page_count} pages; it must have one.")
        return tuple(issues)
    if base.outline:
        fail("pdf_outline", "The cover contains bookmarks.")
    for key in base.interactive:
        fail("pdf_catalog", f"Unexpected catalog entry {key}.")
    if base.optional_content:
        fail("pdf_layers", "The cover contains layers.")
    page = base.pages[0]
    for name, actual, expected in (
        ("/MediaBox", page.media, g.media),
        ("/TrimBox", page.trim, g.trim),
        ("/BleedBox", page.bleed, g.media),
    ):
        if not same_box(actual, expected):
            fail("pdf_page_size", f"{name} differs from the cover geometry.")
    if page.rotation:
        fail("pdf_rotation", "The cover page is rotated.")
    if page.annotations:
        fail("pdf_annotations", "The cover contains annotations.")
    if page.transparency:
        fail("pdf_transparency", "The cover uses transparency.")
    allowed = BUNDLED_FAMILIES + layout.fonts
    for font in page.fonts:
        if not font.embedded:
            fail("font_not_embedded", f"Font {font.name} is not embedded.")
        if not _family(font.name).startswith(allowed):
            fail("font_not_bundled", f"Font {font.name} is not a bundled or imported cover font.")
    if image_sizes is not None:
        placed = len(image_sizes)
        if len(facts.images) != placed:
            fail(
                "pdf_image",
                f"The cover has {len(facts.images)} images; its layout places {placed}.",
            )
        elif sorted((i.width, i.height) for i in facts.images) != sorted(image_sizes):
            fail("pdf_image", "The embedded photographs are not the layout's pixel crops.")
        for image in facts.images:
            if image.filters != ("/DCTDecode",) or image.color_space != "/DeviceRGB":
                fail("pdf_image", "The photograph is not a DeviceRGB JPEG.")
            if PRIVATE_SEGMENTS & set(image.segments) or "INVALID" in image.segments:
                fail("pdf_metadata_leak", "The embedded photograph carries metadata segments.")
    if facts.operators & STROKE_OPERATORS:
        fail("pdf_guides", "The cover strokes paths; guides and marks are never printed.")
    if base.descriptive_metadata or facts.xmp_metadata:
        fail("pdf_metadata", "The cover carries descriptive or XMP metadata.")
    text = " ".join(page.text.split())
    compact = "".join(text.split())
    for line in layout.texts:
        # Extraction may split letter-spaced text into spaced characters.
        found = (
            "".join(line.text.split()) in compact
            if line.tracking
            else " ".join(line.text.split()) in text
        )
        if not found:
            fail("pdf_text_missing", f"Cover text {line.role!r} is missing from the PDF.")
    return tuple(issues)


def inspect_cover_pdf(
    data: bytes, layout: CoverLayout, image_sizes: tuple[tuple[int, int], ...]
) -> tuple[LayoutIssue, ...]:
    facts = read_cover_facts(data)
    if isinstance(facts, LayoutIssue):
        return (facts,)
    return cover_contract_issues(facts, layout, image_sizes)
