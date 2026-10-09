"""The book-planning document: an authored, versioned blueprint beside book.yaml.

A plan records what an author intends to make and why, before production:
concept, audience and positioning, structure, difficulty levels, themes,
candidate vocabulary, planned puzzles, content constraints, open questions,
research notes and comparable books. It is authored source, not production
content: nothing here generates puzzles or changes book.yaml, and no field
counts as verified because PuzzlePress read it. Unknown values stay explicit
(`None`, `undecided`, `unknown`) and never default to a claim.

Values are immutable and normalized by `planning.schema`. `to_dict` is the
canonical source representation, in document order, used for saving and for
the planning identity.
"""

from dataclasses import dataclass, field
from enum import StrEnum

from ..wordsearch import Direction

PLANNING_VERSION = 1
PLANNING_FILE = "planning.yaml"


class Familiarity(StrEnum):
    """How much the intended reader already knows about the subject."""

    UNDECIDED = "undecided"
    NEWCOMER = "newcomer"
    CASUAL = "casual"
    ENTHUSIAST = "enthusiast"
    PROFESSIONAL = "professional"
    MIXED = "mixed"


class Strategy(StrEnum):
    """How difficulty should develop through the book, as the author intends it."""

    UNDECIDED = "undecided"
    CONSISTENT = "consistent"  # Every puzzle uses one level.
    GRADUAL = "gradual"  # Levels never step back along the book.
    SECTIONS = "sections"  # Each level forms one contiguous section.
    MIXED = "mixed"  # Levels vary freely.


class SolutionsPlan(StrEnum):
    UNDECIDED = "undecided"
    END = "end"
    OMIT = "omit"


class WordSource(StrEnum):
    """Where a candidate word came from, as the author records it.

    A source records origin only. It never implies permission: a URL does not
    grant rights, and a generic term is not proprietary because a commercial
    source uses it. AI-generated words are never treated as human-authored.
    """

    UNKNOWN = "unknown"
    HUMAN = "human"
    PUBLIC_REFERENCE = "public_reference"
    LICENSED = "licensed"
    AI_ASSISTED = "ai_assisted"
    AI_GENERATED = "ai_generated"


class Evidence(StrEnum):
    """What kind of statement a research note or comparable record is.

    `verified_source` means the author states they checked the cited source.
    PuzzlePress never fetches sources and verifies nothing itself.
    """

    UNKNOWN = "unknown"
    VERIFIED_SOURCE = "verified_source"
    UNVERIFIED_SOURCE = "unverified_source"
    AUTHOR_OBSERVATION = "author_observation"
    HYPOTHESIS = "hypothesis"
    PREFERENCE = "preference"


# Evidence a decision should not rest on alone. A preference is a legitimate
# basis for the author's own decisions, but never support for a claim.
WEAK_EVIDENCE = frozenset({Evidence.UNKNOWN, Evidence.HYPOTHESIS})
# Evidence that names an outside source and so must cite it.
SOURCED_EVIDENCE = frozenset({Evidence.VERIFIED_SOURCE, Evidence.UNVERIFIED_SOURCE})


class Confidence(StrEnum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class SourceType(StrEnum):
    OFFICIAL = "official"  # Official documentation, e.g. a printer's help pages.
    REFERENCE = "reference"  # Dictionaries, encyclopedias, technical references.
    MARKETPLACE = "marketplace"  # A store listing, read by a person.
    PUBLISHER = "publisher"
    BOOK = "book"
    ARTICLE = "article"
    PERSONAL = "personal"  # The author's own experience.
    OTHER = "other"


def _optional(value: StrEnum | None) -> str | None:
    return None if value is None else value.value


def direction_name(direction: Direction) -> str:
    return direction.name.lower().replace("_", "-")


@dataclass(frozen=True)
class Concept:
    summary: str | None = None
    subject: str | None = None
    reader_experience: str | None = None
    scope: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "summary": self.summary,
            "subject": self.subject,
            "reader_experience": self.reader_experience,
            "scope": self.scope,
        }


@dataclass(frozen=True)
class Claim:
    """A statement the author intends to make about the book in its positioning."""

    text: str
    evidence: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {"text": self.text, "evidence": list(self.evidence)}


@dataclass(frozen=True)
class Positioning:
    primary_audience: str | None = None
    secondary_audience: str | None = None
    candidate_audiences: tuple[str, ...] = ()  # Considered, not validated.
    familiarity: Familiarity = Familiarity.UNDECIDED
    tone: str | None = None
    use_case: str | None = None
    main_benefit: str | None = None
    differentiation: str | None = None
    evidence: tuple[str, ...] = ()  # Research note IDs this positioning relies on.
    claims: tuple[Claim, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {
            "primary_audience": self.primary_audience,
            "secondary_audience": self.secondary_audience,
            "candidate_audiences": list(self.candidate_audiences),
            "familiarity": self.familiarity.value,
            "tone": self.tone,
            "use_case": self.use_case,
            "main_benefit": self.main_benefit,
            "differentiation": self.differentiation,
            "evidence": list(self.evidence),
            "claims": [claim.to_dict() for claim in self.claims],
        }


@dataclass(frozen=True)
class Structure:
    """The planned book's shape. Print values name print profiles; nothing is inferred."""

    puzzle_type: str | None = None
    target_puzzles: int | None = None
    print_profile: str | None = None
    solutions: SolutionsPlan = SolutionsPlan.UNDECIDED
    solutions_per_page: int | None = None
    front_matter_pages: int | None = None
    back_matter_pages: int | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "puzzle_type": self.puzzle_type,
            "target_puzzles": self.target_puzzles,
            "print_profile": self.print_profile,
            "solutions": self.solutions.value,
            "solutions_per_page": self.solutions_per_page,
            "front_matter_pages": self.front_matter_pages,
            "back_matter_pages": self.back_matter_pages,
        }


@dataclass(frozen=True)
class WordRange:
    min: int
    max: int

    def to_dict(self) -> dict[str, object]:
        return {"min": self.min, "max": self.max}


@dataclass(frozen=True)
class Level:
    """A planned difficulty level: an existing project profile or explicit settings.

    Settings use the generator's own vocabulary (grid, directions) plus the word
    count the author expects. Their order in the plan is the author's declared
    order from easiest to hardest; PuzzlePress does not measure difficulty.
    """

    id: str
    label: str
    words: WordRange
    profile: str | None = None
    width: int | None = None
    height: int | None = None
    directions: tuple[Direction, ...] = ()
    notes: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "label": self.label,
            "profile": self.profile,
            "width": self.width,
            "height": self.height,
            "directions": [direction_name(d) for d in self.directions],
            "words": self.words.to_dict(),
            "notes": self.notes,
        }


@dataclass(frozen=True)
class Difficulty:
    strategy: Strategy = Strategy.UNDECIDED
    levels: tuple[Level, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {
            "strategy": self.strategy.value,
            "levels": [level.to_dict() for level in self.levels],
        }


@dataclass(frozen=True)
class Theme:
    id: str
    label: str
    parent: str | None = None
    required: bool = False
    puzzles: int | None = None  # Planned puzzle allocation; None means not decided.
    notes: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "label": self.label,
            "parent": self.parent,
            "required": self.required,
            "puzzles": self.puzzles,
            "notes": self.notes,
        }


@dataclass(frozen=True)
class Word:
    """A candidate word or phrase exactly as authored. Validity is a finding."""

    word: str
    source: WordSource | None = None  # None: the pool's source applies.
    reference: str | None = None
    note: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "word": self.word,
            "source": _optional(self.source),
            "reference": self.reference,
            "note": self.note,
        }


@dataclass(frozen=True)
class Pool:
    """Candidate vocabulary for one theme. Entries keep their authored order."""

    theme: str
    entries: tuple[Word, ...] = ()
    source: WordSource = WordSource.UNKNOWN
    reference: str | None = None

    def source_of(self, entry: Word) -> WordSource:
        return entry.source if entry.source is not None else self.source

    def to_dict(self) -> dict[str, object]:
        return {
            "theme": self.theme,
            "source": self.source.value,
            "reference": self.reference,
            "entries": [entry.to_dict() for entry in self.entries],
        }


@dataclass(frozen=True)
class PlannedPuzzle:
    """One planned puzzle, in book order. Words are entries of its theme's pool."""

    id: str
    theme: str
    level: str | None = None
    title: str | None = None
    words: tuple[str, ...] = ()
    notes: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "theme": self.theme,
            "level": self.level,
            "title": self.title,
            "words": list(self.words),
            "notes": self.notes,
        }


@dataclass(frozen=True)
class Constraints:
    min_letters: int | None = None
    max_letters: int | None = None
    max_word_reuse: int | None = None  # None: the word-search quality default applies.
    # Normalized search forms, sorted, as in word_search.quality.prohibited_words.
    prohibited_words: tuple[str, ...] = ()
    notes: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {
            "min_letters": self.min_letters,
            "max_letters": self.max_letters,
            "max_word_reuse": self.max_word_reuse,
            "prohibited_words": list(self.prohibited_words),
            "notes": list(self.notes),
        }


@dataclass(frozen=True)
class Question:
    id: str
    question: str
    blocking: bool = False  # Must be resolved before the plan can be approved.
    resolution: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "question": self.question,
            "blocking": self.blocking,
            "resolution": self.resolution,
        }


@dataclass(frozen=True)
class Source:
    citation: str | None = None
    url: str | None = None
    type: SourceType | None = None

    @property
    def cited(self) -> bool:
        return self.citation is not None or self.url is not None

    def to_dict(self) -> dict[str, object]:
        return {"citation": self.citation, "url": self.url, "type": _optional(self.type)}


@dataclass(frozen=True)
class Note:
    """One research notebook entry: an observation and what kind of statement it is."""

    id: str
    observation: str
    evidence: Evidence = Evidence.UNKNOWN
    question: str | None = None
    confidence: Confidence | None = None
    source: Source = field(default_factory=Source)
    observed: str | None = None  # YYYY-MM-DD, authored; never a runtime clock.
    relevance: str | None = None
    notes: str | None = None
    decision: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "question": self.question,
            "observation": self.observation,
            "evidence": self.evidence.value,
            "confidence": _optional(self.confidence),
            "source": self.source.to_dict(),
            "observed": self.observed,
            "relevance": self.relevance,
            "notes": self.notes,
            "decision": self.decision,
        }


@dataclass(frozen=True)
class Price:
    amount: str  # Decimal text as observed, e.g. "12.99"; never a float.
    currency: str  # ISO 4217 code, e.g. USD.

    def to_dict(self) -> dict[str, object]:
        return {"amount": self.amount, "currency": self.currency}


@dataclass(frozen=True)
class Comparable:
    """A comparable book a person looked at. Unknown values stay None, never zero."""

    id: str
    title: str
    contributor: str | None = None
    url: str | None = None
    citation: str | None = None
    format: str | None = None
    trim: str | None = None
    pages: int | None = None
    puzzles: int | None = None
    price: Price | None = None
    audience: str | None = None
    strengths: tuple[str, ...] = ()
    weaknesses: tuple[str, ...] = ()
    positioning: str | None = None
    observed: str | None = None
    evidence: Evidence = Evidence.UNKNOWN

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "title": self.title,
            "contributor": self.contributor,
            "url": self.url,
            "citation": self.citation,
            "format": self.format,
            "trim": self.trim,
            "pages": self.pages,
            "puzzles": self.puzzles,
            "price": self.price.to_dict() if self.price else None,
            "audience": self.audience,
            "strengths": list(self.strengths),
            "weaknesses": list(self.weaknesses),
            "positioning": self.positioning,
            "observed": self.observed,
            "evidence": self.evidence.value,
        }


@dataclass(frozen=True)
class PlanningDocument:
    concept: Concept = field(default_factory=Concept)
    positioning: Positioning = field(default_factory=Positioning)
    structure: Structure = field(default_factory=Structure)
    difficulty: Difficulty = field(default_factory=Difficulty)
    themes: tuple[Theme, ...] = ()
    vocabulary: tuple[Pool, ...] = ()
    puzzles: tuple[PlannedPuzzle, ...] = ()
    constraints: Constraints = field(default_factory=Constraints)
    questions: tuple[Question, ...] = ()
    research: tuple[Note, ...] = ()
    comparables: tuple[Comparable, ...] = ()
    # The planning identity the author approved, or None. Never set by PuzzlePress
    # on its own; it applies only while it equals the current planning identity.
    approval: str | None = None
    version: int = PLANNING_VERSION

    def content(self) -> dict[str, object]:
        """Everything the author planned: the document without its approval."""
        return {
            "planning_version": self.version,
            "concept": self.concept.to_dict(),
            "positioning": self.positioning.to_dict(),
            "structure": self.structure.to_dict(),
            "difficulty": self.difficulty.to_dict(),
            "themes": [theme.to_dict() for theme in self.themes],
            "vocabulary": [pool.to_dict() for pool in self.vocabulary],
            "puzzles": [puzzle.to_dict() for puzzle in self.puzzles],
            "constraints": self.constraints.to_dict(),
            "questions": [question.to_dict() for question in self.questions],
            "research": [note.to_dict() for note in self.research],
            "comparables": [comparable.to_dict() for comparable in self.comparables],
        }

    def to_dict(self) -> dict[str, object]:
        return {**self.content(), "approval": self.approval}
