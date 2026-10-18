"""Resolved interior design: the renderer settings an interior style stands for.

A preset is a named, versioned set of these values; an authored style replaces
individual values. The layout engine reads only this object, so what a preset
means is defined once, here, and enters the interior identity in full. The
`classic` settings are exactly the constants the renderer used before styles
existed, and with no style the engine draws byte-identical interiors.

Version 2 styles resolve a theme, then a page layout, then the author's
overrides into a `Look`. The classic theme with the classic layout draws the
same pages as no style at all.
"""

from dataclasses import asdict, dataclass, field, replace
from typing import Any

from ..interior_style import (
    Align,
    Background,
    Banner,
    Corners,
    Density,
    DividerLayout,
    Folio,
    FolioStyle,
    Intensity,
    InteriorStyle,
    LetterScale,
    Motif,
    PageLayout,
    StylePhoto,
    StylePreset,
    Theme,
    TitleLayout,
    Weight,
    WordPosition,
)

# Bump when what a preset or a setting draws changes for identical settings.
DESIGN_VERSION = 1
# Bump when what a version 2 theme, layout or look setting draws changes.
LOOK_VERSION = 1
LETTER_RATIOS = {LetterScale.STANDARD.value: 0.56, LetterScale.LARGE.value: 0.64}


def print_gray(color: str) -> float:
    """DeviceGray a #rrggbb colour prints as in black ink: its Rec. 601 luminance."""
    red, green, blue = (int(color[i : i + 2], 16) for i in (1, 3, 5))
    return round((0.299 * red + 0.587 * green + 0.114 * blue) / 255, 3)


@dataclass(frozen=True)
class Look:
    """Resolved version 2 settings. The defaults draw the original pages."""

    theme: str = Theme.CLASSIC.value
    layout: str = PageLayout.CLASSIC.value
    accent: str = "#000000"
    secondary: str = "#000000"
    accent_gray: float = 0.0  # What `accent` prints as on black ink.
    secondary_gray: float = 0.0
    banner: str = Banner.NONE.value  # Section headings (solutions, dividers).
    title_banner: bool = False  # Puzzle titles in a banner of the theme's style.
    corners: str = Corners.SQUARE.value
    background: str = Background.NONE.value
    motif: str = Motif.NONE.value
    motif_intensity: str = Intensity.MEDIUM.value
    density: str = Density.BALANCED.value
    folio_style: str = FolioStyle.PLAIN.value
    accent_labels: bool = False  # Theme labels and puzzle numbers in the accent tone.
    word_position: str = WordPosition.BELOW.value
    word_align: str = Align.CENTER.value
    word_weight: str = Weight.REGULAR.value
    word_leading: float = 1.5
    letter_scale: str = LetterScale.STANDARD.value
    grid_width: int = 100
    puzzle_number: bool = False
    answer_reference: str | None = None
    page_label: str | None = None

    @property
    def letter_ratio(self) -> float:
        return LETTER_RATIOS[self.letter_scale]

    def to_dict(self) -> dict[str, object]:
        return {"look_version": LOOK_VERSION, **asdict(self)}


@dataclass(frozen=True)
class InteriorDesign:
    # Every default is the original renderer's value (MUTED_GRAY is 0.55, and so on).
    preset: str = StylePreset.CLASSIC.value
    folio: str | None = None  # center or outside; None keeps the print profile's choice.
    # Title page.
    title_layout: str = TitleLayout.MINIMAL.value
    title_tint: int = 0  # Percent black ink.
    title_size: float | None = None  # None: the profile's title size.
    title_align: str = Align.CENTER.value
    title_rule: bool = True
    # Puzzle pages.
    header_align: str = Align.CENTER.value
    puzzle_title_size: float | None = None  # None: the profile's size.
    puzzle_title_bold: bool = True
    theme_label: bool = True
    theme_size: float | None = None
    header_rule: bool = False
    grid_frame: float | None = None  # None: the profile's grid frame stroke.
    word_size: float | None = None
    word_columns: int = 5
    word_rule: bool = False
    # Solution pages.
    caption_size: float | None = None
    mark_width: float | None = None
    muted_gray: float = 0.55  # DeviceGray of letters outside any solution (0.55 = 45% ink).
    # Theme dividers.
    divider_layout: str = DividerLayout.CENTERED.value
    divider_tint: int = 0
    # Version 2 only; None (version 1 and no style) is the original renderer.
    look: Look | None = field(default=None, compare=True)

    def to_dict(self) -> dict[str, object]:
        data = asdict(self)
        del data["look"]
        if self.look is not None:
            data["look"] = self.look.to_dict()
        return {"design_version": DESIGN_VERSION, **data}


CLASSIC = InteriorDesign()
PRESETS: dict[StylePreset, InteriorDesign] = {
    StylePreset.CLASSIC: CLASSIC,
    StylePreset.EDITORIAL: InteriorDesign(
        preset=StylePreset.EDITORIAL.value,
        folio=Folio.OUTSIDE.value,
        title_layout=TitleLayout.EDITORIAL.value,
        title_align=Align.LEFT.value,
        header_align=Align.LEFT.value,
        header_rule=True,
        grid_frame=0.75,
        word_size=12.5,
        word_columns=4,
        word_rule=True,
        divider_layout=DividerLayout.CENTERED.value,
    ),
    StylePreset.MODERN: InteriorDesign(
        preset=StylePreset.MODERN.value,
        title_layout=TitleLayout.FRAMED.value,
        title_size=34.0,
        puzzle_title_size=24.0,
        puzzle_title_bold=False,
        theme_size=11.0,
        grid_frame=1.5,
        word_columns=4,
        mark_width=1.25,
        divider_layout=DividerLayout.FRAMED.value,
    ),
    StylePreset.HIGH_CONTRAST: InteriorDesign(
        preset=StylePreset.HIGH_CONTRAST.value,
        title_layout=TitleLayout.FRAMED.value,
        title_size=36.0,
        puzzle_title_size=24.0,
        grid_frame=2.0,
        word_size=14.0,
        word_columns=4,
        caption_size=10.0,
        mark_width=1.5,
        muted_gray=0.62,
        divider_layout=DividerLayout.BAND.value,
        divider_tint=70,
    ),
}


# What a title layout implies when the author chooses it but not these settings.
LAYOUT_DEFAULTS: dict[TitleLayout, dict[str, object]] = {
    TitleLayout.EDITORIAL: {"title_align": Align.LEFT.value},
    TitleLayout.COLOR_BLOCK: {"title_tint": 85},
}


@dataclass(frozen=True)
class ThemeSpec:
    """A version 2 theme: its look and the renderer settings it implies."""

    name: str
    description: str
    look: dict[str, object]
    design: dict[str, object]


THEMES: dict[Theme, ThemeSpec] = {
    Theme.CLASSIC: ThemeSpec("Classic", "The original PuzzlePress interior.", {}, {}),
    Theme.RACING_ORANGE: ThemeSpec(
        "Racing Orange",
        "Black banners, orange accents, crisp rounded frames and angled stripes.",
        {
            "accent": "#e8590c",
            "secondary": "#141414",
            "banner": Banner.SOLID.value,
            "corners": Corners.ROUNDED.value,
            "motif": Motif.STRIPES.value,
            "folio_style": FolioStyle.RULE.value,
            "accent_labels": True,
        },
        {
            "grid_frame": 1.5,
            "mark_width": 1.25,
            "divider_layout": DividerLayout.BAND.value,
            "divider_tint": 85,  # The band default: dark enough for paper-white type.
        },
    ),
    Theme.CLASSIC_GARAGE: ThemeSpec(
        "Classic Garage",
        "Warm, muted accents, outlined banners, a ruled page frame and small chevrons.",
        {
            "accent": "#8c5a2b",
            "secondary": "#3b3b3b",
            "banner": Banner.OUTLINE.value,
            "corners": Corners.ROUNDED.value,
            "background": Background.FRAME.value,
            "motif": Motif.CHEVRONS.value,
            "motif_intensity": Intensity.SUBTLE.value,
            "folio_style": FolioStyle.OUTLINE.value,
            "accent_labels": True,
        },
        # The page frame already frames dividers; a second frame inside it is clutter.
        {"grid_frame": 1.25, "divider_layout": DividerLayout.CENTERED.value},
    ),
    Theme.EDITORIAL_MINIMAL: ThemeSpec(
        "Editorial Minimal",
        "Clean rules, neutral tones, left-aligned headers and generous spacing.",
        {
            "accent": "#5c5c5c",
            "secondary": "#222222",
            "banner": Banner.RULE.value,
            "density": Density.SPACIOUS.value,
        },
        {
            "folio": Folio.OUTSIDE.value,
            "header_align": Align.LEFT.value,
            "grid_frame": 0.75,
            "divider_layout": DividerLayout.CENTERED.value,
        },
    ),
    Theme.HIGH_CONTRAST: ThemeSpec(
        "High Contrast",
        "Black on white with solid banners, heavy frames and no decoration.",
        {"banner": Banner.SOLID.value, "word_weight": Weight.BOLD.value},
        {
            "grid_frame": 2.0,
            "mark_width": 1.5,
            "muted_gray": 0.62,
            "caption_size": 10.0,
            "divider_layout": DividerLayout.BAND.value,
            "divider_tint": 70,
        },
    ),
    Theme.INK_SAVER: ThemeSpec(
        "Ink Saver",
        "White pages, thin outlines and no fills or decoration, to keep ink light.",
        {
            "accent": "#4d4d4d",
            "secondary": "#4d4d4d",
            "banner": Banner.OUTLINE.value,
            "corners": Corners.ROUNDED.value,
        },
        {"grid_frame": 0.75, "divider_layout": DividerLayout.CENTERED.value},
    ),
}


@dataclass(frozen=True)
class LayoutSpec:
    name: str
    description: str
    look: dict[str, object]
    design: dict[str, object]


LAYOUTS: dict[PageLayout, LayoutSpec] = {
    PageLayout.CLASSIC: LayoutSpec(
        "Classic", "Centred title and theme, the grid, then the word list.", {}, {}
    ),
    PageLayout.BOLD_HEADER: LayoutSpec(
        "Bold Header",
        "The puzzle title in a banner, a rule between the grid and the word list.",
        {"title_banner": True},
        {"puzzle_title_size": 24.0, "word_rule": True, "header_rule": False},
    ),
    PageLayout.CLEAN_MINIMAL: LayoutSpec(
        "Clean Minimal",
        "Left-aligned regular-weight title over a hairline, more white space.",
        {"density": Density.SPACIOUS.value},
        {
            "header_align": Align.LEFT.value,
            "puzzle_title_bold": False,
            "header_rule": True,
            "word_columns": 4,
        },
    ),
    PageLayout.LARGE_READABILITY: LayoutSpec(
        "Large Readability",
        "Larger, bolder words in fewer columns and larger grid letters.",
        {
            "word_weight": Weight.BOLD.value,
            "letter_scale": LetterScale.LARGE.value,
            "word_leading": 1.6,
        },
        {
            "word_size": 15.0,
            "word_columns": 3,
            "puzzle_title_size": 26.0,
            "theme_size": 13.0,
            "caption_size": 11.0,
        },
    ),
}


def _resolve_look(style: InteriorStyle) -> tuple[Look, dict[str, object]]:
    """The version 2 look and the renderer settings the theme and layout imply."""
    theme, layout = THEMES[style.theme], LAYOUTS[style.layout]
    values: dict[str, object] = {"theme": style.theme.value, "layout": style.layout.value}
    values |= theme.look | layout.look
    values |= style.colors.to_dict() | style.look.to_dict()
    puzzles = style.puzzle_pages
    for key in ("word_position", "word_align", "word_weight", "letter_scale"):
        choice = getattr(puzzles, key)
        if choice is not None:
            values[key] = choice.value
    for key in ("grid_width", "puzzle_number", "answer_reference"):
        if getattr(puzzles, key) is not None:
            values[key] = getattr(puzzles, key)
    if style.solution_pages.page_label is not None:
        values["page_label"] = style.solution_pages.page_label
    look = Look(**values)  # type: ignore[arg-type]
    look = replace(
        look, accent_gray=print_gray(look.accent), secondary_gray=print_gray(look.secondary)
    )
    return look, theme.design | layout.design


def resolve_design(style: InteriorStyle | None) -> InteriorDesign:
    """The renderer settings for `style`; None (no interior section) is classic."""
    if style is None:
        return CLASSIC
    design = PRESETS[style.preset]
    if style.version >= 2:
        look, implied = _resolve_look(style)
        design = replace(design, look=look, **implied)  # type: ignore[arg-type]
    chosen = style.title_page.layout
    if chosen is not None and chosen.value != design.title_layout:
        design = replace(design, **LAYOUT_DEFAULTS.get(chosen, {}))  # type: ignore[arg-type]
    title, puzzles = style.title_page, style.puzzle_pages
    solutions, dividers = style.solution_pages, style.dividers
    changes: dict[str, Any] = {
        "folio": style.folio.value if style.folio else None,
        "title_layout": title.layout.value if title.layout else None,
        "title_tint": title.tint,
        "title_size": title.title_size,
        "title_align": title.align.value if title.align else None,
        "title_rule": title.rule,
        "header_align": puzzles.header_align.value if puzzles.header_align else None,
        "puzzle_title_size": puzzles.title_size,
        "puzzle_title_bold": puzzles.title_bold,
        "theme_label": puzzles.theme_label,
        "theme_size": puzzles.theme_size,
        "header_rule": puzzles.header_rule,
        "grid_frame": puzzles.grid_frame,
        "word_size": puzzles.word_size,
        "word_columns": puzzles.word_columns,
        "word_rule": puzzles.word_rule,
        "caption_size": solutions.caption_size,
        "mark_width": solutions.mark_width,
        "muted_gray": None if solutions.muted_ink is None else 1 - solutions.muted_ink / 100,
        "divider_layout": dividers.layout.value if dividers.layout else None,
        "divider_tint": dividers.tint,
    }
    return replace(design, **{k: v for k, v in changes.items() if v is not None})


@dataclass(frozen=True)
class StyleImages:
    """Photographs a style prints, by where they print: the title page and themes."""

    title: StylePhoto | None = None
    themes: tuple[tuple[str, StylePhoto], ...] = ()

    def theme(self, name: str) -> StylePhoto | None:
        return dict(self.themes).get(name)


def style_images(style: InteriorStyle | None) -> StyleImages:
    if style is None:
        return StyleImages()
    title = style.title_page.photo
    layout = resolve_design(style).title_layout
    return StyleImages(
        title if layout == TitleLayout.PHOTO_FEATURE.value else None,
        tuple((d.theme, d.photo) for d in style.dividers.photos),
    )


def style_inputs(style: InteriorStyle | None) -> dict[str, object] | None:
    """What the interior identity records for a style (None without one).

    The resolved settings plus each photograph by SHA-256 and crop, never paths.
    """
    if style is None:
        return None
    images = style_images(style)

    def photo(value: StylePhoto) -> dict[str, object]:
        return {"sha256": value.image.sha256, "crop": value.crop.to_dict()}

    return {
        "design": resolve_design(style).to_dict(),
        "title_photo": None if images.title is None else photo(images.title),
        "divider_photos": [{"theme": t, **photo(p)} for t, p in images.themes],
    }


def design_catalogue() -> dict[str, object]:
    """Built-in themes and page layouts with what each sets, for Studio to present."""

    def look_of(values: dict[str, object]) -> dict[str, object]:
        look = replace(Look(), **values)  # type: ignore[arg-type]
        look = replace(
            look, accent_gray=print_gray(look.accent), secondary_gray=print_gray(look.secondary)
        )
        return look.to_dict()

    return {
        "themes": [
            {
                "id": key.value,
                "name": spec.name,
                "description": spec.description,
                "look": look_of(spec.look),
                "design": spec.design,
            }
            for key, spec in THEMES.items()
        ],
        "layouts": [
            {
                "id": key.value,
                "name": spec.name,
                "description": spec.description,
                "look": spec.look,
                "design": spec.design,
            }
            for key, spec in LAYOUTS.items()
        ],
    }
