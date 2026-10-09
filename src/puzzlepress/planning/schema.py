"""Planning document schema, version 1. Collects independent issues; never repairs.

The schema decides only whether values are interpretable: types, enumerations,
identifiers, uniqueness and generous size bounds. Everything a plan can get
wrong while still being a plan (an allocation that does not add up, a word the
generator rejects, an unknown reference, a target above a production cap) is a
planning finding instead, so an incomplete or inconsistent draft still saves and
is reported precisely. Text edges are trimmed; nothing else is rewritten.
"""

import datetime
import re
from typing import TypeVar, cast

from ..content_validation import _Reader
from ..errors import ValidationIssue
from ..wordsearch import Direction, TargetEntry, WordSearchError, normalize_targets
from .model import (
    PLANNING_VERSION,
    Claim,
    Comparable,
    Concept,
    Confidence,
    Constraints,
    Difficulty,
    Evidence,
    Familiarity,
    Level,
    Note,
    PlannedPuzzle,
    PlanningDocument,
    Pool,
    Positioning,
    Price,
    Question,
    SolutionsPlan,
    Source,
    SourceType,
    Strategy,
    Structure,
    Theme,
    Word,
    WordRange,
    WordSource,
    direction_name,
)

# Generous bounds: they keep files reasonable, not books small. Production caps
# (20 puzzles, 100 words a bank, 50-cell grids) are findings, not schema limits.
MAX_SHORT = 300
MAX_LONG = 4000
MAX_URL = 2000
MAX_COUNT = 10_000
MAX_THEMES = 200
MAX_LEVELS = 50
MAX_POOLS = 200
MAX_ENTRIES = 1000
MAX_PUZZLES = 2000
MAX_PUZZLE_WORDS = 500
MAX_ITEMS = 200  # Research notes, comparables, questions.
MAX_SMALL_LIST = 50
MAX_GRID = 999
PLANNING_IDENTITY = re.compile(r"pp1-planning-sha256-[0-9a-f]{64}")
IDENTIFIER = re.compile(r"[A-Za-z0-9_-]{1,64}")
PROFILE_ID = re.compile(r"[a-z0-9][a-z0-9.-]{0,63}")  # e.g. paperback-8.5x11
DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
AMOUNT = re.compile(r"\d{1,9}(?:\.\d{1,4})?")
CURRENCY = re.compile(r"[A-Z]{3}")
SOLUTIONS_PER_PAGE = (1, 2, 4, 6)
DIRECTIONS = {direction_name(d): d for d in Direction}

Choice = TypeVar(
    "Choice",
    Familiarity,
    Strategy,
    SolutionsPlan,
    WordSource,
    Evidence,
    Confidence,
    SourceType,
)


class _Plan(_Reader):
    """Schema helpers for planning values (paths are planning.yaml paths)."""

    def text(self, value: object, path: str, identifier: bool = False) -> str:
        """Required single-line text; identifiers use the project ID syntax."""
        if identifier:
            if not isinstance(value, str) or not IDENTIFIER.fullmatch(value.strip()):
                self.issue(path, "id", "Use 1..64 ASCII letters, digits, '_' or '-'.")
                return ""
            return value.strip()
        result = self.words(value, path, MAX_SHORT)
        return "" if result is None else result

    def words(self, value: object, path: str, limit: int, multiline: bool = False) -> str | None:
        if (
            not isinstance(value, str)
            or not value.strip()
            or len(value) > limit
            or any(
                0xD800 <= ord(c) <= 0xDFFF
                or (ord(c) < 32 and not (multiline and c == "\n"))
                or 0x7F <= ord(c) <= 0x9F
                for c in value
            )
        ):
            breaks = "; line breaks are allowed" if multiline else " on one line"
            self.issue(path, "text", f"Expected 1..{limit:,} characters of plain text{breaks}.")
            return None
        return value.strip()

    def optional(
        self, value: object, path: str, limit: int = MAX_SHORT, multiline: bool = False
    ) -> str | None:
        return None if value is None else self.words(value, path, limit, multiline)

    def long(self, value: object, path: str) -> str | None:
        return self.optional(value, path, MAX_LONG, multiline=True)

    def texts(
        self, value: object, path: str, count: int, limit: int = MAX_SHORT
    ) -> tuple[str, ...]:
        return tuple(
            text
            for i, item in enumerate(self.sequence(value, path, count, 0))
            if (text := self.words(item, f"{path}.{i}", limit)) is not None
        )

    def ids(self, value: object, path: str, count: int = MAX_SMALL_LIST) -> tuple[str, ...]:
        found = tuple(
            self.text(item, f"{path}.{i}", identifier=True)
            for i, item in enumerate(self.sequence(value, path, count, 0))
        )
        self.unique(list(found), path)
        return found

    def number(self, value: object, path: str, low: int, high: int) -> int | None:
        if value is None:
            return None
        if type(value) is not int or not low <= value <= high:
            self.issue(path, "number", f"Expected a whole number from {low} to {high}, or null.")
            return None
        return value

    def flag(self, value: object, path: str) -> bool:
        if not isinstance(value, bool):
            self.issue(path, "type", "Expected true or false.")
            return False
        return value

    def choice(self, value: object, path: str, enum: type[Choice], default: Choice) -> Choice:
        names = [member.value for member in enum]
        if not isinstance(value, str) or value not in names:
            self.issue(path, "choice", f"Use one of: {', '.join(names)}.")
            return default
        return enum(value)

    def maybe(self, value: object, path: str, enum: type[Choice]) -> Choice | None:
        if value is None:
            return None
        names = [member.value for member in enum]
        if not isinstance(value, str) or value not in names:
            self.issue(path, "choice", f"Use one of: {', '.join(names)}, or null.")
            return None
        return enum(value)

    def date(self, value: object, path: str) -> str | None:
        """An authored calendar date (YYYY-MM-DD). It is never read from a clock."""
        if value is None:
            return None
        if isinstance(value, str) and DATE.fullmatch(value.strip()):
            try:
                datetime.date.fromisoformat(value.strip())
                return value.strip()
            except ValueError:
                pass
        self.issue(path, "date", "Expected a date as YYYY-MM-DD, or null.")
        return None

    def section(self, root: dict[str, object], key: str, fields: set[str]) -> dict[str, object]:
        return self.mapping(root.get(key, {}), key, fields)

    def items(self, root: dict[str, object], key: str, count: int) -> list[tuple[str, object]]:
        return [
            (f"{key}.{i}", item)
            for i, item in enumerate(self.sequence(root.get(key, []), key, count, 0))
        ]


ROOT = {
    "planning_version",
    "concept",
    "positioning",
    "structure",
    "difficulty",
    "themes",
    "vocabulary",
    "puzzles",
    "constraints",
    "questions",
    "research",
    "comparables",
    "approval",
}


def validate_planning(value: object) -> tuple[PlanningDocument | None, tuple[ValidationIssue, ...]]:
    """Validate a decoded planning document; every issue is collected."""
    r = _Plan()
    root = r.mapping(value, "planning", ROOT)
    if not isinstance(value, dict):
        return None, tuple(r.issues)
    r.issues = [  # Root fields read as bare paths (concept.summary), not planning.concept.
        ValidationIssue(i.path.removeprefix("planning."), i.code, i.message) for i in r.issues
    ]
    version = root.get("planning_version")
    if type(version) is not int or version != PLANNING_VERSION:
        r.issue(
            "planning_version",
            "unsupported_version",
            f"Planning version {version!r} is not supported. Supported versions: "
            f"{PLANNING_VERSION}.",
        )
        return None, tuple(r.issues)
    document = PlanningDocument(
        concept=_concept(r, root),
        positioning=_positioning(r, root),
        structure=_structure(r, root),
        difficulty=_difficulty(r, root),
        themes=_themes(r, root),
        vocabulary=_vocabulary(r, root),
        puzzles=_puzzles(r, root),
        constraints=_constraints(r, root),
        questions=_questions(r, root),
        research=_research(r, root),
        comparables=_comparables(r, root),
        approval=_approval(r, root.get("approval")),
    )
    if r.issues:
        return None, tuple(r.issues)
    return document, ()


def _concept(r: _Plan, root: dict[str, object]) -> Concept:
    data = r.section(root, "concept", {"summary", "subject", "reader_experience", "scope"})
    return Concept(
        summary=r.long(data.get("summary"), "concept.summary"),
        subject=r.optional(data.get("subject"), "concept.subject"),
        reader_experience=r.long(data.get("reader_experience"), "concept.reader_experience"),
        scope=r.long(data.get("scope"), "concept.scope"),
    )


def _positioning(r: _Plan, root: dict[str, object]) -> Positioning:
    path = "positioning"
    data = r.section(
        root,
        path,
        {
            "primary_audience",
            "secondary_audience",
            "candidate_audiences",
            "familiarity",
            "tone",
            "use_case",
            "main_benefit",
            "differentiation",
            "evidence",
            "claims",
        },
    )
    claims: list[Claim] = []
    for i, raw in enumerate(
        r.sequence(data.get("claims", []), f"{path}.claims", MAX_SMALL_LIST, 0)
    ):
        item = r.mapping(raw, f"{path}.claims.{i}", {"text", "evidence"})
        text = r.words(item.get("text"), f"{path}.claims.{i}.text", MAX_SHORT)
        evidence = r.ids(item.get("evidence", []), f"{path}.claims.{i}.evidence")
        if text is not None:
            claims.append(Claim(text, evidence))
    return Positioning(
        primary_audience=r.optional(data.get("primary_audience"), f"{path}.primary_audience"),
        secondary_audience=r.optional(data.get("secondary_audience"), f"{path}.secondary_audience"),
        candidate_audiences=r.texts(
            data.get("candidate_audiences", []), f"{path}.candidate_audiences", MAX_SMALL_LIST
        ),
        familiarity=r.choice(
            data.get("familiarity", "undecided"),
            f"{path}.familiarity",
            Familiarity,
            Familiarity.UNDECIDED,
        ),
        tone=r.optional(data.get("tone"), f"{path}.tone"),
        use_case=r.long(data.get("use_case"), f"{path}.use_case"),
        main_benefit=r.long(data.get("main_benefit"), f"{path}.main_benefit"),
        differentiation=r.long(data.get("differentiation"), f"{path}.differentiation"),
        evidence=r.ids(data.get("evidence", []), f"{path}.evidence"),
        claims=tuple(claims),
    )


def _structure(r: _Plan, root: dict[str, object]) -> Structure:
    path = "structure"
    data = r.section(
        root,
        path,
        {
            "puzzle_type",
            "target_puzzles",
            "print_profile",
            "solutions",
            "solutions_per_page",
            "front_matter_pages",
            "back_matter_pages",
        },
    )
    puzzle_type = data.get("puzzle_type")
    profile = data.get("print_profile")
    per_page = data.get("solutions_per_page")
    if per_page is not None and (type(per_page) is not int or per_page not in SOLUTIONS_PER_PAGE):
        r.issue(
            f"{path}.solutions_per_page", "choice", "Use 1, 2, 4 or 6 solutions a page, or null."
        )
        per_page = None
    return Structure(
        puzzle_type=None
        if puzzle_type is None
        else r.text(puzzle_type, f"{path}.puzzle_type", identifier=True) or None,
        target_puzzles=r.number(data.get("target_puzzles"), f"{path}.target_puzzles", 1, MAX_COUNT),
        print_profile=None if profile is None else _profile_id(r, profile, f"{path}.print_profile"),
        solutions=r.choice(
            data.get("solutions", "undecided"),
            f"{path}.solutions",
            SolutionsPlan,
            SolutionsPlan.UNDECIDED,
        ),
        solutions_per_page=per_page if isinstance(per_page, int) else None,
        front_matter_pages=r.number(
            data.get("front_matter_pages"), f"{path}.front_matter_pages", 0, 100
        ),
        back_matter_pages=r.number(
            data.get("back_matter_pages"), f"{path}.back_matter_pages", 0, 100
        ),
    )


def _profile_id(r: _Plan, value: object, path: str) -> str | None:
    """A print profile ID. Whether PuzzlePress supports it is a feasibility finding."""
    if not isinstance(value, str) or not PROFILE_ID.fullmatch(value.strip()):
        r.issue(path, "id", "Use a print profile ID such as paperback-8.5x11, or null.")
        return None
    return value.strip()


def _difficulty(r: _Plan, root: dict[str, object]) -> Difficulty:
    data = r.section(root, "difficulty", {"strategy", "levels"})
    strategy = r.choice(
        data.get("strategy", "undecided"), "difficulty.strategy", Strategy, Strategy.UNDECIDED
    )
    levels: list[Level] = []
    for i, raw in enumerate(r.sequence(data.get("levels", []), "difficulty.levels", MAX_LEVELS, 0)):
        path = f"difficulty.levels.{i}"
        item = r.mapping(
            raw, path, {"id", "label", "profile", "width", "height", "directions", "words", "notes"}
        )
        profile = item.get("profile")
        raw_words = item.get("words")
        words = r.mapping(raw_words, f"{path}.words", {"min", "max"})
        low = r.number(words.get("min"), f"{path}.words.min", 1, MAX_PUZZLE_WORDS)
        high = r.number(words.get("max"), f"{path}.words.max", 1, MAX_PUZZLE_WORDS)
        if isinstance(raw_words, dict):
            if words.get("min") is None or words.get("max") is None:
                r.issue(
                    f"{path}.words", "required", "State the expected words a puzzle: min and max."
                )
            elif low is not None and high is not None and low > high:
                r.issue(f"{path}.words", "range", "The minimum word count exceeds the maximum.")
        directions: list[Direction] = []
        for j, name in enumerate(
            r.sequence(item.get("directions", []), f"{path}.directions", len(DIRECTIONS), 0)
        ):
            if not isinstance(name, str) or name not in DIRECTIONS:
                r.issue(f"{path}.directions.{j}", "direction", "Unknown direction name.")
            elif DIRECTIONS[name] in directions:
                r.issue(f"{path}.directions.{j}", "duplicate", "Each direction is listed once.")
            else:
                directions.append(DIRECTIONS[name])
        width = r.number(item.get("width"), f"{path}.width", 1, MAX_GRID)
        height = r.number(item.get("height"), f"{path}.height", 1, MAX_GRID)
        if profile is not None and (
            item.get("width") is not None or item.get("height") is not None or directions
        ):
            r.issue(
                f"{path}.profile",
                "profile_or_settings",
                "Use an existing profile or state width, height and directions, not both.",
            )
        levels.append(
            Level(
                id=r.text(item.get("id"), f"{path}.id", identifier=True),
                label=r.text(item.get("label"), f"{path}.label"),
                words=WordRange(low or 1, high or 1),
                profile=None
                if profile is None
                else r.text(profile, f"{path}.profile", identifier=True),
                width=width,
                height=height,
                # Order is not semantic: always the generator's declaration order.
                directions=tuple(d for d in Direction if d in directions),
                notes=r.long(item.get("notes"), f"{path}.notes"),
            )
        )
    r.unique([level.id for level in levels], "difficulty.levels")
    return Difficulty(strategy, tuple(levels))


def _themes(r: _Plan, root: dict[str, object]) -> tuple[Theme, ...]:
    themes: list[Theme] = []
    for path, raw in r.items(root, "themes", MAX_THEMES):
        item = r.mapping(raw, path, {"id", "label", "parent", "required", "puzzles", "notes"})
        parent = item.get("parent")
        themes.append(
            Theme(
                id=r.text(item.get("id"), f"{path}.id", identifier=True),
                label=r.text(item.get("label"), f"{path}.label"),
                parent=None
                if parent is None
                else r.text(parent, f"{path}.parent", identifier=True),
                required=r.flag(item.get("required", False), f"{path}.required"),
                puzzles=r.number(item.get("puzzles"), f"{path}.puzzles", 0, MAX_COUNT),
                notes=r.long(item.get("notes"), f"{path}.notes"),
            )
        )
    r.unique([theme.id for theme in themes], "themes")
    return tuple(themes)


def _vocabulary(r: _Plan, root: dict[str, object]) -> tuple[Pool, ...]:
    pools: list[Pool] = []
    for path, raw in r.items(root, "vocabulary", MAX_POOLS):
        item = r.mapping(raw, path, {"theme", "source", "reference", "entries"})
        entries: list[Word] = []
        for j, entry_raw in enumerate(
            r.sequence(item.get("entries", []), f"{path}.entries", MAX_ENTRIES, 0)
        ):
            entry_path = f"{path}.entries.{j}"
            entry = r.mapping(entry_raw, entry_path, {"word", "source", "reference", "note"})
            word = r.words(entry.get("word"), f"{entry_path}.word", MAX_SHORT)
            if word is None:
                continue
            entries.append(
                Word(
                    word=word,
                    source=r.maybe(entry.get("source"), f"{entry_path}.source", WordSource),
                    reference=r.optional(
                        entry.get("reference"), f"{entry_path}.reference", MAX_URL
                    ),
                    note=r.long(entry.get("note"), f"{entry_path}.note"),
                )
            )
        pools.append(
            Pool(
                theme=r.text(item.get("theme"), f"{path}.theme", identifier=True),
                entries=tuple(entries),
                source=r.choice(
                    item.get("source", "unknown"), f"{path}.source", WordSource, WordSource.UNKNOWN
                ),
                reference=r.optional(item.get("reference"), f"{path}.reference", MAX_URL),
            )
        )
    # One pool a theme: puzzles draw their words from their theme's pool.
    r.unique([pool.theme for pool in pools], "vocabulary")
    return tuple(pools)


def _puzzles(r: _Plan, root: dict[str, object]) -> tuple[PlannedPuzzle, ...]:
    puzzles: list[PlannedPuzzle] = []
    for path, raw in r.items(root, "puzzles", MAX_PUZZLES):
        item = r.mapping(raw, path, {"id", "theme", "level", "title", "words", "notes"})
        level = item.get("level")
        puzzles.append(
            PlannedPuzzle(
                id=r.text(item.get("id"), f"{path}.id", identifier=True),
                theme=r.text(item.get("theme"), f"{path}.theme", identifier=True),
                level=None if level is None else r.text(level, f"{path}.level", identifier=True),
                title=r.optional(item.get("title"), f"{path}.title"),
                words=r.texts(item.get("words", []), f"{path}.words", MAX_PUZZLE_WORDS),
                notes=r.long(item.get("notes"), f"{path}.notes"),
            )
        )
    r.unique([puzzle.id for puzzle in puzzles], "puzzles")
    return tuple(puzzles)


def _constraints(r: _Plan, root: dict[str, object]) -> Constraints:
    path = "constraints"
    data = r.section(
        root, path, {"min_letters", "max_letters", "max_word_reuse", "prohibited_words", "notes"}
    )
    low = r.number(data.get("min_letters"), f"{path}.min_letters", 1, 50)
    high = r.number(data.get("max_letters"), f"{path}.max_letters", 1, 50)
    if low is not None and high is not None and low > high:
        r.issue(path, "range", "min_letters exceeds max_letters.")
    words = r.sequence(data.get("prohibited_words", []), f"{path}.prohibited_words", 100, 0)
    prohibited: tuple[str, ...] = ()
    if words:
        # Same normalization and rules as word_search.quality.prohibited_words.
        try:
            prohibited = tuple(
                sorted(
                    t.search
                    for t in normalize_targets(
                        tuple(TargetEntry(str(i), cast(str, w)) for i, w in enumerate(words))
                    )
                )
            )
        except WordSearchError as error:
            r.engine_issues(error, path, "prohibited_words", scalar_targets=True)
    return Constraints(
        min_letters=low,
        max_letters=high,
        max_word_reuse=r.number(data.get("max_word_reuse"), f"{path}.max_word_reuse", 1, 20),
        prohibited_words=prohibited,
        notes=r.texts(data.get("notes", []), f"{path}.notes", MAX_SMALL_LIST, 1000),
    )


def _questions(r: _Plan, root: dict[str, object]) -> tuple[Question, ...]:
    questions: list[Question] = []
    for path, raw in r.items(root, "questions", MAX_ITEMS):
        item = r.mapping(raw, path, {"id", "question", "blocking", "resolution"})
        questions.append(
            Question(
                id=r.text(item.get("id"), f"{path}.id", identifier=True),
                question=r.words(item.get("question"), f"{path}.question", 1000) or "",
                blocking=r.flag(item.get("blocking", False), f"{path}.blocking"),
                resolution=r.long(item.get("resolution"), f"{path}.resolution"),
            )
        )
    r.unique([q.id for q in questions], "questions")
    return tuple(questions)


def _source(r: _Plan, value: object, path: str) -> Source:
    data = r.mapping(value if value is not None else {}, path, {"citation", "url", "type"})
    return Source(
        citation=r.optional(data.get("citation"), f"{path}.citation", 1000),
        url=r.optional(data.get("url"), f"{path}.url", MAX_URL),
        type=r.maybe(data.get("type"), f"{path}.type", SourceType),
    )


def _research(r: _Plan, root: dict[str, object]) -> tuple[Note, ...]:
    notes: list[Note] = []
    for path, raw in r.items(root, "research", MAX_ITEMS):
        item = r.mapping(
            raw,
            path,
            {
                "id",
                "question",
                "observation",
                "evidence",
                "confidence",
                "source",
                "observed",
                "relevance",
                "notes",
                "decision",
            },
        )
        question = item.get("question")
        notes.append(
            Note(
                id=r.text(item.get("id"), f"{path}.id", identifier=True),
                observation=r.words(item.get("observation"), f"{path}.observation", MAX_LONG, True)
                or "",
                evidence=r.choice(
                    item.get("evidence", "unknown"), f"{path}.evidence", Evidence, Evidence.UNKNOWN
                ),
                question=None
                if question is None
                else r.text(question, f"{path}.question", identifier=True),
                confidence=r.maybe(item.get("confidence"), f"{path}.confidence", Confidence),
                source=_source(r, item.get("source"), f"{path}.source"),
                observed=r.date(item.get("observed"), f"{path}.observed"),
                relevance=r.long(item.get("relevance"), f"{path}.relevance"),
                notes=r.long(item.get("notes"), f"{path}.notes"),
                decision=r.long(item.get("decision"), f"{path}.decision"),
            )
        )
    r.unique([note.id for note in notes], "research")
    return tuple(notes)


def _price(r: _Plan, value: object, path: str) -> Price | None:
    if value is None:
        return None
    data = r.mapping(value, path, {"amount", "currency"})
    amount, currency = data.get("amount"), data.get("currency")
    if not isinstance(amount, str) or not AMOUNT.fullmatch(amount.strip()):
        r.issue(
            f"{path}.amount", "amount", 'Write the observed amount as quoted text, e.g. "12.99".'
        )
        return None
    if not isinstance(currency, str) or not CURRENCY.fullmatch(currency.strip()):
        r.issue(f"{path}.currency", "currency", "Use a three-letter currency code such as USD.")
        return None
    return Price(amount.strip(), currency.strip())


def _comparables(r: _Plan, root: dict[str, object]) -> tuple[Comparable, ...]:
    found: list[Comparable] = []
    for path, raw in r.items(root, "comparables", MAX_ITEMS):
        item = r.mapping(
            raw,
            path,
            {
                "id",
                "title",
                "contributor",
                "url",
                "citation",
                "format",
                "trim",
                "pages",
                "puzzles",
                "price",
                "audience",
                "strengths",
                "weaknesses",
                "positioning",
                "observed",
                "evidence",
            },
        )
        found.append(
            Comparable(
                id=r.text(item.get("id"), f"{path}.id", identifier=True),
                title=r.text(item.get("title"), f"{path}.title"),
                contributor=r.optional(item.get("contributor"), f"{path}.contributor"),
                url=r.optional(item.get("url"), f"{path}.url", MAX_URL),
                citation=r.optional(item.get("citation"), f"{path}.citation", 1000),
                format=r.optional(item.get("format"), f"{path}.format"),
                trim=r.optional(item.get("trim"), f"{path}.trim"),
                pages=r.number(item.get("pages"), f"{path}.pages", 1, MAX_COUNT),
                puzzles=r.number(item.get("puzzles"), f"{path}.puzzles", 1, MAX_COUNT),
                price=_price(r, item.get("price"), f"{path}.price"),
                audience=r.optional(item.get("audience"), f"{path}.audience"),
                strengths=r.texts(
                    item.get("strengths", []), f"{path}.strengths", MAX_SMALL_LIST, 1000
                ),
                weaknesses=r.texts(
                    item.get("weaknesses", []), f"{path}.weaknesses", MAX_SMALL_LIST, 1000
                ),
                positioning=r.long(item.get("positioning"), f"{path}.positioning"),
                observed=r.date(item.get("observed"), f"{path}.observed"),
                evidence=r.choice(
                    item.get("evidence", "unknown"),
                    f"{path}.evidence",
                    Evidence,
                    Evidence.UNKNOWN,
                ),
            )
        )
    r.unique([c.id for c in found], "comparables")
    return tuple(found)


def _approval(r: _Plan, value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not PLANNING_IDENTITY.fullmatch(value):
        r.issue(
            "approval",
            "approval_identity",
            "Expected null or the planning identity you approved (pp1-planning-sha256-...). "
            "Approve in Studio or with `puzzlepress plan approve`.",
        )
        return None
    return value
