"""Portable interior design files: a named `interior` section, as validated JSON.

A design file carries presentation only, so one book's look can be reused in
another. It never holds book details, puzzles, composition (pagination) or
photographs: photos belong to a project's own cover-assets, so an exported design
leaves them out and an imported one keeps the receiving draft's photos. Files are
parsed as data and validated by the same schema as book.yaml; nothing in them runs.
"""

import json
from typing import Any

from .errors import ValidationIssue
from .interior_style import InteriorStyle
from .interior_style_validation import validate_interior_style

DESIGN_FORMAT = "puzzlepress-interior-design"
DESIGN_FORMAT_VERSION = 1
MAX_DESIGN_BYTES = 64 * 1024
MAX_NAME = 80
FIELDS = {"format", "format_version", "name", "interior"}


class DesignFileError(Exception):
    def __init__(self, issues: tuple[ValidationIssue, ...]) -> None:
        self.issues = issues
        super().__init__("; ".join(f"{i.path}: {i.message}" for i in issues))


def _portable(style: dict[str, Any]) -> dict[str, Any]:
    """The style without photographs (they are project assets, not design)."""
    data: dict[str, Any] = json.loads(json.dumps(style))
    title = data.get("title_page", {})
    title.pop("photo", None)
    if not title:
        data.pop("title_page", None)
    dividers = data.get("dividers", {})
    dividers.pop("photos", None)
    if not dividers:
        data.pop("dividers", None)
    return data


def _name(value: object) -> str:
    if (
        not isinstance(value, str)
        or not value.strip()
        or len(value) > MAX_NAME
        or any(ord(c) < 32 or ord(c) == 127 for c in value)
    ):
        raise DesignFileError(
            (ValidationIssue("name", "text", f"Name the design in 1..{MAX_NAME} characters."),)
        )
    return value.strip()


def export_design(style: InteriorStyle, name: object) -> bytes:
    """Canonical design-file bytes for `style` under `name` (photographs left out)."""
    document = {
        "format": DESIGN_FORMAT,
        "format_version": DESIGN_FORMAT_VERSION,
        "name": _name(name),
        "interior": _portable(style.to_dict()),
    }
    text = json.dumps(document, sort_keys=True, indent=2, ensure_ascii=False) + "\n"
    return text.encode("utf-8")


def import_design(
    data: bytes, current: InteriorStyle | None, has_composition: bool
) -> tuple[str, InteriorStyle]:
    """Validate a design file and return its name and the style for the draft.

    The receiving draft keeps its own photographs: the title photo when the
    imported design uses the photo-feature title page, and every divider photo.
    Raises DesignFileError with every issue found; never repairs a file.
    """
    if len(data) > MAX_DESIGN_BYTES:
        raise DesignFileError(
            (
                ValidationIssue(
                    "file", "too_large", f"A design file is at most {MAX_DESIGN_BYTES // 1024} KB."
                ),
            )
        )
    try:
        document = json.loads(data.decode("utf-8"))
    except (UnicodeDecodeError, ValueError) as error:
        raise DesignFileError(
            (ValidationIssue("file", "json", f"Not a JSON design file: {error}"),)
        ) from error
    if not isinstance(document, dict) or set(document) != FIELDS:
        raise DesignFileError(
            (ValidationIssue("file", "format", "Not a PuzzlePress interior design file."),)
        )
    if (
        document["format"] != DESIGN_FORMAT
        or type(document["format_version"]) is not int
        or document["format_version"] != DESIGN_FORMAT_VERSION
    ):
        raise DesignFileError(
            (
                ValidationIssue(
                    "format_version",
                    "unsupported_version",
                    f"Supported: {DESIGN_FORMAT} version {DESIGN_FORMAT_VERSION}.",
                ),
            )
        )
    name = _name(document["name"])
    interior = document["interior"]
    if not isinstance(interior, dict):
        raise DesignFileError((ValidationIssue("interior", "type", "Expected a mapping."),))
    title, dividers = interior.get("title_page", {}), interior.get("dividers", {})
    if (isinstance(title, dict) and "photo" in title) or (
        isinstance(dividers, dict) and "photos" in dividers
    ):
        raise DesignFileError(
            (
                ValidationIssue(
                    "interior",
                    "photos_not_portable",
                    "Design files never carry photographs; choose photos in this book.",
                ),
            )
        )
    merged = json.loads(json.dumps(interior))
    if current is not None:
        mine: dict[str, Any] = current.to_dict()
        photo = mine.get("title_page", {}).get("photo")
        if photo is not None and isinstance(merged.get("title_page"), dict):
            if merged["title_page"].get("layout") == "photo_feature":
                merged["title_page"]["photo"] = photo
        photos = mine.get("dividers", {}).get("photos")
        if photos:
            merged.setdefault("dividers", {})
            if isinstance(merged["dividers"], dict):
                merged["dividers"]["photos"] = photos
    style, issues = validate_interior_style(merged, has_composition)
    if style is None:
        raise DesignFileError(tuple(issues))
    return name, style
