"""Schema-v1 optional composition section. Collects independent issues; never repairs."""

from typing import TypeVar

from .composition import (
    BACK_MATTER_KINDS,
    FRONT_MATTER_KINDS,
    MATTER_FIELDS,
    SOLUTIONS_PER_PAGE,
    Composition,
    MatterItem,
    MatterKind,
    NumberingScheme,
    PageNumberPolicy,
    SectionStart,
    SolutionPlacement,
    SolutionPolicy,
)
from .content_validation import _Reader
from .errors import ValidationIssue

MAX_BODY_TEXT = 2000
Choice = TypeVar("Choice", SectionStart, SolutionPlacement, NumberingScheme)


def validate_composition(
    value: object, has_puzzles: bool
) -> tuple[Composition | None, tuple[ValidationIssue, ...]]:
    """Validate composition; `has_puzzles` states whether word_search is declared."""
    reader = _Reader()
    path = "composition"
    root = reader.mapping(
        value, path, {"front_matter", "puzzles", "solutions", "back_matter", "page_numbers"}
    )
    if not isinstance(value, dict):
        return None, tuple(reader.issues)
    if not has_puzzles:
        reader.issue(
            path, "requires_puzzles", "Composition requires word_search puzzle definitions."
        )
    front = _matter(
        reader, root.get("front_matter", []), f"{path}.front_matter", FRONT_MATTER_KINDS
    )
    back = _matter(reader, root.get("back_matter", []), f"{path}.back_matter", BACK_MATTER_KINDS)
    puzzles = reader.mapping(root.get("puzzles", {}), f"{path}.puzzles", {"start"})
    puzzles_start = _choice(
        reader, puzzles.get("start", "any"), f"{path}.puzzles.start", SectionStart
    )
    solutions = _solutions(reader, root.get("solutions"), f"{path}.solutions", "solutions" in root)
    numbers = _page_numbers(reader, root.get("page_numbers", {}), f"{path}.page_numbers")
    if numbers.scheme is NumberingScheme.ROMAN_FRONT_MATTER and not front:
        reader.issue(
            f"{path}.page_numbers.scheme",
            "requires_front_matter",
            "Roman front-matter numbering requires at least one front-matter page.",
        )
    if reader.issues or solutions is None:
        return None, tuple(reader.issues)
    return Composition(solutions, tuple(front), puzzles_start, tuple(back), numbers), ()


def _choice(reader: _Reader, value: object, path: str, enum: type[Choice]) -> Choice:
    names = [member.value for member in enum]
    if not isinstance(value, str) or value not in names:
        reader.issue(path, "choice", f"Use one of: {', '.join(names)}.")
        return next(iter(enum))
    return enum(value)


def _flag(reader: _Reader, value: object, path: str) -> bool:
    if type(value) is not bool:
        reader.issue(path, "type", "Expected true or false.")
        return False
    return value


def _title(reader: _Reader, value: object, path: str) -> str:
    text = reader.text(value, path)
    if any(ord(char) < 32 or ord(char) == 127 for char in text):
        reader.issue(path, "text", "Titles are a single line without control characters.")
    return text


def _body(reader: _Reader, value: object, path: str) -> str:
    if (
        not isinstance(value, str)
        or not value.strip()
        or len(value) > MAX_BODY_TEXT
        or any(0xD800 <= ord(c) <= 0xDFFF for c in value)
        or any((ord(c) < 32 and c != "\n") or ord(c) == 127 for c in value)
    ):
        reader.issue(
            path,
            "text",
            f"Expected 1..{MAX_BODY_TEXT} characters of plain text; line breaks are allowed.",
        )
        return ""
    return value.strip()


def _matter(
    reader: _Reader, raw: object, path: str, kinds: tuple[MatterKind, ...]
) -> list[MatterItem]:
    items: list[MatterItem] = []
    seen: set[MatterKind] = set()
    for i, entry in enumerate(reader.sequence(raw, path, len(kinds), 0)):
        item_path = f"{path}.{i}"
        if not isinstance(entry, dict):
            reader.mapping(entry, item_path, set())
            continue
        raw_kind = entry.get("kind")
        if not isinstance(raw_kind, str) or raw_kind not in {kind.value for kind in kinds}:
            reader.mapping(entry, item_path, {"kind", "title", "text"})
            reader.issue(
                f"{item_path}.kind",
                "kind",
                f"Supported kinds here: {', '.join(kind.value for kind in kinds)}.",
            )
            continue
        kind = MatterKind(raw_kind)
        fields = MATTER_FIELDS[kind]
        data = reader.mapping(entry, item_path, {"kind", *fields})
        if kind in seen:
            reader.issue(f"{item_path}.kind", "duplicate_kind", f"Only one {kind.value} page.")
        seen.add(kind)
        if kind is MatterKind.TITLE_PAGE and i:
            reader.issue(item_path, "order", "The title page must be the first page.")
        title = (
            _title(reader, data.get("title"), f"{item_path}.title") if "title" in fields else None
        )
        text = _body(reader, data.get("text"), f"{item_path}.text") if "text" in fields else None
        items.append(MatterItem(kind, title, text))
    return items


def _solutions(reader: _Reader, raw: object, path: str, present: bool) -> SolutionPolicy | None:
    if not present:
        reader.issue(path, "required", "Choose a solution placement: end or omit.")
        return None
    data = reader.mapping(raw, path, {"placement", "title", "per_page", "start"})
    placement = _choice(reader, data.get("placement"), f"{path}.placement", SolutionPlacement)
    if placement is SolutionPlacement.OMIT:
        for key in sorted({"title", "per_page", "start"} & set(data)):
            reader.issue(
                f"{path}.{key}", "not_applicable", "Only applies when solutions are placed."
            )
        return SolutionPolicy(placement)
    title = _title(reader, data.get("title"), f"{path}.title")
    per_page = data.get("per_page", 1)
    if type(per_page) is not int or per_page not in SOLUTIONS_PER_PAGE:
        reader.issue(
            f"{path}.per_page",
            "choice",
            f"Use one of: {', '.join(map(str, SOLUTIONS_PER_PAGE))}.",
        )
        per_page = 1
    start = _choice(reader, data.get("start", "any"), f"{path}.start", SectionStart)
    return SolutionPolicy(placement, title, per_page, start)


def _page_numbers(reader: _Reader, raw: object, path: str) -> PageNumberPolicy:
    data = reader.mapping(
        raw, path, {"scheme", "show_front_matter", "show_solutions", "show_back_matter"}
    )
    defaults = PageNumberPolicy()
    scheme = data.get("scheme", defaults.scheme.value)
    return PageNumberPolicy(
        _choice(reader, scheme, f"{path}.scheme", NumberingScheme),
        _flag(reader, data.get("show_front_matter", False), f"{path}.show_front_matter"),
        _flag(reader, data.get("show_solutions", True), f"{path}.show_solutions"),
        _flag(reader, data.get("show_back_matter", True), f"{path}.show_back_matter"),
    )
