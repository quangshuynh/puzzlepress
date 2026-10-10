"""Production comparison: how the production book in book.yaml relates to its plan.

The handoff (handoff.py) is what an approved plan hands to production. This is
the other direction: an auditable, read-only comparison of the plan with the
production source that was actually written, whatever the plan's state. It
states the planning and production identities side by side, planned versus
produced puzzle counts, theme allocations, level settings against profiles,
each puzzle's title, level and words, vocabulary coverage and provenance, every
deviation, and the decisions that remain open. It generates nothing, writes
nothing and approves nothing: a matching comparison is not a planning approval,
and a plan that is not approved stays visibly so.

Production puzzles are matched to planned ones by ID; a puzzle's theme comes
from its plan entry, so how production groups words into banks is free (one
plan pool may become several banks). Words compare by the engine's search form.
"""

import json

from .. import __version__
from ..identity import build_identity
from ..models import Project
from .model import SolutionsPlan, WordSource
from .readiness import BOUNDARY, PlanningReadinessReport
from .vocabulary import search_form

COMPARISON_VERSION = 1
NOT_COMPARED = (
    "Generation, placement and quality: run `puzzlepress puzzle batch` on the production book.",
    "Page count, layout and KDP checks: the publication plan, interior build and preflight.",
    "Accuracy and suitability of the words themselves: only a person can review them.",
)


class ProductionUnavailable(Exception):
    """The project has no word_search section, so there is no production book to compare."""


def _form(word: str) -> str:
    form, _ = search_form(word)
    return form if form is not None else word


def comparison_document(report: PlanningReadinessReport) -> dict[str, object]:
    project: Project = report.project
    content = project.word_search
    if content is None:
        raise ProductionUnavailable(
            "book.yaml has no word_search section: there is no production book to compare."
        )
    doc = report.document
    deviations: list[dict[str, object]] = []

    def deviate(code: str, message: str, subject: str | None = None, **values: object) -> None:
        deviations.append({"code": code, "message": message, "subject": subject, **values})

    themes = {t.id: t for t in doc.themes}
    planned = {p.id: p for p in doc.puzzles}
    produced = {p.id: p for p in content.puzzles}
    profiles = {p.id: p.config for p in content.profiles}
    level_rows = report.views["levels"]
    assert isinstance(level_rows, list)
    levels = {row["id"]: row for row in level_rows}
    pools = {pool.theme: pool for pool in doc.vocabulary}
    pool_forms = {
        theme: {_form(e.word): (e.word, pool.source_of(e)) for e in pool.entries}
        for theme, pool in pools.items()
    }

    # Counts and order.
    target = doc.structure.target_puzzles
    if target is not None and len(content.puzzles) != target:
        deviate(
            "puzzle_count_differs",
            f"The plan targets {target} puzzles; book.yaml has {len(content.puzzles)}.",
            None,
            planned=target,
            produced=len(content.puzzles),
        )
    for p in doc.puzzles:
        if p.id not in produced:
            deviate("puzzle_missing", f"Planned puzzle {p.id} is not in book.yaml.", p.id)
    for d in content.puzzles:
        if d.id not in planned:
            deviate("puzzle_unplanned", f"Puzzle {d.id} is in book.yaml but not in the plan.", d.id)
    shared_plan = [p.id for p in doc.puzzles if p.id in produced]
    shared_book = [p.id for p in content.puzzles if p.id in planned]
    if shared_plan != shared_book:
        deviate(
            "order_differs",
            "Puzzles shared by the plan and book.yaml are in a different "
            "order; book order is book.yaml's.",
        )

    # Per puzzle.
    words_by_source: dict[str, int] = {source.value: 0 for source in WordSource}
    used_forms: dict[str, set[str]] = {}
    puzzle_rows: list[dict[str, object]] = []
    for order, definition in enumerate(content.puzzles, 1):
        plan_puzzle = planned.get(definition.id)
        entries = content.entries_for(definition)
        forms = [_form(e.display) for e in entries]
        differences: list[str] = []

        def differ(
            code: str,
            message: str,
            ident: str = definition.id,
            found: list[str] = differences,
            **values: object,
        ) -> None:
            found.append(code)
            deviate(code, message, ident, **values)

        row: dict[str, object] = {
            "order": order,
            "id": definition.id,
            "title": definition.title,
            "theme_text": definition.theme,
            "bank": definition.bank,
            "profile": definition.difficulty,
            "words": [e.display for e in entries],
            "planned": None,
        }
        if plan_puzzle is not None:
            row["planned"] = {
                "order": doc.puzzles.index(plan_puzzle) + 1,
                "theme": plan_puzzle.theme,
                "level": plan_puzzle.level,
                "title": plan_puzzle.title,
            }
            if plan_puzzle.title is not None and plan_puzzle.title != definition.title:
                differ(
                    "title_differs",
                    f"Title {definition.title!r} differs from the planned {plan_puzzle.title!r}.",
                    planned=plan_puzzle.title,
                    produced=definition.title,
                )
            if plan_puzzle.level is not None and plan_puzzle.level != definition.difficulty:
                differ(
                    "level_differs",
                    f"Profile {definition.difficulty!r} differs from the "
                    f"planned level {plan_puzzle.level!r}.",
                    planned=plan_puzzle.level,
                    produced=definition.difficulty,
                )
            planned_forms = [_form(w) for w in plan_puzzle.words]
            if planned_forms != forms:
                added = sorted(set(forms) - set(planned_forms))
                removed = sorted(set(planned_forms) - set(forms))
                differ(
                    "words_differ",
                    "Words differ from the plan"
                    + ("" if added or removed else " in order only")
                    + ".",
                    added=added,
                    removed=removed,
                )
            level = levels.get(plan_puzzle.level) if plan_puzzle.level else None
            if level is not None:
                words = level["words"]
                assert isinstance(words, dict)
                if not words["min"] <= len(forms) <= words["max"]:
                    differ(
                        "word_count_outside_level",
                        f"{len(forms)} words are outside the "
                        f"level's {words['min']}..{words['max']}.",
                        produced=len(forms),
                    )
            sources = pool_forms.get(plan_puzzle.theme, {})
            outside = [form for form in forms if form not in sources]
            if outside:
                differ(
                    "word_outside_pool",
                    f"Words not in the {plan_puzzle.theme} pool: " + ", ".join(outside) + ".",
                    words=outside,
                )
            for form in forms:
                origin = sources.get(form)
                words_by_source[(origin[1] if origin else WordSource.UNKNOWN).value] += 1
            used_forms.setdefault(plan_puzzle.theme, set()).update(forms)
        else:
            words_by_source[WordSource.UNKNOWN.value] += len(forms)
        row["differences"] = differences
        puzzle_rows.append(row)

    # Levels against production profiles.
    level_view: list[dict[str, object]] = []
    for row in level_rows:
        config = profiles.get(str(row["id"]))
        settings = None
        if config is not None:
            settings = {
                "width": config.size.width,
                "height": config.size.height,
                "directions": [d.name.lower().replace("_", "-") for d in config.directions],
            }
            expected = {k: row[k] for k in ("width", "height", "directions")}
            if settings != expected:
                deviate(
                    "profile_differs",
                    f"Profile {row['id']} differs from the planned level settings.",
                    str(row["id"]),
                    planned=expected,
                    produced=settings,
                )
        counts = [len(p.target_ids) for p in content.puzzles if p.difficulty == row["id"]]
        level_view.append(
            {
                "id": row["id"],
                "label": row["label"],
                "planned": {
                    k: row[k] for k in ("width", "height", "directions", "words", "puzzles")
                },
                "profile": settings,
                "produced_puzzles": len(counts),
                "produced_words": {"min": min(counts), "max": max(counts)} if counts else None,
            }
        )
        if config is None and row["puzzles"]:
            deviate("profile_missing", f"No production profile named {row['id']}.", str(row["id"]))

    # Theme allocations.
    produced_by_theme: dict[str, int] = {}
    for definition in content.puzzles:
        plan_puzzle = planned.get(definition.id)
        if plan_puzzle is not None:
            produced_by_theme[plan_puzzle.theme] = produced_by_theme.get(plan_puzzle.theme, 0) + 1
    allocation: list[dict[str, object]] = []
    for theme in doc.themes:
        if theme.puzzles is None and theme.id not in produced_by_theme:
            continue
        made = produced_by_theme.get(theme.id, 0)
        allocation.append(
            {
                "theme": theme.id,
                "label": theme.label,
                "allocated": theme.puzzles,
                "planned": sum(p.theme == theme.id for p in doc.puzzles),
                "produced": made,
            }
        )
        if theme.puzzles is not None and made != theme.puzzles:
            deviate(
                "allocation_differs",
                f"{theme.label}: {theme.puzzles} allocated, {made} produced.",
                theme.id,
                planned=theme.puzzles,
                produced=made,
            )

    # Vocabulary coverage.
    banks_by_theme: dict[str, list[str]] = {}
    for definition in content.puzzles:
        plan_puzzle = planned.get(definition.id)
        if plan_puzzle is not None:
            names = banks_by_theme.setdefault(plan_puzzle.theme, [])
            if definition.bank not in names:
                names.append(definition.bank)
    coverage = []
    for pool_theme, pool_words in pool_forms.items():
        used = used_forms.get(pool_theme, set())
        coverage.append(
            {
                "theme": pool_theme,
                "label": themes[pool_theme].label if pool_theme in themes else None,
                "pool_words": len(pool_words),
                "used": len(used & set(pool_words)),
                "unused": [pool_words[f][0] for f in pool_words if f not in used],
                "banks": banks_by_theme.get(pool_theme, []),
            }
        )

    # Book structure against composition.
    structure = doc.structure
    composition = project.composition
    if composition is None:
        deviate("composition_missing", "book.yaml has no composition: no book can be planned.")
    else:
        solutions = composition.solutions
        check: list[tuple[str, object, object]] = [
            ("front_matter_pages", structure.front_matter_pages, len(composition.front_matter)),
            ("back_matter_pages", structure.back_matter_pages, len(composition.back_matter)),
        ]
        if structure.solutions is not SolutionsPlan.UNDECIDED:
            check.append(("solutions", structure.solutions.value, solutions.placement.value))
        if structure.solutions_per_page is not None and solutions.placement.value == "end":
            check.append(("solutions_per_page", structure.solutions_per_page, solutions.per_page))
        for name, plan_value, book_value in check:
            if plan_value is not None and plan_value != book_value:
                deviate(
                    "structure_differs",
                    f"{name}: planned {plan_value}, produced {book_value}.",
                    name,
                    planned=plan_value,
                    produced=book_value,
                )

    approval = report.approval
    open_questions = [q.to_dict() for q in doc.questions if q.resolution is None]
    notes: list[str] = []
    split = {t: b for t, b in banks_by_theme.items() if len(b) > 1}
    if split:
        notes.append(
            "Theme pools split across banks: "
            + "; ".join(f"{t} -> {', '.join(b)}" for t, b in sorted(split.items()))
            + "."
        )
    if structure.print_profile:
        notes.append(
            f"The plan chooses print profile {structure.print_profile}; production "
            "chooses the profile when the interior is built (book build --profile)."
        )
    return {
        "comparison_version": COMPARISON_VERSION,
        "engine_version": __version__,
        "book": {"id": project.book.id, "title": project.book.title},
        "planning": {
            "identity": report.identity,
            "state": report.state.value,
            "approval": approval.to_dict(),
            "approved": report.approved,
            "boundary": BOUNDARY,
        },
        "production": {
            "identity": build_identity(project),
            "puzzles": len(content.puzzles),
            "banks": len(content.banks),
            "profiles": len(content.profiles),
        },
        "counts": {
            "target": target,
            "planned": len(doc.puzzles),
            "produced": len(content.puzzles),
        },
        "themes": allocation,
        "levels": level_view,
        "puzzles": puzzle_rows,
        "vocabulary": {
            "coverage": coverage,
            "produced_words": sum(len(p.target_ids) for p in content.puzzles),
            "distinct_produced_words": len(
                {_form(e.display) for p in content.puzzles for e in content.entries_for(p)}
            ),
            "words_by_source": words_by_source,
            "note": "Sources are the plan's records of origin, not permission. AI-generated "
            "words stay AI-generated after editing.",
        },
        "deviations": deviations,
        "matches_plan": not deviations,
        "notes": notes,
        "open_questions": open_questions,
        "not_compared": list(NOT_COMPARED),
    }


def comparison_bytes(report: PlanningReadinessReport) -> bytes:
    text = json.dumps(
        comparison_document(report), sort_keys=True, indent=2, ensure_ascii=True, allow_nan=False
    )
    return (text + "\n").encode("ascii")
