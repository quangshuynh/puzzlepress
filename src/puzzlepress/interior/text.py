"""Deterministic measured text: line construction and greedy word wrapping.

Wrapping is pure apart from font metrics, so it is testable without PDFs. It
never hyphenates, truncates or shrinks: a word wider than the measure fails.
"""

from dataclasses import dataclass

from .fonts import ASCENT, DESCENT, text_width
from .model import Anchor, Box, Face, TextLine


def text_line(
    role: str,
    text: str,
    face: Face,
    size: float,
    x: float,
    baseline: float,
    anchor: Anchor = Anchor.START,
    gray: float = 0.0,
) -> TextLine:
    width = text_width(text, face, size)
    left = {Anchor.START: x, Anchor.MIDDLE: x - width / 2, Anchor.END: x - width}[anchor]
    bounds = Box(left, baseline - DESCENT * size, width, (ASCENT + DESCENT) * size)
    return TextLine(role, text, face, size, x, baseline, anchor, bounds, gray)


@dataclass(frozen=True)
class Wrapped:
    """Lines (an empty string is a kept blank line) or the first word that cannot fit."""

    lines: tuple[str, ...]
    overflow_word: str | None = None
    overflow_width: float = 0.0


def wrap_text(text: str, face: Face, size: float, measure: float) -> Wrapped:
    """Greedy wrap preserving authored line breaks; runs of spaces become one."""
    lines: list[str] = []
    for paragraph in text.split("\n"):
        words = [word for word in paragraph.split(" ") if word]
        if not words:
            lines.append("")
            continue
        current = ""
        for word in words:
            width = text_width(word, face, size)
            if width > measure:
                return Wrapped(tuple(lines), word, width)
            candidate = f"{current} {word}" if current else word
            if current and text_width(candidate, face, size) > measure:
                lines.append(current)
                current = word
            else:
                current = candidate
        lines.append(current)
    return Wrapped(tuple(lines))
