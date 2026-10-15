"""Rich text for cover text boxes and the back-cover text: a bounded, versioned model.

A rich text document is a list of blocks (paragraphs or headings), each a list of
styled runs. It is structured data, never HTML: there is no markup, no CSS, no
link and nothing external. Runs choose a font family, bold, italic, underline,
size and color; blocks choose alignment, a bulleted or numbered list, line
spacing and the space before and after. Explicit line breaks are "\\n" inside a
run. Everything optional inherits from the text box or layer that holds it.

The plain text of a document (block texts joined by line breaks, list markers
left out) is what every other part of PuzzlePress reads: publishing's
confirmation identities, description checks and asset listings see the same
words whether or not they are formatted. A plain-text field becomes rich only
when an author uses formatting; nothing converts it implicitly.
"""

import math
import re
from dataclasses import dataclass, field
from enum import StrEnum

from .content_validation import _Reader

RICH_VERSION = 1
MAX_BLOCKS = 40
MAX_RUNS = 80  # Per block.
MAX_SPACING = 72.0  # Points before or after a block.
MIN_SIZE = 4.0
MAX_SIZE = 160.0
LINE_SPACING = (0.8, 3.0)
# Families a run may name; bold and italic choose the face (see cover.richtext).
BUNDLED_FAMILIES = ("sans", "serif", "serif-display")
HEX = re.compile(r"#[0-9a-fA-F]{6}")
BLOCK_FIELDS = {"type", "align", "list", "line_spacing", "space_before", "space_after", "runs"}
RUN_FIELDS = {"text", "bold", "italic", "underline", "size", "font", "color"}


class BlockType(StrEnum):
    PARAGRAPH = "paragraph"
    HEADING = "heading"


class BlockAlign(StrEnum):
    LEFT = "left"
    CENTER = "center"
    RIGHT = "right"


class ListKind(StrEnum):
    BULLET = "bullet"
    NUMBER = "number"


@dataclass(frozen=True)
class Run:
    """Text in one style. None inherits from the block or the holding text."""

    text: str
    bold: bool | None = None
    italic: bool | None = None
    underline: bool = False
    size: float | None = None
    font: str | None = None  # A bundled family or an imported font's id.
    color: str | None = None  # #rrggbb, lowercase.

    def to_dict(self) -> dict[str, object]:
        data: dict[str, object] = {"text": self.text}
        if self.bold is not None:
            data["bold"] = self.bold
        if self.italic is not None:
            data["italic"] = self.italic
        if self.underline:
            data["underline"] = True
        if self.size is not None:
            data["size"] = self.size
        if self.font is not None:
            data["font"] = self.font
        if self.color is not None:
            data["color"] = self.color
        return data

    @property
    def styled(self) -> bool:
        return self != Run(self.text)


@dataclass(frozen=True)
class Block:
    type: BlockType = BlockType.PARAGRAPH
    runs: tuple[Run, ...] = ()
    align: BlockAlign | None = None
    list: ListKind | None = None
    line_spacing: float | None = None
    space_before: float = 0.0
    space_after: float = 0.0

    @property
    def text(self) -> str:
        return "".join(run.text for run in self.runs)

    def to_dict(self) -> dict[str, object]:
        data: dict[str, object] = {}
        if self.type is not BlockType.PARAGRAPH:
            data["type"] = self.type.value
        if self.align is not None:
            data["align"] = self.align.value
        if self.list is not None:
            data["list"] = self.list.value
        if self.line_spacing is not None:
            data["line_spacing"] = self.line_spacing
        if self.space_before:
            data["space_before"] = self.space_before
        if self.space_after:
            data["space_after"] = self.space_after
        data["runs"] = [run.to_dict() for run in self.runs]
        return data


@dataclass(frozen=True)
class RichText:
    blocks: tuple[Block, ...] = field(default_factory=tuple)

    def plain(self) -> str:
        """The words, block by block on their own lines; list markers are not text."""
        return "\n".join(block.text for block in self.blocks)

    def fonts(self) -> set[str]:
        return {run.font for block in self.blocks for run in block.runs if run.font}

    def to_dict(self) -> dict[str, object]:
        return {"rich": RICH_VERSION, "blocks": [block.to_dict() for block in self.blocks]}


def is_rich(raw: object) -> bool:
    """Whether a stored value is a rich text document rather than plain text."""
    return isinstance(raw, dict) and "rich" in raw


def _flag(reader: _Reader, raw: object, path: str) -> bool | None:
    if not isinstance(raw, bool):
        reader.issue(path, "type", "Expected true or false.")
        return None
    return raw


def _number(reader: _Reader, raw: object, path: str, low: float, high: float) -> float | None:
    if not isinstance(raw, int | float) or isinstance(raw, bool) or not math.isfinite(raw):
        reader.issue(path, "number", "Expected a number.")
        return None
    value = round(float(raw), 2)
    if not low <= value <= high:
        reader.issue(path, "range", f"Expected a value from {low:g} to {high:g}.")
        return None
    return value


def _run_text(reader: _Reader, raw: object, path: str) -> str:
    if (
        not isinstance(raw, str)
        or not raw
        or any(0xD800 <= ord(c) <= 0xDFFF for c in raw)
        or any((ord(c) < 32 and c != "\n") or ord(c) == 127 for c in raw)
    ):
        reader.issue(
            path, "text", "Expected nonempty plain text; line breaks are the only control."
        )
        return ""
    return raw


def _choice(reader: _Reader, raw: object, path: str, enum: type[StrEnum]) -> str | None:
    names = [member.value for member in enum]
    if not isinstance(raw, str) or raw not in names:
        reader.issue(path, "choice", f"Use one of: {', '.join(names)}.")
        return None
    return raw


def read_rich(
    reader: _Reader, raw: object, path: str, font_ids: set[str], max_text: int
) -> RichText | None:
    """Validate a rich text document; collects issues and never repairs."""
    data = reader.mapping(raw, path, {"rich", "blocks"})
    version = data.get("rich")
    if type(version) is not int or version != RICH_VERSION:
        reader.issue(
            f"{path}.rich",
            "unsupported_version",
            f"Rich text version {version!r} is not supported. Supported versions: {RICH_VERSION}.",
        )
        return None
    before = len(reader.issues)
    blocks: list[Block] = []
    for index, entry in enumerate(
        reader.sequence(data.get("blocks"), f"{path}.blocks", MAX_BLOCKS)
    ):
        item = f"{path}.blocks.{index}"
        block = reader.mapping(entry, item, BLOCK_FIELDS)
        kind = _choice(reader, block.get("type", "paragraph"), f"{item}.type", BlockType)
        align = (
            _choice(reader, block["align"], f"{item}.align", BlockAlign)
            if "align" in block
            else None
        )
        listed = (
            _choice(reader, block["list"], f"{item}.list", ListKind) if "list" in block else None
        )
        if listed and kind == BlockType.HEADING.value:
            reader.issue(f"{item}.list", "heading_in_list", "A heading cannot be a list item.")
        spacing = (
            _number(reader, block["line_spacing"], f"{item}.line_spacing", *LINE_SPACING)
            if "line_spacing" in block
            else None
        )
        space = {
            key: _number(reader, block.get(key, 0), f"{item}.{key}", 0.0, MAX_SPACING) or 0.0
            for key in ("space_before", "space_after")
        }
        runs: list[Run] = []
        if "runs" not in block:
            reader.issue(
                f"{item}.runs",
                "required",
                "A block lists its runs (an empty list for a blank line).",
            )
        for position, value in enumerate(
            reader.sequence(block.get("runs", []), f"{item}.runs", MAX_RUNS, 0)
        ):
            run_path = f"{item}.runs.{position}"
            run = reader.mapping(value, run_path, RUN_FIELDS)
            if "text" not in run:
                reader.issue(f"{run_path}.text", "required", "A run needs its text.")
            text = _run_text(reader, run.get("text"), f"{run_path}.text")
            font = run.get("font")
            if font is not None and (
                not isinstance(font, str) or (font not in BUNDLED_FAMILIES and font not in font_ids)
            ):
                reader.issue(
                    f"{run_path}.font",
                    "unknown_font",
                    f"Use a bundled family ({', '.join(BUNDLED_FAMILIES)}) or the id of a font "
                    "in cover.fonts.",
                )
                font = None
            color = run.get("color")
            if color is not None and (not isinstance(color, str) or not HEX.fullmatch(color)):
                reader.issue(f"{run_path}.color", "color", "Use a #RRGGBB sRGB color.")
                color = None
            runs.append(
                Run(
                    text,
                    _flag(reader, run["bold"], f"{run_path}.bold") if "bold" in run else None,
                    _flag(reader, run["italic"], f"{run_path}.italic") if "italic" in run else None,
                    bool(_flag(reader, run["underline"], f"{run_path}.underline"))
                    if "underline" in run
                    else False,
                    _number(reader, run["size"], f"{run_path}.size", MIN_SIZE, MAX_SIZE)
                    if "size" in run
                    else None,
                    font if isinstance(font, str) else None,
                    color.lower() if isinstance(color, str) else None,
                )
            )
        blocks.append(
            Block(
                BlockType(kind) if kind else BlockType.PARAGRAPH,
                tuple(runs),
                BlockAlign(align) if align else None,
                ListKind(listed) if listed else None,
                spacing,
                space["space_before"],
                space["space_after"],
            )
        )
    document = RichText(tuple(blocks))
    plain = document.plain()
    if not plain.strip():
        reader.issue(f"{path}.blocks", "text", "Rich text needs at least one visible character.")
    elif len(plain) > max_text:
        reader.issue(f"{path}.blocks", "text", f"Rich text is limited to {max_text} characters.")
    return document if len(reader.issues) == before else None


def plain_equivalent(document: RichText) -> bool:
    """True when the document uses no formatting: it lays out exactly like its plain text."""
    return all(
        block.type is BlockType.PARAGRAPH
        and block.align is None
        and block.list is None
        and block.line_spacing is None
        and not block.space_before
        and not block.space_after
        and not any(run.styled for run in block.runs)
        for block in document.blocks
    )
