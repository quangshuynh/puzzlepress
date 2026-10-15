"""Authored interior styling: an optional, versioned `interior` section of book.yaml.

Styling is presentation of the printed interior. Like the cover, it is excluded
from the project build identity, so a restyled title page never changes the
plan, puzzle generation or seeds; the interior identity covers the resolved
renderer settings instead (`interior.design`). Pagination is never a style:
theme divider pages are composition (`composition.puzzles.dividers`), so they
appear in the publication plan.

The interior is black ink on white or cream paper without bleed. Tints are
percentages of black ink, panels stay inside the live area and nothing prints
to the trimmed edge. A preset names a coherent set of renderer settings; each
optional field overrides one of them. `classic` without overrides renders
exactly the interior PuzzlePress drew before styling existed.
"""

from dataclasses import dataclass, field
from enum import StrEnum

from .cover_config import CoverImage, Crop

STYLE_VERSION = 1
SUPPORTED_STYLE_VERSIONS = (1,)
MAX_DIVIDER_PHOTOS = 20
# Bounds in points (or percent of black ink). KDP's 7 pt / 0.75 pt minimums hold.
TITLE_SIZE = (18.0, 48.0)
PUZZLE_TITLE_SIZE = (16.0, 30.0)
THEME_SIZE = (9.0, 14.0)
WORD_SIZE = (10.0, 16.0)
WORD_COLUMNS = (2, 5)
GRID_FRAME = (0.75, 3.0)
CAPTION_SIZE = (8.0, 12.0)
MARK_WIDTH = (0.75, 2.0)
MUTED_INK = (35, 65)  # Percent black of unmarked letters on solution pages.
TINT = (0, 100)


class StylePreset(StrEnum):
    CLASSIC = "classic"  # The original PuzzlePress interior, unchanged.
    EDITORIAL = "editorial"  # Left-aligned headers with fine rules.
    MODERN = "modern"  # Regular-weight titles, heavier grid frames.
    HIGH_CONTRAST = "high_contrast"  # Larger words, bolder frames and solution marks.


class TitleLayout(StrEnum):
    MINIMAL = "minimal"  # Centred title, short rule, subtitle, author (the original).
    EDITORIAL = "editorial"  # Left-aligned under a full-measure rule, author at the foot.
    COLOR_BLOCK = "color_block"  # Title in a tinted block across the upper live area.
    FRAMED = "framed"  # A ruled frame inside the live area around the title page.
    PHOTO_FEATURE = "photo_feature"  # A grayscale photograph above the title.


class Align(StrEnum):
    CENTER = "center"
    LEFT = "left"


class Folio(StrEnum):
    CENTER = "center"
    OUTSIDE = "outside"


class DividerLayout(StrEnum):
    CENTERED = "centered"  # Theme title, rule, description and quote, centred.
    FRAMED = "framed"  # The same inside a ruled frame.
    BAND = "band"  # The theme title in a tinted band across the upper live area.


@dataclass(frozen=True)
class StylePhoto:
    """A photograph from cover-assets, printed in grayscale, pinned by content."""

    image: CoverImage
    crop: Crop = field(default_factory=Crop)

    def to_dict(self) -> dict[str, object]:
        return {"image": self.image.to_dict(), "crop": self.crop.to_dict()}


@dataclass(frozen=True)
class TitlePageStyle:
    layout: TitleLayout | None = None
    tint: int | None = None  # Percent black ink of the block or frame fill.
    title_size: float | None = None
    align: Align | None = None
    rule: bool | None = None
    photo: StylePhoto | None = None  # photo_feature only.

    def to_dict(self) -> dict[str, object]:
        data: dict[str, object] = {}
        for key in ("tint", "title_size", "rule"):
            value = getattr(self, key)
            if value is not None:
                data[key] = value
        if self.layout is not None:
            data["layout"] = self.layout.value
        if self.align is not None:
            data["align"] = self.align.value
        if self.photo is not None:
            data["photo"] = self.photo.to_dict()
        return data


@dataclass(frozen=True)
class PuzzlePageStyle:
    header_align: Align | None = None
    title_size: float | None = None
    title_bold: bool | None = None
    theme_label: bool | None = None
    theme_size: float | None = None
    header_rule: bool | None = None
    grid_frame: float | None = None
    word_size: float | None = None
    word_columns: int | None = None  # The most columns the word list may use.
    word_rule: bool | None = None

    def to_dict(self) -> dict[str, object]:
        data: dict[str, object] = {}
        for key in (
            "title_size",
            "title_bold",
            "theme_label",
            "theme_size",
            "header_rule",
            "grid_frame",
            "word_size",
            "word_columns",
            "word_rule",
        ):
            value = getattr(self, key)
            if value is not None:
                data[key] = value
        if self.header_align is not None:
            data["header_align"] = self.header_align.value
        return data


@dataclass(frozen=True)
class SolutionPageStyle:
    caption_size: float | None = None
    mark_width: float | None = None
    muted_ink: int | None = None  # Percent black of letters outside any solution.

    def to_dict(self) -> dict[str, object]:
        return {
            key: getattr(self, key)
            for key in ("caption_size", "mark_width", "muted_ink")
            if getattr(self, key) is not None
        }


@dataclass(frozen=True)
class DividerPhoto:
    theme: str
    photo: StylePhoto

    def to_dict(self) -> dict[str, object]:
        return {"theme": self.theme, **self.photo.to_dict()}


@dataclass(frozen=True)
class DividerStyle:
    layout: DividerLayout | None = None
    tint: int | None = None
    photos: tuple[DividerPhoto, ...] = ()

    def to_dict(self) -> dict[str, object]:
        data: dict[str, object] = {}
        if self.layout is not None:
            data["layout"] = self.layout.value
        if self.tint is not None:
            data["tint"] = self.tint
        if self.photos:
            data["photos"] = [photo.to_dict() for photo in self.photos]
        return data


@dataclass(frozen=True)
class InteriorStyle:
    version: int = STYLE_VERSION
    preset: StylePreset = StylePreset.CLASSIC
    folio: Folio | None = None
    title_page: TitlePageStyle = field(default_factory=TitlePageStyle)
    puzzle_pages: PuzzlePageStyle = field(default_factory=PuzzlePageStyle)
    solution_pages: SolutionPageStyle = field(default_factory=SolutionPageStyle)
    dividers: DividerStyle = field(default_factory=DividerStyle)

    def images(self) -> tuple[CoverImage, ...]:
        """Every photograph the style prints (title page and dividers), once each."""
        found: dict[str, CoverImage] = {}
        if self.title_page.photo is not None:
            image = self.title_page.photo.image
            found.setdefault(image.sha256 + image.path, image)
        for divider in self.dividers.photos:
            image = divider.photo.image
            found.setdefault(image.sha256 + image.path, image)
        return tuple(found.values())

    def to_dict(self) -> dict[str, object]:
        data: dict[str, object] = {"version": self.version, "preset": self.preset.value}
        if self.folio is not None:
            data["folio"] = self.folio.value
        for key in ("title_page", "puzzle_pages", "solution_pages", "dividers"):
            section = getattr(self, key).to_dict()
            if section:
                data[key] = section
        return data
