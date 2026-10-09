"""Deterministic planning diagnostics: definition, research, content, structure,
decisions and editorial review, plus the views Studio and the CLI present.

Every finding has a stable code from `planning.rules`. Hard constraints are
facts about the plan (an allocation that does not add up, a word the generator
rejects, an unknown reference). Editorial findings are heuristics: they say what
they compared and never claim to measure quality, originality or market fit.
Nothing here edits the plan, generates puzzles or reads the network.
"""

import math
import re
from collections.abc import Iterable
from dataclasses import dataclass
from itertools import combinations

from ..content import QualityConfig
from ..models import Project
from ..publishing.text import PROMOTIONAL, first
from ..quality import compare_target_sets
from ..wordsearch import Direction, GenerationConfig, GridSize, WordSearchError
from ..wordsearch.validation import normalize_config
from .model import (
    SOURCED_EVIDENCE,
    WEAK_EVIDENCE,
    Evidence,
    Familiarity,
    Level,
    Note,
    PlanningDocument,
    SolutionsPlan,
    Strategy,
    Theme,
    WordSource,
    direction_name,
)
from .rules import Findings
from .vocabulary import WordInfo, analyze_pools

# Editorial heuristics. They flag candidates for a person to look at; the
# thresholds are documented conventions (docs/book-planning.md), not findings
# about readers.
LABEL_SIMILARITY = 0.5  # Shared share of meaningful label words.
POOL_OVERLAP = 0.3  # Jaccard of two theme pools' valid search forms.
OVERREPRESENTED = 2.0  # Times the even share of the allocated puzzles.
THIN = 0.5  # Times the even share.
LABEL_STOPWORDS = frozenset({"a", "an", "and", "the", "of", "in", "for", "to", "on", "with"})
SUPERLATIVE = re.compile(
    r"\b(?:best|ultimate|greatest|unrivall?ed|unbeatable|"
    r"most\s+(?:complete|comprehensive|popular|loved))\b",
    re.IGNORECASE,
)
QUALITY_DEFAULTS = QualityConfig()


@dataclass(frozen=True)
class LevelSettings:
    """A level's effective generator settings, from the plan or a project profile."""

    level: Level
    rank: int  # 1 is the easiest, by the author's declared order.
    path: str
    width: int | None
    height: int | None
    directions: tuple[Direction, ...]
    config: GenerationConfig | None  # Normalized; None when missing or unsupported.
    origin: str  # "plan" or "profile"
    problem: str | None = None  # missing | unknown_profile | the engine's message


def _label_key(label: str) -> str:
    return " ".join(re.findall(r"[^\W_]+", label.casefold().replace("&", " and ")))


def _label_tokens(label: str) -> frozenset[str]:
    words = (w for w in _label_key(label).split() if w not in LABEL_STOPWORDS)
    return frozenset(w[:-1] if len(w) > 3 and w.endswith("s") and not w.endswith("ss") else w
                     for w in words)  # fmt: skip


def _jaccard(left: Iterable[str], right: Iterable[str]) -> float:
    a, b = set(left), set(right)
    return len(a & b) / len(a | b) if a | b else 0.0


def _plural(count: int, word: str) -> str:
    return f"{count} {word}{'' if count == 1 else 's'}"


class PlanAnalysis:
    """One evaluation of a plan against its project and the running engine."""

    def __init__(self, project: Project, document: PlanningDocument) -> None:
        self.project = project
        self.doc = document
        self.findings = Findings()
        self.themes = {theme.id: theme for theme in document.themes}
        self.theme_index = {theme.id: i for i, theme in enumerate(document.themes)}
        self.notes = {note.id: note for note in document.research}
        self.questions = {question.id: question for question in document.questions}
        self.pools = analyze_pools(document)
        self.pool_by_theme = {info.pool.theme: info for info in self.pools}
        self.children: dict[str, list[str]] = {}
        for theme in document.themes:
            if theme.parent in self.themes and theme.parent != theme.id:
                self.children.setdefault(theme.parent, []).append(theme.id)
        self.levels = self._levels()
        self.level_by_id = {s.level.id: s for s in self.levels}
        self.max_reuse = document.constraints.max_word_reuse or QUALITY_DEFAULTS.max_word_reuse
        prohibited = set(document.constraints.prohibited_words)
        if project.word_search is not None:
            prohibited |= set(project.word_search.quality.prohibited_words)
        self.prohibited = tuple(sorted(prohibited))
        # Matched puzzle words: (puzzle index, word info) for words found in the pool.
        self.assigned: dict[int, list[WordInfo]] = {}
        self._run()

    # ------------------------------------------------------------------ helpers

    def leaf(self, theme_id: str) -> bool:
        return not self.children.get(theme_id)

    def subtree(self, theme_id: str) -> list[str]:
        found: list[str] = []
        stack = [theme_id]
        while stack:
            current = stack.pop()
            if current in found:
                continue
            found.append(current)
            stack.extend(self.children.get(current, []))
        return found

    def lineage(self, a: str, b: str) -> bool:
        """Whether one theme is an ancestor of the other."""
        return a in self.subtree(b) or b in self.subtree(a)

    def allocation(self, theme: Theme) -> int:
        return theme.puzzles or 0

    def specified(self, theme_id: str) -> int:
        return sum(puzzle.theme == theme_id for puzzle in self.doc.puzzles)

    def _levels(self) -> tuple[LevelSettings, ...]:
        profiles = (
            {p.id: p.config for p in self.project.word_search.profiles}
            if self.project.word_search
            else {}
        )
        found: list[LevelSettings] = []
        for rank, level in enumerate(self.doc.difficulty.levels, 1):
            path = f"difficulty.levels.{rank - 1}"
            if level.profile is not None:
                config = profiles.get(level.profile)
                if config is None:
                    found.append(
                        LevelSettings(
                            level, rank, path, None, None, (), None, "profile", "unknown_profile"
                        )  # fmt: skip
                    )
                    continue
                found.append(
                    LevelSettings(
                        level,
                        rank,
                        path,
                        config.size.width,
                        config.size.height,
                        config.directions,
                        config,
                        "profile",
                    )
                )
                continue
            if level.width is None or level.height is None or not level.directions:
                found.append(
                    LevelSettings(
                        level,
                        rank,
                        path,
                        level.width,
                        level.height,
                        level.directions,
                        None,
                        "plan",
                        "missing",
                    )  # fmt: skip
                )
                continue
            try:
                config = normalize_config(
                    GenerationConfig(GridSize(level.width, level.height), level.directions)
                )
                problem = None
            except WordSearchError as error:
                config, problem = None, "; ".join(i.message for i in error.issues)
            found.append(
                LevelSettings(
                    level,
                    rank,
                    path,
                    level.width,
                    level.height,
                    level.directions,
                    config,
                    "plan",
                    problem,
                )  # fmt: skip
            )
        return tuple(found)

    # ------------------------------------------------------------------ checks

    def _run(self) -> None:
        self._definition()
        self._research()
        self._themes()
        self._vocabulary()
        self._puzzles()
        self._progression()
        self._decisions()
        self._editorial()

    def _definition(self) -> None:
        add = self.findings.add
        c, p, s, d = self.doc.concept, self.doc.positioning, self.doc.structure, self.doc.difficulty
        for value, code, path, message in (
            (c.summary, "concept_missing", "concept.summary", "State the book concept."),
            (c.subject, "subject_missing", "concept.subject", "State the subject or niche."),
            (
                p.primary_audience,
                "audience_missing",
                "positioning.primary_audience",
                "Choose who the book is for. Candidate audiences are not a choice.",
            ),
            (
                p.differentiation,
                "differentiation_missing",
                "positioning.differentiation",
                "State what makes this book different.",
            ),
            (
                s.puzzle_type,
                "puzzle_type_missing",
                "structure.puzzle_type",
                "State the puzzle type.",
            ),
            (
                s.target_puzzles,
                "target_missing",
                "structure.target_puzzles",
                "State how many puzzles the book should contain.",
            ),
        ):
            if value is None:
                add(code, message, path=path, action="Decide and record it in the plan.")
        if d.strategy is Strategy.UNDECIDED:
            add(
                "strategy_undecided",
                "Choose how difficulty develops: consistent, gradual, sections or mixed.",
                path="difficulty.strategy",
            )
        if not self.doc.themes:
            add("themes_missing", "Plan at least one theme.", path="themes")
        if not d.levels:
            add("levels_missing", "Plan at least one difficulty level.", path="difficulty.levels")

    def _cite(self, ids: tuple[str, ...], path: str) -> list[Note]:
        found: list[Note] = []
        for i, note_id in enumerate(ids):
            note = self.notes.get(note_id)
            if note is None:
                self.findings.add(
                    "reference_unknown",
                    f"No research note has the ID {note_id!r}.",
                    path=f"{path}.{i}",
                    subjects=(note_id,),
                )
            else:
                found.append(note)
        return found

    def _research(self) -> None:
        add = self.findings.add
        for i, question in enumerate(self.doc.questions):
            if question.resolution is not None:
                continue
            if question.blocking:
                add(
                    "question_blocking_open",
                    f"Blocking question is unresolved: {question.question}",
                    path=f"questions.{i}.resolution",
                    subjects=(question.id,),
                    action="Research or decide, then record the resolution.",
                )
            else:
                add("question_open", f"Open question: {question.question}",
                    path=f"questions.{i}", subjects=(question.id,))  # fmt: skip
        for i, note in enumerate(self.doc.research):
            path = f"research.{i}"
            if note.question is not None and note.question not in self.questions:
                add(
                    "reference_unknown",
                    f"No question has the ID {note.question!r}.",
                    path=f"{path}.question",
                    subjects=(note.question,),
                )
            if note.evidence in SOURCED_EVIDENCE and not note.source.cited:
                add(
                    "evidence_source_missing",
                    f"Note {note.id} is recorded as {note.evidence.value.replace('_', ' ')} "
                    "but cites no source.",
                    path=f"{path}.source",
                    subjects=(note.id,),
                    action="Add the citation or URL, or record the note as what it is.",
                )
            if note.evidence is Evidence.VERIFIED_SOURCE and note.observed is None:
                add(
                    "evidence_undated",
                    f"Note {note.id} cites a verified source without the date it was read.",
                    path=f"{path}.observed",
                    subjects=(note.id,),
                )
            self._url(note.source.url, f"{path}.source.url", note.id)
            if note.decision is not None and note.evidence in WEAK_EVIDENCE:
                add(
                    "assumption_unresolved",
                    f"A decision rests on note {note.id}, recorded as "
                    f"{note.evidence.value}: {note.decision}",
                    path=f"{path}.decision",
                    subjects=(note.id,),
                    action="Verify the assumption, or record the note as a preference if it is.",
                )
        positioning = self.doc.positioning
        for note in self._cite(positioning.evidence, "positioning.evidence"):
            if note.evidence in WEAK_EVIDENCE:
                add(
                    "assumption_unresolved",
                    f"The positioning relies on note {note.id}, recorded as {note.evidence.value}.",
                    path="positioning.evidence",
                    subjects=(note.id,),
                )
        for i, claim in enumerate(positioning.claims):
            path = f"positioning.claims.{i}"
            cited = self._cite(claim.evidence, f"{path}.evidence")
            kinds = {note.evidence for note in cited}
            if Evidence.VERIFIED_SOURCE in kinds:
                continue
            if kinds & {Evidence.UNVERIFIED_SOURCE, Evidence.AUTHOR_OBSERVATION}:
                add(
                    "claim_weak_evidence",
                    f"Claim rests on unverified or observed evidence only: {claim.text}",
                    path=path,
                )
            else:
                add(
                    "claim_unsupported",
                    f"Claim has no supporting evidence: {claim.text}",
                    path=path,
                    action="Cite a verified source, or drop the claim.",
                )
        for i, comparable in enumerate(self.doc.comparables):
            path = f"comparables.{i}"
            if comparable.url is None and comparable.citation is None:
                add(
                    "comparable_unsourced",
                    f"Comparable {comparable.title!r} does not say where it was observed.",
                    path=path,
                    subjects=(comparable.id,),
                    action="Add the URL or citation you read, or remove the record.",
                )
            if comparable.price is not None and comparable.observed is None:
                add(
                    "comparable_price_undated",
                    f"The price of {comparable.title!r} has no observation date; prices change.",
                    path=f"{path}.observed",
                    subjects=(comparable.id,),
                )
            self._url(comparable.url, f"{path}.url", comparable.id)

    def _url(self, url: str | None, path: str, subject: str) -> None:
        if url is not None and not re.match(r"https?://\S+$", url):
            self.findings.add(
                "source_url_format",
                "This source URL is not an http(s) web address.",
                path=path,
                actual=url,
                subjects=(subject,),
            )

    def _themes(self) -> None:
        add = self.findings.add
        themes = self.doc.themes
        for i, theme in enumerate(themes):
            if theme.parent is not None and theme.parent not in self.themes:
                add("reference_unknown", f"No theme has the ID {theme.parent!r}.",
                    path=f"themes.{i}.parent", subjects=(theme.parent,))  # fmt: skip
        reported: set[str] = set()
        for theme in themes:
            seen: list[str] = []
            current: str | None = theme.id
            while current is not None and current in self.themes and current not in seen:
                seen.append(current)
                current = self.themes[current].parent
            if current is not None and current in seen and theme.id not in reported:
                cycle = seen[seen.index(current) :]
                reported.update(cycle)
                add(
                    "theme_cycle",
                    "Theme parents form a cycle: " + " -> ".join([*cycle, current]) + ".",
                    path=f"themes.{self.theme_index[current]}.parent",
                    subjects=tuple(cycle),
                )
        keys: dict[str, int] = {}
        for i, theme in enumerate(themes):
            key = _label_key(theme.label)
            if key in keys:
                add(
                    "theme_label_duplicate",
                    f"Theme label {theme.label!r} duplicates {themes[keys[key]].label!r}.",
                    path=f"themes.{i}.label",
                    subjects=(themes[keys[key]].id, theme.id),
                )
            else:
                keys[key] = i
        for (_, a), (j, b) in combinations(enumerate(themes), 2):
            if _label_key(a.label) == _label_key(b.label) or self.lineage(a.id, b.id):
                continue  # A child naturally repeats its parent's word.
            similarity = _jaccard(_label_tokens(a.label), _label_tokens(b.label))
            if similarity >= LABEL_SIMILARITY:
                add(
                    "theme_labels_similar",
                    f"Theme labels {a.label!r} and {b.label!r} share most of their words. "
                    "Related themes are fine; make sure readers can tell them apart.",
                    path=f"themes.{j}.label",
                    actual=round(similarity, 3),
                    expected=f"below {LABEL_SIMILARITY}",
                    subjects=(a.id, b.id),
                )
        # Allocation: leaves need a number; a parent may hold puzzles of its own.
        missing = [(i, t) for i, t in enumerate(themes) if t.puzzles is None and self.leaf(t.id)]
        for i, theme in missing:
            add(
                "allocation_missing",
                f"Theme {theme.label!r} has no planned puzzle count.",
                path=f"themes.{i}.puzzles",
                subjects=(theme.id,),
            )
        target = self.doc.structure.target_puzzles
        total = sum(self.allocation(t) for t in themes)
        if themes and not missing and target is not None and total != target:
            add(
                "allocation_total_mismatch",
                f"Theme allocations add up to {total}; the target is {target}.",
                path="themes",
                actual=total,
                expected=target,
                action="Change allocations or the target until they agree.",
            )
        for i, theme in enumerate(themes):
            below = sum(self.allocation(self.themes[t]) for t in self.subtree(theme.id))
            if (
                theme.required
                and below == 0
                and not (theme.puzzles is None and self.leaf(theme.id))
            ):
                add(
                    "required_theme_empty",
                    f"Required theme {theme.label!r} receives no puzzles.",
                    path=f"themes.{i}.puzzles",
                    subjects=(theme.id,),
                )
            elif not theme.required and theme.puzzles == 0 and self.leaf(theme.id):
                add(
                    "theme_without_puzzles",
                    f"Theme {theme.label!r} receives no puzzles.",
                    path=f"themes.{i}.puzzles",
                    subjects=(theme.id,),
                )
            if theme.puzzles is not None and self.specified(theme.id) > theme.puzzles:
                add(
                    "theme_overspecified",
                    f"{self.specified(theme.id)} planned puzzles use theme {theme.label!r}; "
                    f"its allocation is {theme.puzzles}.",
                    path=f"themes.{i}.puzzles",
                    actual=self.specified(theme.id),
                    expected=theme.puzzles,
                    subjects=(theme.id,),
                )
        allocated = [t for t in themes if self.allocation(t) > 0]
        if len(allocated) >= 2:
            share = sum(self.allocation(t) for t in allocated) / len(allocated)
            for theme in allocated:
                i = self.theme_index[theme.id]
                ratio = self.allocation(theme) / share
                if ratio > OVERREPRESENTED:
                    add(
                        "theme_overrepresented",
                        f"Theme {theme.label!r} has {theme.puzzles} puzzles, "
                        f"{ratio:.1f} times an even share ({share:.1f}).",
                        path=f"themes.{i}.puzzles",
                        actual=self.allocation(theme),
                        expected=f"at most {OVERREPRESENTED:g} x {share:.1f}",
                        subjects=(theme.id,),
                    )
                elif ratio < THIN:
                    add(
                        "theme_thin",
                        f"Theme {theme.label!r} has {theme.puzzles} puzzles, "
                        f"less than half an even share ({share:.1f}).",
                        path=f"themes.{i}.puzzles",
                        actual=self.allocation(theme),
                        subjects=(theme.id,),
                    )

    def _vocabulary(self) -> None:
        add = self.findings.add
        c = self.doc.constraints
        form_themes: dict[str, list[str]] = {}
        form_text: dict[str, str] = {}
        for info in self.pools:
            theme = self.themes.get(info.pool.theme)
            if theme is None:
                add("reference_unknown", f"No theme has the ID {info.pool.theme!r}.",
                    path=f"{info.path}.theme", subjects=(info.pool.theme,))  # fmt: skip
            for word in info.words:
                path = f"{info.path}.entries.{word.index}.word"
                if word.search is None:
                    add(
                        "word_invalid",
                        f"{word.word!r}: {word.problem}",
                        path=path,
                        actual=word.word,
                        subjects=(word.word,),
                        action="Write the word with ASCII letters and spaces only.",
                    )
                    continue
                if word.duplicate_of is not None:
                    add(
                        "word_duplicate",
                        f"{word.word!r} normalizes to {word.search}, like entry "
                        f"{info.words[word.duplicate_of].word!r}.",
                        path=path,
                        actual=word.search,
                        subjects=(word.word,),
                    )
                    continue
                form_themes.setdefault(word.search, []).append(info.pool.theme)
                form_text.setdefault(word.search, word.word)
                length = len(word.search)
                if word.search in self.prohibited:
                    add("word_prohibited", f"{word.word!r} is on the prohibited list.",
                        path=path, subjects=(word.word,))  # fmt: skip
                else:
                    inside = [p for p in self.prohibited if p in word.search]
                    if inside:
                        add(
                            "word_contains_prohibited",
                            f"{word.word!r} contains the prohibited form {inside[0]}. Check "
                            "whether this is an innocent overlap.",
                            path=path,
                            subjects=(word.word,),
                        )
                if c.min_letters is not None and length < c.min_letters:
                    add("word_short", f"{word.word!r} has {length} letters.", path=path,
                        actual=length, expected=f"at least {c.min_letters}",
                        subjects=(word.word,))  # fmt: skip
                if c.max_letters is not None and length > c.max_letters:
                    add("word_long", f"{word.word!r} has {length} letters.", path=path,
                        actual=length, expected=f"at most {c.max_letters}",
                        subjects=(word.word,))  # fmt: skip
            licensed = [
                w for w in info.words
                if w.source is WordSource.LICENSED
                and info.pool.entries[w.index].reference is None
                and info.pool.reference is None
            ]  # fmt: skip
            if licensed:
                add(
                    "licensed_unreferenced",
                    f"{_plural(len(licensed), 'licensed word')} in {info.pool.theme} record no "
                    "licence reference.",
                    path=info.path,
                    subjects=tuple(w.word for w in licensed),
                )
        for form, themes in sorted(form_themes.items()):
            if len(themes) > 1:
                add(
                    "word_cross_theme",
                    f"{form_text[form]} appears in {len(themes)} theme pools: {', '.join(themes)}.",
                    subjects=(form_text[form], *themes),
                )
        for a, b in combinations(self.pools, 2):
            overlap = _jaccard(a.forms, b.forms)
            if overlap >= POOL_OVERLAP:
                add(
                    "theme_vocabulary_overlap",
                    f"Pools {a.pool.theme} and {b.pool.theme} share "
                    f"{len(set(a.forms) & set(b.forms))} words (Jaccard {overlap:.2f}). The "
                    "themes may overlap; shared terms alone are not a problem.",
                    path=b.path,
                    actual=round(overlap, 3),
                    expected=f"below {POOL_OVERLAP}",
                    subjects=(a.pool.theme, b.pool.theme),
                )
        generated = sum(
            w.source is WordSource.AI_GENERATED for info in self.pools for w in info.words
        )
        if generated:
            add(
                "vocabulary_ai_generated",
                f"{_plural(generated, 'candidate word')} are recorded as AI-generated. If "
                "they are used, declare the book text's AI involvement in Publishing.",
                actual=generated,
            )

    def _puzzles(self) -> None:
        add = self.findings.add
        doc = self.doc
        target = doc.structure.target_puzzles
        count = len(doc.puzzles)
        if target is not None and count < target:
            add(
                "puzzles_unspecified",
                f"{target - count} of {target} planned puzzles are not yet specified.",
                path="puzzles",
                actual=count,
                expected=target,
                action="Specify each puzzle's theme, level and words.",
            )
        elif target is not None and count > target:
            add("puzzles_exceed_target", f"{count} puzzles are specified; the target is {target}.",
                path="puzzles", actual=count, expected=target)  # fmt: skip
        pools_reported: set[str] = set()
        for t in doc.themes:
            if self.allocation(t) > 0 and t.id not in self.pool_by_theme:
                pools_reported.add(t.id)
                add(
                    "pool_missing",
                    f"Theme {t.label!r} has puzzles allocated but no candidate vocabulary.",
                    path=f"themes.{self.theme_index[t.id]}",
                    subjects=(t.id,),
                )
        titles: dict[str, int] = {}
        for i, puzzle in enumerate(doc.puzzles):
            path = f"puzzles.{i}"
            if puzzle.theme not in self.themes:
                add("reference_unknown", f"No theme has the ID {puzzle.theme!r}.",
                    path=f"{path}.theme", subjects=(puzzle.theme,))  # fmt: skip
            settings = None
            if puzzle.level is None:
                if doc.difficulty.levels:
                    add("puzzle_level_missing", f"Puzzle {puzzle.id} has no level.",
                        path=f"{path}.level", subjects=(puzzle.id,))  # fmt: skip
            elif puzzle.level not in self.level_by_id:
                add("reference_unknown", f"No level has the ID {puzzle.level!r}.",
                    path=f"{path}.level", subjects=(puzzle.level,))  # fmt: skip
            else:
                settings = self.level_by_id[puzzle.level]
            if not puzzle.words:
                add("puzzle_words_missing", f"Puzzle {puzzle.id} has no words assigned.",
                    path=f"{path}.words", subjects=(puzzle.id,))  # fmt: skip
            elif settings is not None:
                expected = settings.level.words
                if not expected.min <= len(puzzle.words) <= expected.max:
                    add(
                        "puzzle_word_count",
                        f"Puzzle {puzzle.id} lists {len(puzzle.words)} words; level "
                        f"{settings.level.label!r} expects {expected.min}-{expected.max}.",
                        path=f"{path}.words",
                        actual=len(puzzle.words),
                        expected=f"{expected.min}-{expected.max}",
                        subjects=(puzzle.id,),
                    )
            pool = self.pool_by_theme.get(puzzle.theme)
            matched: list[WordInfo] = []
            seen_forms: set[str] = set()
            if pool is None:
                if (
                    puzzle.words
                    and puzzle.theme in self.themes
                    and puzzle.theme not in pools_reported
                ):
                    pools_reported.add(puzzle.theme)
                    add("pool_missing", f"Theme {puzzle.theme} has no candidate vocabulary.",
                        path=f"{path}.theme", subjects=(puzzle.theme,))  # fmt: skip
            else:
                entries = pool.by_text()
                for j, text in enumerate(puzzle.words):
                    found = entries.get(text)
                    if found is None:
                        add(
                            "puzzle_word_not_in_pool",
                            f"Puzzle {puzzle.id} lists {text!r}, which is not an entry of the "
                            f"{puzzle.theme} pool.",
                            path=f"{path}.words.{j}",
                            subjects=(puzzle.id, text),
                        )
                        continue
                    if found.search is not None and found.search in seen_forms:
                        add("puzzle_word_repeated", f"Puzzle {puzzle.id} lists {text!r} twice.",
                            path=f"{path}.words.{j}", subjects=(puzzle.id, text))  # fmt: skip
                        continue
                    if found.usable and found.search is not None:
                        seen_forms.add(found.search)
                        matched.append(found)
            self.assigned[i] = matched
            if puzzle.title is not None:
                key = puzzle.title.casefold().strip()
                if key in titles:
                    add(
                        "puzzle_titles_duplicate",
                        f"Puzzles {doc.puzzles[titles[key]].id} and {puzzle.id} share the title "
                        f"{puzzle.title!r}.",
                        path=f"{path}.title",
                        subjects=(doc.puzzles[titles[key]].id, puzzle.id),
                    )
                else:
                    titles[key] = i
        for settings in self.levels:
            if settings.problem == "unknown_profile":
                add(
                    "level_profile_unknown",
                    f"Level {settings.level.label!r} names profile {settings.level.profile!r}, "
                    "which this project does not define.",
                    path=f"{settings.path}.profile",
                    subjects=(settings.level.id,),
                )
            elif settings.problem == "missing":
                add(
                    "level_settings_missing",
                    f"Level {settings.level.label!r} needs a width, a height and at least one "
                    "direction, or an existing project profile.",
                    path=settings.path,
                    subjects=(settings.level.id,),
                )
        # Pools: enough valid words for one puzzle, and within reuse for the allocation.
        minimum_words = min((s.level.words.min for s in self.levels), default=None)
        for t in self.doc.themes:
            pool_info = self.pool_by_theme.get(t.id)
            if pool_info is None or self.allocation(t) == 0:
                continue
            levels = {
                p.level for p in doc.puzzles if p.theme == t.id and p.level in self.level_by_id
            }
            needed = max(
                (self.level_by_id[lv].level.words.min for lv in levels if lv is not None),
                default=minimum_words,
            )
            if needed is None:
                continue
            available = len(pool_info.forms)
            if available < needed:
                add(
                    "pool_insufficient",
                    f"Pool {t.id} has {available} usable words; one puzzle needs {needed}.",
                    path=pool_info.path,
                    actual=available,
                    expected=f"at least {needed}",
                    subjects=(t.id,),
                )
                continue
            slots = self.allocation(t) * (minimum_words or needed)
            capacity = available * self.max_reuse
            if capacity < slots:
                add(
                    "pool_thin",
                    f"Pool {t.id} has {available} usable words for {t.puzzles} puzzles of at "
                    f"least {minimum_words or needed} words; even reusing each word "
                    f"{self.max_reuse} times fills only {capacity} of {slots} places.",
                    path=pool_info.path,
                    actual=available,
                    expected=f"at least {math.ceil(slots / self.max_reuse)}",
                    subjects=(t.id,),
                )
        for pool_info in self.pools:
            theme = self.themes.get(pool_info.pool.theme)
            if theme is not None and self.allocation(theme) == 0 and not self.specified(theme.id):
                add("pool_unused", f"Pool {theme.id} belongs to a theme with no puzzles.",
                    path=pool_info.path, subjects=(theme.id,))  # fmt: skip
        # Reuse and similarity across planned puzzles: the batch quality measures.
        planned = {
            doc.puzzles[i].id: frozenset(w.search for w in matched_words if w.search)
            for i, matched_words in self.assigned.items()
        }
        usage: dict[str, list[str]] = {}
        for puzzle_id, word_forms in planned.items():
            for word in sorted(word_forms):
                usage.setdefault(word, []).append(puzzle_id)
        for word, ids in sorted(usage.items()):
            if len(ids) > self.max_reuse:
                add(
                    "word_reuse",
                    f"{word} is planned in {len(ids)} puzzles; the reuse limit is "
                    f"{self.max_reuse}.",
                    actual=len(ids),
                    expected=f"at most {self.max_reuse}",
                    subjects=(word, *ids),
                )
        threshold = QUALITY_DEFAULTS.target_similarity_threshold
        for (a, left), (b, right) in combinations(planned.items(), 2):
            if not left or not right:
                continue
            similarity = compare_target_sets(a, b, left, right)
            if similarity.identical_targets:
                add("duplicate_word_sets", f"Puzzles {a} and {b} plan identical word sets.",
                    subjects=(a, b))  # fmt: skip
            elif similarity.target_jaccard >= threshold:
                add(
                    "similar_word_sets",
                    f"Puzzles {a} and {b} share {len(similarity.shared_words)} words "
                    f"(Jaccard {similarity.target_jaccard:.2f}).",
                    actual=round(similarity.target_jaccard, 3),
                    expected=f"below {threshold}",
                    subjects=(a, b),
                )

    def _progression(self) -> None:
        add = self.findings.add
        strategy = self.doc.difficulty.strategy
        sequence = [
            (i, puzzle, self.level_by_id[puzzle.level])
            for i, puzzle in enumerate(self.doc.puzzles)
            if puzzle.level in self.level_by_id
        ]
        used = {settings.level.id for _, _, settings in sequence}
        if self.doc.puzzles:
            for settings in self.levels:
                if settings.level.id not in used:
                    add("level_unused", f"No planned puzzle uses level {settings.level.label!r}.",
                        path=settings.path, subjects=(settings.level.id,))  # fmt: skip
        if len(sequence) >= 2:
            ranks = [settings.rank for _, _, settings in sequence]
            if strategy is Strategy.CONSISTENT and len(set(ranks)) > 1:
                names = [s.level.label for s in self.levels if s.level.id in used]
                add(
                    "progression_contradicts_strategy",
                    "The strategy is consistent difficulty, but planned puzzles use "
                    f"{len(names)} levels: {', '.join(names)}.",
                    path="difficulty.strategy",
                    actual=len(names),
                    expected=1,
                )
            elif strategy is Strategy.GRADUAL:
                for (_, before, a), (i, puzzle, b) in zip(sequence, sequence[1:], strict=False):
                    if b.rank < a.rank:
                        add(
                            "progression_contradicts_strategy",
                            f"The strategy is gradual, but puzzle {puzzle.id} "
                            f"({b.level.label}) follows {before.id} ({a.level.label}), "
                            "an easier level after a harder one.",
                            path=f"puzzles.{i}.level",
                            subjects=(before.id, puzzle.id),
                        )
                    elif b.rank - a.rank >= 2:
                        add(
                            "difficulty_jump",
                            f"Puzzle {puzzle.id} moves from {a.level.label} to "
                            f"{b.level.label}, skipping {b.rank - a.rank - 1} level(s).",
                            path=f"puzzles.{i}.level",
                            subjects=(before.id, puzzle.id),
                        )
            elif strategy is Strategy.SECTIONS:
                blocks: list[int] = []
                for rank in ranks:
                    if not blocks or blocks[-1] != rank:
                        blocks.append(rank)
                repeated = sorted({rank for rank in blocks if blocks.count(rank) > 1})
                if repeated:
                    labels = [s.level.label for s in self.levels if s.rank in repeated]
                    add(
                        "progression_contradicts_strategy",
                        "The strategy is sections by difficulty, but level(s) "
                        f"{', '.join(labels)} appear in more than one section.",
                        path="puzzles",
                    )
                elif blocks != sorted(blocks):
                    add(
                        "sections_out_of_order",
                        "Difficulty sections do not run from the easiest level to the hardest.",
                        path="puzzles",
                    )
        # Declared order: a harder level that measures no harder on any setting.
        for a, b in zip(self.levels, self.levels[1:], strict=False):
            if a.config is None or b.config is None:
                continue
            area = (a.config.size.width * a.config.size.height,
                    b.config.size.width * b.config.size.height)  # fmt: skip
            if (
                area[1] <= area[0]
                and set(b.config.directions) <= set(a.config.directions)
                and b.level.words.max <= a.level.words.max
            ):
                add(
                    "level_order_inverted",
                    f"Level {b.level.label!r} comes after {a.level.label!r} but has no larger "
                    "grid, no new direction and no more words. Grid size, directions and word "
                    "count are only some influences on difficulty.",
                    path=b.path,
                    subjects=(a.level.id, b.level.id),
                )

    def _decisions(self) -> None:
        add = self.findings.add
        s = self.doc.structure
        if s.print_profile is None:
            add(
                "print_profile_undecided",
                "Choose the print profile: trim and paper. Paper is never assumed.",
                path="structure.print_profile",
            )
        if s.solutions is SolutionsPlan.UNDECIDED:
            add("solutions_undecided", "Decide whether solutions print at the end or not at all.",
                path="structure.solutions")  # fmt: skip
        elif s.solutions is SolutionsPlan.END and s.solutions_per_page is None:
            add("solutions_undecided", "Decide how many solutions share a page: 1, 2, 4 or 6.",
                path="structure.solutions_per_page")  # fmt: skip
        unknown: dict[str, list[str]] = {}
        for matched_words in self.assigned.values():
            for word in matched_words:
                if word.source is WordSource.UNKNOWN:
                    unknown.setdefault(word.theme, [])
                    if word.word not in unknown[word.theme]:
                        unknown[word.theme].append(word.word)
        for theme, unknown_words in sorted(unknown.items()):
            add(
                "provenance_unknown",
                f"{_plural(len(unknown_words), 'assigned word')} in {theme} record no source.",
                path=self.pool_by_theme[theme].path,
                subjects=tuple(unknown_words),
                action="Record where these words came from: human, public reference, "
                "licensed, AI-assisted or AI-generated.",
            )

    def _editorial(self) -> None:
        add = self.findings.add
        p = self.doc.positioning
        if p.familiarity is Familiarity.UNDECIDED:
            add(
                "familiarity_undecided",
                "State how familiar readers are with the subject; vocabulary is hard to judge "
                "without it.",
                path="positioning.familiarity",
            )
        if (
            p.primary_audience is not None
            and p.secondary_audience is not None
            and p.primary_audience.casefold() == p.secondary_audience.casefold()
        ):
            add("audience_repeated", "The secondary audience repeats the primary audience.",
                path="positioning.secondary_audience")  # fmt: skip
        texts: list[tuple[str, str | None]] = [
            ("concept.summary", self.doc.concept.summary),
            ("positioning.main_benefit", p.main_benefit),
            ("positioning.differentiation", p.differentiation),
            *((f"positioning.claims.{i}.text", c.text) for i, c in enumerate(p.claims)),
        ]
        for path, text in texts:
            if text is None:
                continue
            found = first(PROMOTIONAL, text) or first(SUPERLATIVE, text)
            if found:
                add(
                    "promotional_language",
                    f"{found!r} reads as a promotional or superlative claim. A plan states "
                    "intent; claims need evidence.",
                    path=path,
                    actual=found,
                )

    # ------------------------------------------------------------------ views

    def allocation_view(self) -> list[dict[str, object]]:
        total = sum(self.allocation(t) for t in self.doc.themes)

        def depth(theme: Theme) -> int:
            level, current, seen = 0, theme.parent, {theme.id}
            while current in self.themes and current not in seen:
                seen.add(current)
                level += 1
                current = self.themes[current].parent
            return level

        return [
            {
                "id": t.id,
                "label": t.label,
                "parent": t.parent,
                "depth": depth(t),
                "required": t.required,
                "allocated": t.puzzles,
                "specified": self.specified(t.id),
                "share": round(self.allocation(t) / total, 4) if total else None,
            }
            for t in self.doc.themes
        ]

    def levels_view(self) -> list[dict[str, object]]:
        return [
            {
                "id": s.level.id,
                "label": s.level.label,
                "rank": s.rank,
                "origin": s.origin,
                "profile": s.level.profile,
                "width": s.width,
                "height": s.height,
                "directions": [direction_name(d) for d in s.directions],
                "words": s.level.words.to_dict(),
                "puzzles": sum(p.level == s.level.id for p in self.doc.puzzles),
                "supported": s.config is not None,
            }
            for s in self.levels
        ]

    def progression_view(self) -> list[dict[str, object]]:
        return [
            {
                "id": puzzle.id,
                "title": puzzle.title,
                "theme": puzzle.theme,
                "level": puzzle.level,
                "rank": self.level_by_id[puzzle.level].rank
                if puzzle.level in self.level_by_id
                else None,
                "words": len(puzzle.words),
            }
            for puzzle in self.doc.puzzles
        ]

    def vocabulary_view(self) -> list[dict[str, object]]:
        shared: dict[str, int] = {}
        for info in self.pools:
            for form in info.forms:
                shared[form] = shared.get(form, 0) + 1
        assigned: dict[str, set[str]] = {}
        for matched_words in self.assigned.values():
            for word in matched_words:
                if word.search:
                    assigned.setdefault(word.theme, set()).add(word.search)
        rows: list[dict[str, object]] = []
        for info in self.pools:
            sources: dict[str, int] = {}
            for word in info.words:
                sources[word.source.value] = sources.get(word.source.value, 0) + 1
            rows.append(
                {
                    "theme": info.pool.theme,
                    "label": self.themes[info.pool.theme].label
                    if info.pool.theme in self.themes
                    else None,
                    "entries": len(info.words),
                    "usable": len(info.forms),
                    "invalid": sum(w.search is None for w in info.words),
                    "duplicates": sum(w.duplicate_of is not None for w in info.words),
                    "shared": sum(shared[f] > 1 for f in info.forms),
                    "assigned": len(assigned.get(info.pool.theme, set())),
                    "sources": dict(sorted(sources.items())),
                    "words": [
                        {
                            "word": w.word,
                            "search": w.search,
                            "source": w.source.value,
                            "valid": w.search is not None,
                            "duplicate": w.duplicate_of is not None,
                            "shared": w.search is not None and shared.get(w.search, 0) > 1,
                        }
                        for w in info.words
                    ],
                }
            )
        return rows

    def research_view(self) -> dict[str, object]:
        kinds = {kind.value: 0 for kind in Evidence}
        for note in self.doc.research:
            kinds[note.evidence.value] += 1
        return {
            "notes": len(self.doc.research),
            "evidence": kinds,
            "questions": len(self.doc.questions),
            "open_questions": sum(q.resolution is None for q in self.doc.questions),
            "blocking_questions": sum(
                q.resolution is None and q.blocking for q in self.doc.questions
            ),
            "comparables": len(self.doc.comparables),
            "sourced_comparables": sum(
                c.url is not None or c.citation is not None for c in self.doc.comparables
            ),
        }
