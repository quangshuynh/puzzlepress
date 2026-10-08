"""Publishing metadata validation: the authored project alone, no artifacts.

Answers whether the KDP metadata (book details plus the publishing section) is
acceptable, whether the author has declared content origin, and whether the
author has confirmed what software cannot verify. Built files are judged by
readiness (puzzlepress.publishing.readiness), never here.
"""

from dataclasses import dataclass

from ..models import Project
from ..publishing_config import (
    CONFIRMATIONS,
    AiDisclosure,
    ContentOrigin,
    ContributorRole,
    IsbnMode,
    PublishingConfig,
)
from . import text
from .identity import publishing_identity
from .isbn import check_isbn
from .model import Area, Collector, Finding, Outcome, RuleResult, Scope, Severity
from .review import COVERS, review_identity
from .rules import (
    KDP_METADATA,
    KDP_RULES_CHECKED,
    METADATA_CODES,
    PAPERBACK_LANGUAGES,
    RULES,
    RULESET_ID,
    RULESET_VERSION,
)

ATTESTATION_TEXT = {
    "rights": "I hold the rights to publish this book's text, word lists and cover photograph.",
    "ai_disclosure": "I reviewed the AI content declaration above, and it is accurate.",
    "metadata": "The title, author and other book details, description, keywords, categories "
    "and audience accurately represent this book.",
    "isbn": "My ISBN is registered with this title, author and imprint exactly as entered.",
}
KINDS = ("text", "images", "translations")


def kdp_ai_answers(disclosure: AiDisclosure) -> dict[str, dict[str, str]]:
    """What the author's declaration means for KDP's AI-generated content question.

    KDP requires disclosure of AI-generated text, images or translations only;
    AI-assisted and human-created content need no disclosure.
    """
    meaning = {
        ContentOrigin.AI_GENERATED: "disclose",
        ContentOrigin.HUMAN: "not_required",
        ContentOrigin.AI_ASSISTED: "not_required",
        ContentOrigin.NONE: "not_applicable",
        ContentOrigin.UNKNOWN: "undecided",
    }
    return {
        kind: {"declared": origin.value, "kdp": meaning[origin]}
        for kind, origin in (
            ("text", disclosure.text),
            ("images", disclosure.images),
            ("translations", disclosure.translations),
        )
    }


def required_attestations(config: PublishingConfig) -> tuple[str, ...]:
    names = ("rights", "ai_disclosure", "metadata")
    return names + ("isbn",) if config.isbn.mode is IsbnMode.OWN else names


@dataclass(frozen=True)
class Confirmation:
    """Whether a stored confirmation applies to the content as it is now."""

    name: str
    required: bool
    # confirmed: stored identity equals current; stale: it names other content;
    # legacy: a version 1 yes; unconfirmed: nothing stored.
    state: str
    current: str  # Review identity of the covered content now.
    confirmed: str | None  # The stored review identity.

    @property
    def message(self) -> str:
        return {
            "confirmed": "It applies to the content as it is now.",
            "stale": "Something it covers changed after you confirmed it: "
            f"{COVERS[self.name]}. Review and confirm again (restoring exactly what you "
            "reviewed also restores it).",
            "legacy": "Saved as yes or no by publishing version 1, which did not record what "
            "you reviewed. Upgrade the section and confirm again.",
            "unconfirmed": f"It covers {COVERS[self.name]}.",
        }[self.state]

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "statement": ATTESTATION_TEXT[self.name],
            "covers": COVERS[self.name],
            "required": self.required,
            "state": self.state,
            "current": self.current,
            "confirmed": self.confirmed,
            "message": self.message,
        }


def confirmations(project: Project) -> tuple[Confirmation, ...]:
    """Every confirmation's state against the current content; () without publishing."""
    config = project.publishing
    if config is None:
        return ()
    required = required_attestations(config)
    states = []
    for name in CONFIRMATIONS:
        current = review_identity(project, name)
        stored = config.attestations.stored(name)
        legacy = config.attestations.legacy
        state = (
            "legacy"
            if legacy is not None and name in legacy
            else "unconfirmed"
            if stored is None
            else "confirmed"
            if stored == current
            else "stale"
        )
        states.append(Confirmation(name, name in required, state, current, stored))
    return tuple(states)


@dataclass(frozen=True)
class MetadataReport:
    book_id: str
    publishing_identity: str | None
    findings: tuple[Finding, ...]
    results: tuple[RuleResult, ...]
    confirmations: tuple[Confirmation, ...] = ()

    def _blocking(self, *scopes: Scope) -> bool:
        return any(
            r.rule.scope in scopes
            and r.rule.severity is Severity.ERROR
            and r.outcome in (Outcome.FAILED, Outcome.NOT_EVALUATED)
            for r in self.results
        )

    @property
    def configured(self) -> bool:
        return self.publishing_identity is not None

    @property
    def metadata_valid(self) -> bool:
        return self.configured and not self._blocking(Scope.METADATA, Scope.CONSISTENCY)

    @property
    def disclosure_complete(self) -> bool:
        return self.configured and not self._blocking(Scope.DISCLOSURE)

    @property
    def attestations_complete(self) -> bool:
        return self.configured and not self._blocking(Scope.ATTESTATION)

    @property
    def valid(self) -> bool:
        """Metadata valid, disclosure declared and confirmations given."""
        return self.metadata_valid and self.disclosure_complete and self.attestations_complete

    def to_dict(self) -> dict[str, object]:
        return {
            "report_version": 2,
            "ruleset": {
                "id": RULESET_ID,
                "version": RULESET_VERSION,
                "kdp_rules_checked": KDP_RULES_CHECKED,
            },
            "book_id": self.book_id,
            "publishing_identity": self.publishing_identity,
            "verdicts": self.verdicts(),
            "confirmations": [c.to_dict() for c in self.confirmations],
            "findings": [finding.to_dict() for finding in self.findings],
            "rules": [result.to_dict() for result in self.results],
        }

    def verdicts(self) -> dict[str, str]:
        return {
            "metadata": "missing"
            if not self.configured
            else "valid"
            if self.metadata_valid
            else "invalid",
            "disclosure": "complete" if self.disclosure_complete else "incomplete",
            "attestations": "complete" if self.attestations_complete else "incomplete",
        }


def validate_metadata(project: Project) -> MetadataReport:
    """Evaluate every metadata, disclosure and attestation rule. Pure."""
    c = Collector(RULES)
    config = project.publishing
    states = confirmations(project)
    if config is None:
        c.fail(
            "publishing_configured",
            "This project has no publishing section. Add KDP metadata in Publishing.",
            field="publishing",
            action="Start the publishing metadata.",
        )
        for code in METADATA_CODES:
            if code != "publishing_configured":
                c.skip(code, "No publishing metadata.")
    else:
        _book(c, project)
        _description(c, project, config)
        _keywords(c, project, config)
        _categories(c, config)
        _audience(c, config)
        _classification(c, project, config)
        _disclosure(c, config)
        _attestations(c, states)
    return MetadataReport(
        project.book.id,
        publishing_identity(project),
        tuple(sorted(c.findings, key=Finding.sort_key)),
        c.results(METADATA_CODES),
        states,
    )


# ---------------------------------------------------------------- book details


def _book(c: Collector, project: Project) -> None:
    book = project.book
    config = project.publishing
    assert config is not None
    combined = len(book.title) + len(book.subtitle or "")
    if combined > KDP_METADATA.max_title_and_subtitle:
        c.fail(
            "title_length",
            f"Title and subtitle together have {combined} characters; KDP requires fewer "
            "than 200 (one KDP page says 200 or less; the stricter reading applies).",
            field="book.title",
            actual=combined,
            required=KDP_METADATA.max_title_and_subtitle,
            action="Shorten the title or subtitle.",
            area=Area.EDIT,
        )
    titled = [("book.title", book.title, Area.EDIT)]
    if book.subtitle:
        titled.append(("book.subtitle", book.subtitle, Area.BOOK))
    if config.series:
        titled.append(("publishing.series.title", config.series.title, Area.PUBLISHING))
    for path, value, area in titled:
        problem = _name_problem(value)
        if problem:
            c.fail("title_content", f"{problem} ({path}).", field=path, area=area)
        promo = text.first(text.TITLE_PROMOTIONAL, value)
        if promo:
            c.fail(
                "title_review",
                f"'{promo}' reads as sales rank or promotion, which KDP does not allow in titles.",
                field=path,
                area=area,
                action="Keep only the title as it appears on the cover.",
            )
        words = [w.casefold() for w in value.split()]
        generic = sorted({w for w in words if w in text.GENERIC_TITLE_WORDS and words.count(w) > 1})
        if generic:
            c.fail(
                "title_review",
                f"'{generic[0]}' is repeated; KDP disallows repeating generic keywords in titles.",
                field=path,
                area=area,
            )
    if not book.author:
        c.fail(
            "author_present",
            "The book has no author. KDP needs the primary author name shown on the cover.",
            field="book.author",
            action="Enter the author in Book (title page) or Edit.",
            area=Area.BOOK,
        )
    names: list[tuple[str, str | None, Area]] = [
        ("book.author", book.author, Area.BOOK),
        ("book.imprint", book.imprint, Area.BOOK),
    ]
    names += [
        (f"publishing.contributors.{i}.name", person.name, Area.PUBLISHING)
        for i, person in enumerate(config.contributors)
    ]
    for path, name, area in names:
        problem = _name_problem(name) if name else None
        if problem:
            c.fail("names_content", f"{problem} ({path}).", field=path, area=area)
    if book.imprint and len(book.imprint) > KDP_METADATA.max_imprint:
        c.fail(
            "imprint_length",
            f"The imprint has {len(book.imprint)} characters; KDP's field holds "
            f"{KDP_METADATA.max_imprint}.",
            field="book.imprint",
            actual=len(book.imprint),
            required=KDP_METADATA.max_imprint,
            area=Area.BOOK,
        )
    seen: set[tuple[str, str]] = set()
    for i, person in enumerate(config.contributors):
        key = (person.role.value, person.name.casefold())
        path = f"publishing.contributors.{i}"
        if key in seen:
            c.fail(
                "contributors_review",
                f"{person.name} is listed twice as {person.role}.",
                field=path,
            )
        seen.add(key)
        if (
            person.role is ContributorRole.AUTHOR
            and book.author
            and person.name.casefold() == book.author.casefold()
        ):
            c.fail(
                "contributors_review",
                f"{person.name} is already the primary author; list additional people only.",
                field=path,
            )
    primary = book.language.split("-")[0].casefold()
    if primary not in PAPERBACK_LANGUAGES:
        c.fail(
            "language_supported",
            f"Language '{book.language}' is not one KDP lists for paperbacks.",
            field="book.language",
            actual=book.language,
            action="Choose a language KDP supports for paperbacks.",
            area=Area.EDIT,
        )
    else:
        c.note("language_supported", f"{PAPERBACK_LANGUAGES[primary]} ({book.language}).")


def _name_problem(value: str) -> str | None:
    if text.TAG.search(value):
        return "HTML tags are not accepted"
    if text.is_placeholder(value):
        return f"'{value}' is a placeholder, which KDP does not accept"
    if text.punctuation_only(value):
        return "Text made only of punctuation is not accepted"
    return None


# ---------------------------------------------------------------- description


def _description(c: Collector, project: Project, config: PublishingConfig) -> None:
    field = "publishing.description"
    body = config.description
    if body is None:
        c.fail(
            "description_present",
            "No description yet. KDP shows it on the book's product page.",
            field=field,
            action="Write a plain-text description of what the book contains.",
        )
        for code in (
            "description_length",
            "description_markup",
            "description_prohibited",
            "description_review",
            "description_claims",
        ):
            c.skip(code, "No description.")
        return
    if len(body) > KDP_METADATA.max_description:
        c.fail(
            "description_length",
            f"The description has {len(body):,} characters; KDP allows "
            f"{KDP_METADATA.max_description:,}.",
            field=field,
            actual=len(body),
            required=KDP_METADATA.max_description,
            action="Shorten the description.",
        )
    if text.ANGLE.search(body):
        tag = text.first(text.TAG, body) or text.first(text.ANGLE, body)
        c.fail(
            "description_markup",
            f"'{tag}': PuzzlePress keeps descriptions as plain text; angle brackets and HTML "
            "are not passed to KDP.",
            field=field,
            action="Remove the markup; separate paragraphs with blank lines.",
        )
    prohibited = (
        (text.URL, "website address"),
        (text.EMAIL, "email address"),
        (text.PHONE, "phone number"),
        (text.PRICE, "price"),
        (text.REVIEW_REQUEST, "request for reviews"),
    )
    for pattern, label in prohibited:
        found = text.first(pattern, body)
        if found:
            c.fail(
                "description_prohibited",
                f"Contains a {label} ('{found}'), which KDP does not accept in descriptions.",
                field=field,
                action=f"Remove the {label}.",
            )
    marks = text.emojis(body)
    if marks:
        c.fail(
            "description_prohibited",
            f"Contains emoji or symbols KDP does not accept ({' '.join(marks)}).",
            field=field,
            action="Remove the emoji.",
        )
    hidden = text.invisible(body)
    if hidden:
        c.fail(
            "description_prohibited",
            f"Contains invisible characters ({', '.join(hidden)}), which KDP rejects.",
            field=field,
            action="Retype the affected text or remove the invisible characters.",
        )
    for pattern, label in (
        (text.REVIEW_LIKE, "reviews, quotes or testimonials"),
        (text.PROMOTIONAL, "promotional or time-sensitive information"),
    ):
        found = text.first(pattern, body)
        if found:
            c.fail(
                "description_review",
                f"'{found}' may be {label}, which KDP does not accept. Review the wording.",
                field=field,
            )
    stuffed = text.repeated_word(body)
    if stuffed:
        c.fail(
            "description_review",
            f"'{stuffed[0]}' appears {stuffed[1]} times; KDP does not accept keyword "
            "phrases in descriptions.",
            field=field,
        )
    words = project.word_search
    puzzles = len(words.puzzles) if words else 0
    for phrase, claimed in text.puzzle_claims(body):
        if claimed != puzzles:
            c.fail(
                "description_claims",
                f"'{phrase}' claims {claimed} puzzles; the book contains {puzzles}.",
                field=field,
                actual=claimed,
                required=puzzles,
                action="Correct the count; PuzzlePress never edits your description.",
            )
    composition = project.composition
    omitted = composition is not None and composition.solutions.placement.value == "omit"
    mentioned = text.first(text.SOLUTIONS, body)
    if omitted and mentioned:
        c.fail(
            "description_claims",
            f"The description mentions '{mentioned}', but the book omits solutions.",
            field=field,
            action="Remove the mention or include solutions in Book.",
        )


# ---------------------------------------------------------------- keywords and categories


def _keywords(c: Collector, project: Project, config: PublishingConfig) -> None:
    keywords = config.keywords
    if not keywords:
        c.fail(
            "keywords_present",
            "No keywords. KDP lets you add up to seven to help readers find the book.",
            field="publishing.keywords",
        )
    if len(keywords) > KDP_METADATA.max_keywords:
        c.fail(
            "keywords_count",
            f"{len(keywords)} keywords; KDP allows {KDP_METADATA.max_keywords}.",
            field="publishing.keywords",
            actual=len(keywords),
            required=KDP_METADATA.max_keywords,
            action="Remove keywords until seven remain.",
        )
    exact: dict[str, int] = {}
    variants: dict[str, int] = {}
    book = project.book
    elsewhere = {
        value.casefold() for value in (book.title, book.subtitle, book.author) if value
    } | {p.name.casefold() for p in config.contributors}
    segments = {
        part.strip().casefold() for category in config.categories for part in category.split(">")
    }
    for i, keyword in enumerate(keywords):
        path = f"publishing.keywords.{i}"
        for pattern, label in (
            (text.QUOTES, "quotation marks"),
            (text.TAG, "HTML tags"),
            (text.PROGRAMS, "Amazon program names"),
        ):
            found = text.first(pattern, keyword)
            if found:
                c.fail("keywords_format", f"'{keyword}' contains {label} ('{found}').", field=path)
        key = text.keyword_key(keyword)
        if key in exact:
            c.fail(
                "keywords_format",
                f"'{keyword}' repeats keyword {exact[key] + 1}.",
                field=path,
                action="Remove the duplicate.",
            )
            continue
        exact[key] = i
        variant = text.keyword_variant(keyword)
        if variant in variants:
            c.fail(
                "keywords_review",
                f"'{keyword}' is a spacing, punctuation or plural variant of keyword "
                f"{variants[variant] + 1}; KDP advises against repeating variants.",
                field=path,
            )
        variants.setdefault(variant, i)
        if len(keyword) > KDP_METADATA.keyword_field_length:
            c.fail(
                "keywords_length",
                f"'{keyword[:24]}...' has {len(keyword)} characters; KDP's field may not hold "
                f"more than about {KDP_METADATA.keyword_field_length}.",
                field=path,
                actual=len(keyword),
                required=KDP_METADATA.keyword_field_length,
            )
        subjective = text.first(text.SUBJECTIVE, keyword)
        if subjective:
            c.fail(
                "keywords_review",
                f"'{subjective}' is a subjective or time-sensitive claim KDP asks you to avoid.",
                field=path,
            )
        if key in text.GENERIC_KEYWORDS:
            c.fail(
                "keywords_review",
                f"'{keyword}' is common to every item in the category.",
                field=path,
            )
        if key in elsewhere:
            c.fail(
                "keywords_review",
                f"'{keyword}' repeats the title or a contributor; KDP already searches those.",
                field=path,
            )
        elif key in segments:
            c.fail(
                "keywords_review",
                f"'{keyword}' repeats a chosen category; KDP advises using other words.",
                field=path,
            )


def _categories(c: Collector, config: PublishingConfig) -> None:
    categories = config.categories
    if not categories:
        c.fail(
            "categories_present",
            "No categories saved. You will choose up to three in KDP's category selector.",
            field="publishing.categories",
        )
        c.not_applicable("categories_unverified", "No categories saved.")
    else:
        c.fail(
            "categories_unverified",
            "Categories are saved preferences. KDP's list differs by marketplace and format "
            "and changes over time; confirm each one is available when you select it in KDP.",
            field="publishing.categories",
            action="Select matching categories in KDP's category selector.",
        )
    if len(categories) > KDP_METADATA.max_categories:
        c.fail(
            "categories_count",
            f"{len(categories)} categories; KDP lets you select {KDP_METADATA.max_categories}.",
            field="publishing.categories",
            actual=len(categories),
            required=KDP_METADATA.max_categories,
        )
    seen: set[str] = set()
    for i, category in enumerate(categories):
        path = f"publishing.categories.{i}"
        parts = [part.strip() for part in category.split(">")]
        if any(not part for part in parts) or len(parts) > 6:
            c.fail(
                "categories_format",
                f"'{category}': write the path as segments separated by ' > ', for example "
                "'Humor & Entertainment > Puzzles & Games > Word Search'.",
                field=path,
            )
        if text.TAG.search(category):
            c.fail("categories_format", f"'{category}' contains HTML tags.", field=path)
        key = " > ".join(part.casefold() for part in parts)
        if key in seen:
            c.fail("categories_format", f"'{category}' is listed twice.", field=path)
        seen.add(key)


# ---------------------------------------------------------------- audience and classification


def _audience(c: Collector, config: PublishingConfig) -> None:
    audience = config.audience
    if audience.sexually_explicit is None:
        c.fail(
            "audience_explicit",
            "Answer KDP's question whether the book has sexually explicit images or title.",
            field="publishing.audience.sexually_explicit",
            action="Choose yes or no.",
        )
    age = audience.reading_age
    if audience.sexually_explicit and age.minimum is not None and age.minimum < 18:
        c.fail(
            "audience_reading_age",
            "A book declared sexually explicit cannot have a reading age below 18.",
            field="publishing.audience.reading_age.minimum",
            actual=age.minimum,
            required=18,
        )
    if (age.minimum is None) != (age.maximum is None):
        c.fail(
            "audience_reading_age",
            "Enter both a minimum and a maximum reading age, or neither.",
            field="publishing.audience.reading_age",
        )


def _classification(c: Collector, project: Project, config: PublishingConfig) -> None:
    low = config.low_content
    mode = config.isbn.mode
    if low is None:
        c.fail(
            "low_content_decided",
            "Decide whether this is a low-content book. KDP lists puzzle books as "
            "'not generally low-content', with exceptions, and rejects a wrong choice.",
            field="publishing.low_content",
            action="Choose a classification; PuzzlePress does not choose for you.",
        )
    elif low:
        c.fail(
            "low_content_review",
            "Marked low-content. KDP describes low-content books as repetitive pages to fill "
            "in and lists puzzle books as not generally low-content. Confirm this exception.",
            field="publishing.low_content",
        )
    else:
        c.not_applicable("low_content_review", "Not low-content.")
    if mode is IsbnMode.UNDECIDED:
        c.fail(
            "isbn_decided",
            "Choose an ISBN option: a free KDP ISBN or your own. PuzzlePress never invents one.",
            field="publishing.isbn.mode",
        )
    if mode is IsbnMode.OWN:
        value = config.isbn.value
        if value is None:
            c.fail(
                "isbn_valid",
                "Enter your ISBN-13, or choose a different ISBN option.",
                field="publishing.isbn.value",
            )
        else:
            checked = check_isbn(value)
            if checked.problem:
                c.fail(
                    "isbn_valid",
                    f"'{value}': {checked.problem}",
                    field="publishing.isbn.value",
                    required=checked.required,
                )
            else:
                c.note(
                    "isbn_valid",
                    f"ISBN-13 {checked.digits} has a valid check digit. Registration and "
                    "ownership are not verified.",
                )
        if not project.book.imprint:
            c.fail(
                "isbn_imprint",
                "With your own ISBN, KDP compares the imprint with the ISBN agency's record. "
                "Enter the publisher name you registered.",
                field="book.imprint",
                area=Area.BOOK,
            )
    else:
        c.not_applicable("isbn_valid", "No author-supplied ISBN.")
    if mode is IsbnMode.KDP_FREE and project.book.imprint:
        c.fail(
            "isbn_imprint",
            f"With a free KDP ISBN, KDP lists the imprint as 'Independently published', not "
            f"'{project.book.imprint}'. The imprint printed on your cover is unchanged.",
            field="book.imprint",
            area=Area.BOOK,
        )
    if mode is IsbnMode.KDP_FREE and low:
        c.fail(
            "isbn_eligibility",
            "Low-content books are not eligible for the free KDP ISBN.",
            field="publishing.isbn.mode",
        )
    if mode is IsbnMode.NONE and not low:
        c.fail(
            "isbn_eligibility",
            "Only low-content books may publish without an ISBN; paperbacks need one.",
            field="publishing.isbn.mode",
        )
    if low and config.series is not None:
        c.fail(
            "series_eligibility",
            "Low-content books are not eligible for a series.",
            field="publishing.series",
        )


# ---------------------------------------------------------------- disclosure and attestations


def _disclosure(c: Collector, config: PublishingConfig) -> None:
    answers = kdp_ai_answers(config.ai_disclosure)
    for kind in KINDS:
        if answers[kind]["kdp"] == "undecided":
            c.fail(
                "ai_disclosure_complete",
                f"Declare who or what created the book's {kind}. KDP requires disclosure of "
                "AI-generated text, images or translations.",
                field=f"publishing.ai_disclosure.{kind}",
                action="Choose human, AI-assisted, AI-generated"
                + (" or not a translation." if kind == "translations" else "."),
            )
    generated = [kind for kind in KINDS if answers[kind]["kdp"] == "disclose"]
    if generated:
        c.fail(
            "ai_disclosure_required",
            f"Declared AI-generated: {', '.join(generated)}. Disclose this in KDP's AI-generated "
            "content question when you set up the book.",
            field="publishing.ai_disclosure",
        )
    else:
        c.note("ai_disclosure_required", "Nothing declared AI-generated.")


def _attestations(c: Collector, states: tuple[Confirmation, ...]) -> None:
    for state in states:
        if not state.required or state.state == "confirmed":
            continue
        statement = ATTESTATION_TEXT[state.name]
        c.fail(
            "attestations",
            f"Not confirmed: {statement}"
            if state.state == "unconfirmed"
            else f"Review again: {statement} {state.message}",
            field=f"publishing.attestations.{state.name}",
            action="Upgrade the publishing section to version 2, then review and confirm it."
            if state.state == "legacy"
            else "Review and confirm it yourself; PuzzlePress cannot verify it.",
        )
