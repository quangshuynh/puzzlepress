"""Optional interior style section, version 1. Collects independent issues; never repairs."""

from typing import TypeVar

from .content_validation import _Reader
from .cover_validation import _bounded, _crop, _image
from .errors import ValidationIssue
from .interior_style import (
    CAPTION_SIZE,
    GRID_FRAME,
    MARK_WIDTH,
    MAX_DIVIDER_PHOTOS,
    MUTED_INK,
    PUZZLE_TITLE_SIZE,
    SUPPORTED_STYLE_VERSIONS,
    THEME_SIZE,
    TINT,
    TITLE_SIZE,
    WORD_COLUMNS,
    WORD_SIZE,
    Align,
    DividerLayout,
    DividerPhoto,
    DividerStyle,
    Folio,
    InteriorStyle,
    PuzzlePageStyle,
    SolutionPageStyle,
    StylePhoto,
    StylePreset,
    TitleLayout,
    TitlePageStyle,
)

Choice = TypeVar("Choice", StylePreset, TitleLayout, Align, Folio, DividerLayout)
SECTIONS = {
    "version",
    "preset",
    "folio",
    "title_page",
    "puzzle_pages",
    "solution_pages",
    "dividers",
}


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


def _puzzle_pages(reader: _Reader, raw: object, path: str) -> PuzzlePageStyle:
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
    }
    data = reader.mapping(raw, path, fields)

    def flag(key: str) -> bool | None:
        return _flag(reader, data[key], f"{path}.{key}") if key in data else None

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
        _integer(reader, data["word_columns"], f"{path}.word_columns", WORD_COLUMNS)
        if "word_columns" in data
        else None,
        flag("word_rule"),
    )


def _solution_pages(reader: _Reader, raw: object, path: str) -> SolutionPageStyle:
    data = reader.mapping(raw, path, {"caption_size", "mark_width", "muted_ink"})
    return SolutionPageStyle(
        _size(reader, data, "caption_size", path, CAPTION_SIZE),
        _size(reader, data, "mark_width", path, MARK_WIDTH),
        _integer(reader, data["muted_ink"], f"{path}.muted_ink", MUTED_INK)
        if "muted_ink" in data
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


def validate_interior_style(
    value: object, has_composition: bool
) -> tuple[InteriorStyle | None, tuple[ValidationIssue, ...]]:
    reader = _Reader()
    path = "interior"
    data = reader.mapping(value, path, SECTIONS)
    if not isinstance(value, dict):
        return None, tuple(reader.issues)
    if not has_composition:
        reader.issue(path, "requires_composition", "Interior styles apply to a composed book.")
    version = data.get("version")
    if type(version) is not int or version not in SUPPORTED_STYLE_VERSIONS:
        reader.issue(
            f"{path}.version",
            "unsupported_version",
            f"Interior style version {version!r} is not supported. Supported versions: 1.",
        )
        return None, tuple(reader.issues)
    preset = _choice(reader, data.get("preset", "classic"), f"{path}.preset", StylePreset)
    folio = _choice(reader, data["folio"], f"{path}.folio", Folio) if "folio" in data else None
    style = InteriorStyle(
        version,
        preset or StylePreset.CLASSIC,
        folio,
        _title_page(reader, data.get("title_page", {}), f"{path}.title_page"),
        _puzzle_pages(reader, data.get("puzzle_pages", {}), f"{path}.puzzle_pages"),
        _solution_pages(reader, data.get("solution_pages", {}), f"{path}.solution_pages"),
        _dividers(reader, data.get("dividers", {}), f"{path}.dividers"),
    )
    if reader.issues:
        return None, tuple(reader.issues)
    return style, ()
