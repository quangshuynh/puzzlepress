"""Post-build PDF inspection with an independent parser (pypdf).

The renderer returning is not evidence of a correct file. This reopens the bytes
and checks page count, boxes, embedded fonts, absent annotations/outlines/forms,
blank pages and printed page numbers against the layout.
"""

import io

from pypdf import PdfReader
from pypdf.errors import PdfReadError
from pypdf.generic import ArrayObject, DictionaryObject

from .issues import LayoutIssue
from .model import Box, InteriorLayout

BOX_TOLERANCE = 0.01
IDENTITY_TRANSFORM = b"1 0 0 1 0 0 cm"


def inspect_pdf(data: bytes, layout: InteriorLayout) -> tuple[LayoutIssue, ...]:
    issues: list[LayoutIssue] = []

    def fail(code: str, message: str, page: int | None = None) -> None:
        issues.append(LayoutIssue(code, message, physical_page=page))

    if not data:
        fail("pdf_empty", "The renderer produced no bytes.")
        return tuple(issues)
    try:
        reader = PdfReader(io.BytesIO(data), strict=True)
        pages = list(reader.pages)
        catalog = reader.root_object
    except (PdfReadError, ValueError, KeyError, OSError) as error:
        fail("pdf_unreadable", f"The PDF does not parse: {error}")
        return tuple(issues)
    if reader.is_encrypted:
        fail("pdf_encrypted", "The interior must not be encrypted.")
    if len(pages) != len(layout.pages):
        fail(
            "pdf_page_count",
            f"PDF has {len(pages)} pages; the layout has {len(layout.pages)}.",
        )
        return tuple(issues)
    if reader.outline:
        fail("pdf_outline", "The PDF contains bookmarks.")
    for key in ("/AcroForm", "/OpenAction", "/Names"):
        if key in catalog:
            fail("pdf_catalog", f"Unexpected catalog entry {key}.")
    for number, (pdf_page, planned) in enumerate(zip(pages, layout.pages, strict=True), start=1):
        if "/Annots" in pdf_page:
            fail("pdf_annotations", "The page contains annotations.", number)
        if pdf_page.get("/Rotate", 0) != 0:
            fail("pdf_rotation", "The page is rotated.", number)
        for name, expected in (
            ("/MediaBox", planned.frame.media),
            ("/TrimBox", planned.frame.trim),
        ):
            if not _same_box(pdf_page.get(name), expected):
                fail("pdf_page_size", f"{name} differs from the layout.", number)
        resources = pdf_page.get("/Resources")
        fonts = resources.get_object().get("/Font") if resources is not None else None
        for font in fonts.get_object().values() if fonts is not None else []:
            if not _embedded(font.get_object()):
                fail("font_not_embedded", "A font on the page is not embedded.", number)
        text = pdf_page.extract_text() or ""
        if not planned.elements:
            # Font resources are shared document-wide; a blank page may carry only
            # ReportLab's identity transform and no painting operators.
            contents = pdf_page.get_contents()
            stream = contents.get_data() if contents is not None else b""
            if text.strip() or stream.replace(IDENTITY_TRANSFORM, b"").strip():
                fail("pdf_blank_page", "An intentional blank page has content.", number)
        elif planned.folio is not None and planned.folio not in text.split():
            fail("pdf_folio", "The printed page number is missing.", number)
    return tuple(issues)


def _same_box(value: object, expected: Box) -> bool:
    if not isinstance(value, ArrayObject) or len(value) != 4:
        return False
    coordinates = [float(v) for v in value]
    target = [expected.x, expected.y, expected.right, expected.top]
    return all(abs(a - b) <= BOX_TOLERANCE for a, b in zip(coordinates, target, strict=True))


def _embedded(font: DictionaryObject) -> bool:
    if font.get("/Subtype") == "/Type0":
        descendants = font.get("/DescendantFonts")
        if descendants is None:
            return False
        font = descendants.get_object()[0].get_object()
    descriptor = font.get("/FontDescriptor")
    if descriptor is None:
        return False
    descriptor = descriptor.get_object()
    return any(key in descriptor for key in ("/FontFile", "/FontFile2", "/FontFile3"))
