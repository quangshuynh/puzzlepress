"""Bundled print fonts: pinned digests, measurement and glyph coverage.

The production path never discovers system fonts. Each face is a Bitstream Vera
Sans file bundled in this package (redistributable; see fonts/LICENSE.txt),
checked against its SHA-256 before ReportLab registers it under a private name.
"""

import hashlib
from dataclasses import dataclass
from functools import cache
from importlib.resources import files
from pathlib import Path

from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

from .issues import InteriorError, LayoutIssue
from .model import Face


@dataclass(frozen=True)
class FontFile:
    face: Face
    file: str
    sha256: str
    pdf_name: str


FONT_FILES = (
    FontFile(
        Face.REGULAR,
        "Vera.ttf",
        "c4c45690b345435b2cba52ecabe275f05e49b389b39fe68ad03afbb551288d3d",
        "PuzzlePressSans",
    ),
    FontFile(
        Face.BOLD,
        "VeraBd.ttf",
        "cc037385e4d55bfde89b13e03091ee93bf40c0c52ddd391ff031ab276f13b8e9",
        "PuzzlePressSans-Bold",
    ),
    FontFile(
        Face.ITALIC,
        "VeraIt.ttf",
        "2adc684d518f45232c4ad1f56522f5a82a6904c31940373e1b7030beee20fb3a",
        "PuzzlePressSans-Italic",
    ),
)
# PostScript family name of the bundled faces as it appears in PDF font names.
BUNDLED_FAMILY = "BitstreamVeraSans"
# Vertical metrics shared by all three faces (hhea and the 'H' outline, 2048 units).
ASCENT = 1901 / 2048
DESCENT = 483 / 2048
CAP_HEIGHT = 1493 / 2048


def _font_path(font: FontFile) -> Path:
    return Path(str(files("puzzlepress.interior").joinpath("fonts", font.file)))


@cache
def _registered() -> dict[Face, TTFont]:
    faces: dict[Face, TTFont] = {}
    for font in FONT_FILES:
        path = _font_path(font)
        try:
            data = path.read_bytes()
        except OSError as error:
            raise InteriorError(
                "fonts", (LayoutIssue("font_invalid", f"Cannot read bundled font: {error}"),)
            ) from error
        if hashlib.sha256(data).hexdigest() != font.sha256:
            raise InteriorError(
                "fonts",
                (
                    LayoutIssue(
                        "font_invalid",
                        f"Bundled font {font.file} does not match its pinned digest.",
                        region=f"fonts.{font.face.value}",
                    ),
                ),
            )
        ttf = TTFont(font.pdf_name, str(path))
        pdfmetrics.registerFont(ttf)
        faces[font.face] = ttf
    return faces


def font_name(face: Face) -> str:
    return _registered()[face].fontName


def text_width(text: str, face: Face, size: float) -> float:
    return float(pdfmetrics.stringWidth(text, font_name(face), size))


def missing_characters(text: str, face: Face) -> tuple[str, ...]:
    """Characters the face cannot draw, in first-occurrence order."""
    mapping = _registered()[face].face.charToGlyph
    missing: list[str] = []
    for char in text:
        if char != "\n" and ord(char) not in mapping and char not in missing:
            missing.append(char)
    return tuple(missing)


def font_manifest() -> list[dict[str, str]]:
    _registered()
    return [{"face": f.face.value, "file": f.file, "sha256": f.sha256} for f in FONT_FILES]
