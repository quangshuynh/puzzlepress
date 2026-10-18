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

Version 2 replaces the preset with two independent choices: a `theme` (tones,
banners, frames, decoration, spacing and page-number treatment) and a puzzle
page `layout` (how the header, grid and word list are arranged). Accent colours
are authored as #rrggbb; on a black-ink profile Python prints each as the gray
of its luminance, so every theme has one defined monochrome rendering.
"""

from dataclasses import dataclass, field
from enum import StrEnum

from .cover_config import CoverImage, Crop

STYLE_VERSION = 2
SUPPORTED_STYLE_VERSIONS = (1, 2)
MAX_DIVIDER_PHOTOS = 20
# Bounds in points (or percent of black ink). KDP's 7 pt / 0.75 pt minimums hold.
TITLE_SIZE = (18.0, 48.0)
PUZZLE_TITLE_SIZE = (16.0, 30.0)
THEME_SIZE = (9.0, 14.0)
WORD_SIZE = (10.0, 16.0)
WORD_COLUMNS = (2, 5)
WORD_COLUMNS_V2 = (1, 5)
GRID_WIDTH = (60, 100)  # Percent of the measure a puzzle grid may use.
MAX_LABEL_TEMPLATE = 60  # Authored text around {page}, such as "Solution on page {page}".
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


class Theme(StrEnum):
    """Version 2 visual themes. `classic` is the original interior."""

    CLASSIC = "classic"
    RACING_ORANGE = "racing_orange"
    CLASSIC_GARAGE = "classic_garage"
    EDITORIAL_MINIMAL = "editorial_minimal"
    HIGH_CONTRAST = "high_contrast"
    INK_SAVER = "ink_saver"


class PageLayout(StrEnum):
    """Version 2 puzzle-page arrangements. `classic` is the original page."""

    CLASSIC = "classic"
    BOLD_HEADER = "bold_header"  # Puzzle titles in a banner, ruled off from the word list.
    CLEAN_MINIMAL = "clean_minimal"  # Left-aligned, regular weight, hairlines, more space.
    LARGE_READABILITY = "large_readability"  # Larger, bolder words and grid letters.


class Banner(StrEnum):
    NONE = "none"  # Headings print as plain text (the original).
    RULE = "rule"  # A heavy accent rule under the heading.
    OUTLINE = "outline"  # A ruled box around the heading.
    SOLID = "solid"  # A dark filled box with paper-white type.


class Corners(StrEnum):
    SQUARE = "square"
    ROUNDED = "rounded"


class Background(StrEnum):
    NONE = "none"
    HEADER_BAND = "header_band"  # A light tint behind the page header.
    FRAME = "frame"  # A ruled frame around the page content, inside the margins.


class Motif(StrEnum):
    NONE = "none"
    STRIPES = "stripes"  # Angled stripes at the outer top corner.
    CHEVRONS = "chevrons"


class Intensity(StrEnum):
    SUBTLE = "subtle"
    MEDIUM = "medium"
    BOLD = "bold"


class Density(StrEnum):
    COMPACT = "compact"
    BALANCED = "balanced"
    SPACIOUS = "spacious"


class FolioStyle(StrEnum):
    PLAIN = "plain"
    RULE = "rule"  # A short rule above the number.
    OUTLINE = "outline"  # The number in a small ruled box.


class WordPosition(StrEnum):
    BELOW = "below"
    ABOVE = "above"


class Weight(StrEnum):
    REGULAR = "regular"
    BOLD = "bold"


class LetterScale(StrEnum):
    STANDARD = "standard"
    LARGE = "large"


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
    # Version 2.
    word_position: WordPosition | None = None
    word_align: Align | None = None
    word_weight: Weight | None = None
    letter_scale: LetterScale | None = None
    grid_width: int | None = None  # Percent of the measure.
    puzzle_number: bool | None = None
    answer_reference: str | None = None  # Authored text containing {page}.

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
            "grid_width",
            "puzzle_number",
            "answer_reference",
        ):
            value = getattr(self, key)
            if value is not None:
                data[key] = value
        for key in ("header_align", "word_position", "word_align", "word_weight", "letter_scale"):
            choice = getattr(self, key)
            if choice is not None:
                data[key] = choice.value
        return data


@dataclass(frozen=True)
class SolutionPageStyle:
    caption_size: float | None = None
    mark_width: float | None = None
    muted_ink: int | None = None  # Percent black of letters outside any solution.
    page_label: str | None = None  # Version 2: authored caption text containing {page}.

    def to_dict(self) -> dict[str, object]:
        return {
            key: getattr(self, key)
            for key in ("caption_size", "mark_width", "muted_ink", "page_label")
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
class Colors:
    """Version 2 accents as #rrggbb (lowercase). None keeps the theme's colour."""

    accent: str | None = None
    secondary: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {k: v for k in ("accent", "secondary") if (v := getattr(self, k)) is not None}


LOOK_FIELDS = (
    "banner",
    "corners",
    "background",
    "motif",
    "motif_intensity",
    "density",
    "folio_style",
)


@dataclass(frozen=True)
class Look:
    """Version 2 theme overrides; None keeps the theme's value."""

    banner: Banner | None = None
    corners: Corners | None = None
    background: Background | None = None
    motif: Motif | None = None
    motif_intensity: Intensity | None = None
    density: Density | None = None
    folio_style: FolioStyle | None = None

    def to_dict(self) -> dict[str, object]:
        data: dict[str, object] = {}
        for key in LOOK_FIELDS:
            value = getattr(self, key)
            if value is not None:
                data[key] = value.value
        return data


@dataclass(frozen=True)
class InteriorStyle:
    version: int = 1
    preset: StylePreset = StylePreset.CLASSIC  # Version 1 only.
    folio: Folio | None = None
    title_page: TitlePageStyle = field(default_factory=TitlePageStyle)
    puzzle_pages: PuzzlePageStyle = field(default_factory=PuzzlePageStyle)
    solution_pages: SolutionPageStyle = field(default_factory=SolutionPageStyle)
    dividers: DividerStyle = field(default_factory=DividerStyle)
    # Version 2.
    theme: Theme = Theme.CLASSIC
    layout: PageLayout = PageLayout.CLASSIC
    colors: Colors = field(default_factory=Colors)
    look: Look = field(default_factory=Look)

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
        data: dict[str, object] = {"version": self.version}
        if self.version == 1:
            data["preset"] = self.preset.value
        else:
            data |= {"theme": self.theme.value, "layout": self.layout.value}
            colors = self.colors.to_dict()
            if colors:
                data["colors"] = colors
            data |= self.look.to_dict()
        if self.folio is not None:
            data["folio"] = self.folio.value
        for key in ("title_page", "puzzle_pages", "solution_pages", "dividers"):
            section = getattr(self, key).to_dict()
            if section:
                data[key] = section
        return data
