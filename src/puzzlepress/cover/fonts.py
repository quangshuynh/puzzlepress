"""Bundled cover fonts: pinned digests, measurement and glyph coverage.

Sans faces are the interior's Bitstream Vera Sans (same pinned files). Serif
faces are Newsreader static cuts (SIL OFL 1.1, fonts/OFL.txt), copied from
github.com/productiontype/Newsreader at commit cfcb4f7. Each file's SHA-256 is
checked before ReportLab registers it; system fonts are never consulted.
"""

import hashlib
from dataclasses import dataclass
from enum import StrEnum
from functools import cache
from importlib.resources import files
from pathlib import Path

from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

from ..interior import fonts as interior_fonts
from ..interior.issues import LayoutIssue
from ..interior.model import Face
from .issues import CoverError


class CoverFace(StrEnum):
    SANS = "sans"
    SANS_BOLD = "sans-bold"
    SANS_ITALIC = "sans-italic"
    SERIF_DISPLAY = "serif-display"
    SERIF = "serif"
    SERIF_ITALIC = "serif-italic"


_VERA = {CoverFace.SANS: Face.REGULAR, CoverFace.SANS_BOLD: Face.BOLD}
_VERA[CoverFace.SANS_ITALIC] = Face.ITALIC


@dataclass(frozen=True)
class SerifFile:
    face: CoverFace
    file: str
    sha256: str
    pdf_name: str


SERIF_FILES = (
    SerifFile(
        CoverFace.SERIF_DISPLAY,
        "Newsreader72pt-Regular.ttf",
        "fda3ed5d7dc98387a94eed6a9f1384c9d5929ff1ad6d4851e223ffe119fe95c0",
        "PuzzlePressSerifDisplay",
    ),
    SerifFile(
        CoverFace.SERIF,
        "Newsreader16pt-Regular.ttf",
        "0636887c9f72f77ce188f0b31029be58e65adae5a47e6d2887ad5020c2c75036",
        "PuzzlePressSerif",
    ),
    SerifFile(
        CoverFace.SERIF_ITALIC,
        "Newsreader16pt-Italic.ttf",
        "292646cbb948153511e308fa80def59959746d70114bd0936ba0a7f67a33181d",
        "PuzzlePressSerif-Italic",
    ),
)


def _font_path(font: SerifFile) -> Path:
    return Path(str(files("puzzlepress.cover").joinpath("fonts", font.file)))


@cache
def _serif() -> dict[CoverFace, TTFont]:
    faces: dict[CoverFace, TTFont] = {}
    for font in SERIF_FILES:
        try:
            data = _font_path(font).read_bytes()
        except OSError as error:
            raise CoverError(
                "fonts", (LayoutIssue("font_invalid", f"Cannot read bundled font: {error}"),)
            ) from error
        if hashlib.sha256(data).hexdigest() != font.sha256:
            raise CoverError(
                "fonts",
                (
                    LayoutIssue(
                        "font_invalid",
                        f"Bundled font {font.file} does not match its pinned digest.",
                        region=f"fonts.{font.face.value}",
                    ),
                ),
            )
        ttf = TTFont(font.pdf_name, str(_font_path(font)))
        pdfmetrics.registerFont(ttf)
        faces[font.face] = ttf
    return faces


def _ttf(face: CoverFace) -> TTFont:
    if face in _VERA:
        return interior_fonts._registered()[_VERA[face]]
    return _serif()[face]


def font_name(face: CoverFace) -> str:
    return _ttf(face).fontName


@dataclass(frozen=True)
class Metrics:
    ascent: float  # Per point of size.
    descent: float  # Positive, per point of size.


def metrics(face: CoverFace) -> Metrics:
    if face in _VERA:
        return Metrics(interior_fonts.ASCENT, interior_fonts.DESCENT)
    font = _serif()[face].face
    return Metrics(font.ascent / 1000, -font.descent / 1000)


def text_width(text: str, face: CoverFace, size: float) -> float:
    return float(pdfmetrics.stringWidth(text, font_name(face), size))


def missing_characters(text: str, face: CoverFace) -> tuple[str, ...]:
    mapping = _ttf(face).face.charToGlyph
    missing: list[str] = []
    for char in text:
        if char != "\n" and ord(char) not in mapping and char not in missing:
            missing.append(char)
    return tuple(missing)


def font_manifest() -> list[dict[str, str]]:
    """Every font a cover may embed, with pinned digests (part of cover identity)."""
    _serif()
    vera = {f.face: f for f in interior_fonts.FONT_FILES}
    entries = [
        {"face": face.value, "file": vera[_VERA[face]].file, "sha256": vera[_VERA[face]].sha256}
        for face in (CoverFace.SANS, CoverFace.SANS_BOLD, CoverFace.SANS_ITALIC)
    ]
    entries += [{"face": f.face.value, "file": f.file, "sha256": f.sha256} for f in SERIF_FILES]
    return entries


# PostScript family prefixes of every bundled cover face as they appear in PDFs.
BUNDLED_FAMILIES = (interior_fonts.BUNDLED_FAMILY, "Newsreader")
