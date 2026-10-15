"""Resolved interior design: the renderer settings an interior style stands for.

A preset is a named, versioned set of these values; an authored style replaces
individual values. The layout engine reads only this object, so what a preset
means is defined once, here, and enters the interior identity in full. The
`classic` settings are exactly the constants the renderer used before styles
existed, and with no style the engine draws byte-identical interiors.
"""

from dataclasses import asdict, dataclass, replace
from typing import Any

from ..interior_style import (
    Align,
    DividerLayout,
    Folio,
    InteriorStyle,
    StylePhoto,
    StylePreset,
    TitleLayout,
)

# Bump when what a preset or a setting draws changes for identical settings.
DESIGN_VERSION = 1


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

    def to_dict(self) -> dict[str, object]:
        return {"design_version": DESIGN_VERSION, **asdict(self)}


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


def resolve_design(style: InteriorStyle | None) -> InteriorDesign:
    """The renderer settings for `style`; None (no interior section) is classic."""
    if style is None:
        return CLASSIC
    design = PRESETS[style.preset]
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
