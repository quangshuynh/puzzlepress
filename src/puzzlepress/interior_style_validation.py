"""Optional interior style section, versions 1 and 2. Collects issues; never repairs."""

from enum import StrEnum
from typing import Any, TypeVar

from .content_validation import _Reader
from .cover_validation import HEX_COLOR, _bounded, _crop, _image
from .errors import ValidationIssue
from .interior_style import (
    CAPTION_SIZE,
    GRID_FRAME,
    GRID_WIDTH,
    LOOK_FIELDS,
    MARK_WIDTH,
    MAX_DIVIDER_PHOTOS,
    MAX_LABEL_TEMPLATE,
    MUTED_INK,
    PUZZLE_TITLE_SIZE,
    SUPPORTED_STYLE_VERSIONS,
    THEME_SIZE,
    TINT,
    TITLE_SIZE,
    WORD_COLUMNS,
    WORD_COLUMNS_V2,
    WORD_SIZE,
    Align,
    Background,
    Banner,
    Colors,
    Corners,
    Density,
    DividerLayout,
    DividerPhoto,
    DividerStyle,
    Folio,
    FolioStyle,
    Intensity,
    InteriorStyle,
    LetterScale,
    Look,
    Motif,
    PageLayout,
    PuzzlePageStyle,
    SolutionPageStyle,
    StylePhoto,
    StylePreset,
    Theme,
    TitleLayout,
    TitlePageStyle,
    Weight,
    WordPosition,
)

Choice = TypeVar("Choice", bound=StrEnum)
SECTIONS = {
    "version",
    "preset",
    "folio",
    "title_page",
    "puzzle_pages",
    "solution_pages",
    "dividers",
}
# Keys only version 2 accepts (and version 2 has no preset).
V2_SECTIONS = {"theme", "layout", "colors", *LOOK_FIELDS}
V2_PUZZLE_FIELDS = {
    "word_position",
    "word_align",
    "word_weight",
    "letter_scale",
    "grid_width",
    "puzzle_number",
    "answer_reference",
}
LOOK_CHOICES: dict[str, type[StrEnum]] = {
    "banner": Banner,
    "corners": Corners,
    "background": Background,
    "motif": Motif,
    "motif_intensity": Intensity,
    "density": Density,
    "folio_style": FolioStyle,
}
PAGE_PLACEHOLDER = "{page}"


def _choice(reader: _Reader, value: object, path: str, enum: type[Choice]) -> Choice | None:
    names = [member.value for member in enum]
    if not isinstance(value, str) or value not in names:
        reader.issue(path, "choice", f"Use one of: {', '.join(names)}.")
        return None
    return enum(value)


def _flag(reader: _Reader, value: object, path: str) -> bool | None:
    if not isinstance(value, bool):
        reader.issue(path, "type", "Expected true or false.")
        return None
    return value


def _integer(reader: _Reader, value: object, path: str, bounds: tuple[int, int]) -> int | None:
    if type(value) is not int or not bounds[0] <= value <= bounds[1]:
        reader.issue(path, "range", f"Expected a whole number from {bounds[0]} to {bounds[1]}.")
        return None
    return value


def _size(
    reader: _Reader, data: dict[str, object], key: str, path: str, bounds: tuple[float, float]
) -> float | None:
    if key not in data:
        return None
    return _bounded(reader, data[key], f"{path}.{key}", *bounds)


def _photo(reader: _Reader, raw: object, path: str) -> StylePhoto | None:
    data = reader.mapping(raw, path, {"image", "crop"})
    image = _image(reader, data.get("image"), f"{path}.image", "image" in data)
    crop = _crop(reader, data.get("crop", {}), f"{path}.crop")
    return None if image is None else StylePhoto(image, crop)


def _title_page(reader: _Reader, raw: object, path: str) -> TitlePageStyle:
    data = reader.mapping(raw, path, {"layout", "tint", "title_size", "align", "rule", "photo"})
    layout = (
        _choice(reader, data["layout"], f"{path}.layout", TitleLayout) if "layout" in data else None
    )
    photo = _photo(reader, data["photo"], f"{path}.photo") if "photo" in data else None
    if layout is TitleLayout.PHOTO_FEATURE and "photo" not in data:
        reader.issue(f"{path}.photo", "required", "A photo feature title page needs a photo.")
    if photo is not None and layout is not TitleLayout.PHOTO_FEATURE:
        reader.issue(
            f"{path}.photo", "not_applicable", "Only the photo_feature layout prints a photograph."
        )
    return TitlePageStyle(
        layout,
        _integer(reader, data["tint"], f"{path}.tint", TINT) if "tint" in data else None,
        _size(reader, data, "title_size", path, TITLE_SIZE),
        _choice(reader, data["align"], f"{path}.align", Align) if "align" in data else None,
        _flag(reader, data["rule"], f"{path}.rule") if "rule" in data else None,
        photo,
    )


def _template(reader: _Reader, raw: object, path: str) -> str | None:
    """Authored label text with exactly one {page} placeholder and no other braces."""
    if (
        not isinstance(raw, str)
        or not raw.strip()
        or len(raw) > MAX_LABEL_TEMPLATE
        or raw != raw.strip()
        or any(ord(c) < 32 or ord(c) == 127 or 0xD800 <= ord(c) <= 0xDFFF for c in raw)
    ):
        reader.issue(
            path,
            "text",
            f"Expected 1..{MAX_LABEL_TEMPLATE} characters on one line, without surrounding spaces.",
        )
        return None
    rest = raw.replace(PAGE_PLACEHOLDER, "", 1)
    if PAGE_PLACEHOLDER not in raw or "{" in rest or "}" in rest:
        reader.issue(
            path,
            "placeholder",
            "Write the text with {page} exactly once where the page number goes, "
            "for example: Solution on page {page}.",
        )
        return None
    return raw


def _puzzle_pages(reader: _Reader, raw: object, path: str, version: int) -> PuzzlePageStyle:
    fields = {
        "header_align",
        "title_size",
        "title_bold",
        "theme_label",
        "theme_size",
        "header_rule",
        "grid_frame",
        "word_size",
        "word_columns",
        "word_rule",
        *V2_PUZZLE_FIELDS,
    }
    data = reader.mapping(raw, path, fields)
    if version == 1:
        for key in sorted(V2_PUZZLE_FIELDS & set(data)):
            _requires_v2(reader, f"{path}.{key}")
        data = {k: v for k, v in data.items() if k not in V2_PUZZLE_FIELDS}

    def flag(key: str) -> bool | None:
        return _flag(reader, data[key], f"{path}.{key}") if key in data else None

    def choice(key: str, enum: type[Choice]) -> Choice | None:
        return _choice(reader, data[key], f"{path}.{key}", enum) if key in data else None

    columns = WORD_COLUMNS if version == 1 else WORD_COLUMNS_V2
    return PuzzlePageStyle(
        _choice(reader, data["header_align"], f"{path}.header_align", Align)
        if "header_align" in data
        else None,
        _size(reader, data, "title_size", path, PUZZLE_TITLE_SIZE),
        flag("title_bold"),
        flag("theme_label"),
        _size(reader, data, "theme_size", path, THEME_SIZE),
        flag("header_rule"),
        _size(reader, data, "grid_frame", path, GRID_FRAME),
        _size(reader, data, "word_size", path, WORD_SIZE),
        _integer(reader, data["word_columns"], f"{path}.word_columns", columns)
        if "word_columns" in data
        else None,
        flag("word_rule"),
        choice("word_position", WordPosition),
        choice("word_align", Align),
        choice("word_weight", Weight),
        choice("letter_scale", LetterScale),
        _integer(reader, data["grid_width"], f"{path}.grid_width", GRID_WIDTH)
        if "grid_width" in data
        else None,
        flag("puzzle_number"),
        _template(reader, data["answer_reference"], f"{path}.answer_reference")
        if "answer_reference" in data
        else None,
    )


def _requires_v2(reader: _Reader, path: str) -> None:
    reader.issue(path, "requires_version_2", "This setting needs interior style version 2.")


def _solution_pages(reader: _Reader, raw: object, path: str, version: int) -> SolutionPageStyle:
    data = reader.mapping(raw, path, {"caption_size", "mark_width", "muted_ink", "page_label"})
    if version == 1 and "page_label" in data:
        _requires_v2(reader, f"{path}.page_label")
        data = {k: v for k, v in data.items() if k != "page_label"}
    return SolutionPageStyle(
        _size(reader, data, "caption_size", path, CAPTION_SIZE),
        _size(reader, data, "mark_width", path, MARK_WIDTH),
        _integer(reader, data["muted_ink"], f"{path}.muted_ink", MUTED_INK)
        if "muted_ink" in data
        else None,
        _template(reader, data["page_label"], f"{path}.page_label")
        if "page_label" in data
        else None,
    )


def _dividers(reader: _Reader, raw: object, path: str) -> DividerStyle:
    data = reader.mapping(raw, path, {"layout", "tint", "photos"})
    photos: list[DividerPhoto] = []
    seen: set[str] = set()
    for index, entry in enumerate(
        reader.sequence(data.get("photos", []), f"{path}.photos", MAX_DIVIDER_PHOTOS, 0)
    ):
        item = f"{path}.photos.{index}"
        values = reader.mapping(entry, item, {"theme", "image", "crop"})
        theme = reader.text(values.get("theme"), f"{item}.theme")
        if theme in seen:
            reader.issue(f"{item}.theme", "duplicate", f"Theme {theme!r} has two photographs.")
        seen.add(theme)
        photo = _photo(reader, {k: v for k, v in values.items() if k != "theme"}, item)
        if photo is not None and theme:
            photos.append(DividerPhoto(theme, photo))
    return DividerStyle(
        _choice(reader, data["layout"], f"{path}.layout", DividerLayout)
        if "layout" in data
        else None,
        _integer(reader, data["tint"], f"{path}.tint", TINT) if "tint" in data else None,
        tuple(photos),
    )


def _colors(reader: _Reader, raw: object, path: str) -> Colors:
    data = reader.mapping(raw, path, {"accent", "secondary"})
    found: dict[str, str] = {}
    for key in ("accent", "secondary"):
        if key not in data:
            continue
        value = data[key]
        if not isinstance(value, str) or not HEX_COLOR.fullmatch(value):
            reader.issue(f"{path}.{key}", "color", "Expected a colour as #rrggbb.")
        else:
            found[key] = value
    return Colors(**found)


def validate_interior_style(
    value: object, has_composition: bool
) -> tuple[InteriorStyle | None, tuple[ValidationIssue, ...]]:
    reader = _Reader()
    path = "interior"
    data = reader.mapping(value, path, SECTIONS | V2_SECTIONS)
    if not isinstance(value, dict):
        return None, tuple(reader.issues)
    if not has_composition:
        reader.issue(path, "requires_composition", "Interior styles apply to a composed book.")
    version = data.get("version")
    if type(version) is not int or version not in SUPPORTED_STYLE_VERSIONS:
        reader.issue(
            f"{path}.version",
            "unsupported_version",
            f"Interior style version {version!r} is not supported. Supported versions: 1, 2.",
        )
        return None, tuple(reader.issues)
    if version == 1:
        for key in sorted(V2_SECTIONS & set(data)):
            _requires_v2(reader, f"{path}.{key}")
        preset = _choice(reader, data.get("preset", "classic"), f"{path}.preset", StylePreset)
    else:
        if "preset" in data:
            reader.issue(
                f"{path}.preset",
                "not_applicable",
                "Version 2 replaces the preset with a theme and a page layout.",
            )
        preset = StylePreset.CLASSIC
    folio = _choice(reader, data["folio"], f"{path}.folio", Folio) if "folio" in data else None
    v2 = data if version == 2 else {}
    theme = _choice(reader, v2.get("theme", "classic"), f"{path}.theme", Theme)
    layout = _choice(reader, v2.get("layout", "classic"), f"{path}.layout", PageLayout)
    overrides: dict[str, Any] = {
        key: _choice(reader, data[key], f"{path}.{key}", LOOK_CHOICES[key])
        for key in LOOK_FIELDS
        if version == 2 and key in data
    }
    look = Look(**overrides)
    style = InteriorStyle(
        version,
        preset or StylePreset.CLASSIC,
        folio,
        _title_page(reader, data.get("title_page", {}), f"{path}.title_page"),
        _puzzle_pages(reader, data.get("puzzle_pages", {}), f"{path}.puzzle_pages", version),
        _solution_pages(reader, data.get("solution_pages", {}), f"{path}.solution_pages", version),
        _dividers(reader, data.get("dividers", {}), f"{path}.dividers"),
        theme or Theme.CLASSIC,
        layout or PageLayout.CLASSIC,
        _colors(reader, data.get("colors", {}), f"{path}.colors") if version == 2 else Colors(),
        look,
    )
    if reader.issues:
        return None, tuple(reader.issues)
    return style, ()
