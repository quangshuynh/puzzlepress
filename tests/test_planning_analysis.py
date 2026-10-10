"""Planning diagnostics: definition, research, coverage, vocabulary, difficulty,
feasibility, decisions and editorial review. Each case changes one thing in a
complete plan and checks the exact finding codes, values and gates."""

import copy
from dataclasses import replace

import pytest
from planning_helpers import ENGINE_WORDS, ROOT, codes, complete_plan, evaluate, variant

from puzzlepress import load_project
from puzzlepress.planning import State, report_bytes
from puzzlepress.planning.readiness import PlanningReadinessReport
from puzzlepress.planning.rules import Gate


def finding(report: PlanningReadinessReport, code: str) -> dict[str, object]:
    found = [f.to_dict() for f in report.findings if f.rule.code == code]
    assert found, (code, codes(report))
    return found[0]


def item(report: PlanningReadinessReport, code: str) -> dict[str, object]:
    return next(i.to_dict() for i in report.feasibility if i.code == code)


def test_complete_plan_is_clean_and_ready() -> None:
    report = evaluate(complete_plan())
    assert report.state is State.READY_FOR_APPROVAL
    assert report.findings == ()
    assert all(gate.passed for gate in report.gates)


def test_empty_plan_is_a_draft_with_every_missing_definition() -> None:
    report = evaluate({"planning_version": 1})
    assert report.state is State.DRAFT
    definition = {f.rule.code for f in report.findings if f.rule.gate is Gate.DEFINITION}
    assert definition == {
        "concept_missing",
        "subject_missing",
        "audience_missing",
        "differentiation_missing",
        "puzzle_type_missing",
        "target_missing",
        "strategy_undecided",
        "themes_missing",
        "levels_missing",
    }
    assert [g.gate.value for g in report.gates if not g.passed] == ["definition", "decisions"]


def test_candidate_audiences_are_not_a_chosen_audience() -> None:
    report = evaluate(variant(positioning__primary_audience=None))
    assert report.state is State.DRAFT
    assert "Candidate audiences are not a choice" in str(finding(report, "audience_missing"))


# ----------------------------------------------------------------- research


def test_blocking_questions_block_research_and_open_ones_are_notes() -> None:
    data = complete_plan()
    data["questions"] = [
        {"id": "q1", "question": "Which audience?", "blocking": True},
        {"id": "q2", "question": "Cream paper?"},
    ]
    report = evaluate(data)
    assert report.state is State.NEEDS_RESEARCH
    assert finding(report, "question_blocking_open")["path"] == "questions.0.resolution"
    assert finding(report, "question_open")["severity"] == "info"


def test_sourced_evidence_must_cite_and_verified_should_be_dated() -> None:
    note = copy.deepcopy(complete_plan()["research"][0])  # type: ignore[index]
    note["source"] = {"citation": None, "url": None, "type": None}
    report = evaluate(variant(research=[note]))
    assert report.state is State.NEEDS_RESEARCH
    assert finding(report, "evidence_source_missing")["subjects"] == ["r-test"]
    note = copy.deepcopy(complete_plan()["research"][0])  # type: ignore[index]
    note["observed"] = None
    note["source"]["url"] = "kdp help page"
    report = evaluate(variant(research=[note]))
    assert {"evidence_undated", "source_url_format"} <= codes(report)
    assert report.state is State.READY_FOR_APPROVAL  # Warnings never block.


def test_unverified_notes_are_never_reported_as_verified() -> None:
    note = copy.deepcopy(complete_plan()["research"][0])  # type: ignore[index]
    note["evidence"] = "unknown"
    report = evaluate(variant(research=[note]))
    assert report.to_dict()["research"]["evidence"]["unknown"] == 1  # type: ignore[index]
    assert report.to_dict()["research"]["evidence"]["verified_source"] == 0  # type: ignore[index]
    assert "assumption_unresolved" in codes(report)  # The positioning relies on it.


@pytest.mark.parametrize(
    ("evidence", "expected"),
    [
        ("hypothesis", True),
        ("unknown", True),
        ("preference", False),  # A preference is a valid basis for the author's own decision.
        ("author_observation", False),
    ],
)
def test_decisions_resting_on_hypotheses_are_flagged(evidence: str, expected: bool) -> None:
    note = {
        "id": "r2",
        "observation": "Readers like engines.",
        "evidence": evidence,
        "decision": "Lead with engines.",
    }
    data = complete_plan()
    data["research"].append(note)  # type: ignore[union-attr]
    report = evaluate(data)
    flagged = any(
        f.rule.code == "assumption_unresolved" and f.path == "research.1.decision"
        for f in report.findings
    )
    assert flagged is expected


def test_claims_need_verified_evidence() -> None:
    data = complete_plan()
    data["research"].append(  # type: ignore[union-attr]
        {"id": "r-obs", "observation": "Seen once.", "evidence": "author_observation"}
    )
    data["research"].append(  # type: ignore[union-attr]
        {"id": "r-pref", "observation": "I like it.", "evidence": "preference"}
    )
    for evidence, code in (
        (["r-test"], None),
        (["r-obs"], "claim_weak_evidence"),
        (["r-pref"], "claim_unsupported"),
        ([], "claim_unsupported"),
    ):
        variant_data = copy.deepcopy(data)
        variant_data["positioning"]["claims"] = [  # type: ignore[index]
            {"text": "Covers every workshop tool.", "evidence": evidence}
        ]
        report = evaluate(variant_data)
        claim_codes = codes(report) & {"claim_weak_evidence", "claim_unsupported"}
        assert claim_codes == ({code} if code else set()), evidence
    variant_data = copy.deepcopy(data)
    variant_data["positioning"]["claims"] = [{"text": "x", "evidence": ["nope"]}]  # type: ignore[index]
    assert finding(evaluate(variant_data), "reference_unknown")["path"] == (
        "positioning.claims.0.evidence.0"
    )


def test_comparables_must_be_sourced_and_prices_dated() -> None:
    report = evaluate(
        variant(
            comparables=[
                {"id": "c1", "title": "Some book", "price": {"amount": "9.99", "currency": "USD"}}
            ]
        )
    )
    assert report.state is State.NEEDS_RESEARCH
    assert {"comparable_unsourced", "comparable_price_undated"} <= codes(report)
    report = evaluate(
        variant(
            comparables=[
                {
                    "id": "c1",
                    "title": "Some book",
                    "citation": "Seen in a shop",
                    "observed": "2026-10-01",
                    "price": {"amount": "9.99", "currency": "USD"},
                }
            ]
        )
    )
    assert report.state is State.READY_FOR_APPROVAL


# ----------------------------------------------------------------- allocation and themes


def test_allocations_must_reconcile_with_the_target() -> None:
    report = evaluate(variant(themes__1__puzzles=5))
    f = finding(report, "allocation_total_mismatch")
    assert (f["actual"], f["expected"]) == (11, 12)
    assert report.state is State.NEEDS_CONTENT
    report = evaluate(variant(themes__1__puzzles=None))
    assert "allocation_missing" in codes(report)
    assert "allocation_total_mismatch" not in codes(report)


def test_required_and_empty_themes() -> None:
    data = complete_plan()
    data["themes"].append({"id": "history", "label": "History", "required": True, "puzzles": 0})  # type: ignore[union-attr]
    data["themes"].append({"id": "racing", "label": "Racing", "puzzles": 0})  # type: ignore[union-attr]
    report = evaluate(data)
    assert finding(report, "required_theme_empty")["subjects"] == ["history"]
    assert finding(report, "theme_without_puzzles")["subjects"] == ["racing"]


def test_parent_themes_hold_children_and_cycles_are_reported() -> None:
    data = complete_plan()
    data["themes"].insert(0, {"id": "auto", "label": "Automotive", "required": True})  # type: ignore[union-attr]
    for theme in data["themes"][1:]:  # type: ignore[index]
        theme["parent"] = "auto"
    report = evaluate(data)
    assert report.state is State.READY_FOR_APPROVAL  # Parent needs no own allocation.
    assert report.to_dict()["allocation"][1]["depth"] == 1  # type: ignore[index]
    data["themes"][0]["parent"] = "engines"  # type: ignore[index]
    report = evaluate(data)
    assert "theme_cycle" in codes(report)
    data["themes"][0]["parent"] = "nowhere"  # type: ignore[index]
    assert finding(evaluate(data), "reference_unknown")["path"] == "themes.0.parent"


def test_theme_label_duplicates_are_structural_and_similarity_is_editorial() -> None:
    report = evaluate(variant(themes__1__label="engines"))
    assert finding(report, "theme_label_duplicate")["severity"] == "error"
    data = complete_plan()
    data["themes"][0]["label"] = "Tools & Workshop"  # type: ignore[index]
    data["themes"][1]["label"] = "tools and  workshop"  # type: ignore[index]
    assert "theme_label_duplicate" in codes(evaluate(data))  # Case, "&"/"and", spacing.
    data["themes"][1]["label"] = "Workshop and Tool"  # type: ignore[index]
    report = evaluate(data)
    assert "theme_label_duplicate" not in codes(report)
    assert finding(report, "theme_labels_similar")["severity"] == "warning"
    assert report.state is State.READY_FOR_APPROVAL


def test_balance_heuristics() -> None:
    data = complete_plan()
    data["structure"]["target_puzzles"] = 20  # type: ignore[index]
    data["themes"][0]["puzzles"] = 6  # type: ignore[index]
    data["themes"][1]["puzzles"] = 6  # type: ignore[index]
    data["themes"].append({"id": "a", "label": "Alpha", "puzzles": 1})  # type: ignore[union-attr]
    data["themes"].append({"id": "b", "label": "Bravo", "puzzles": 7})  # type: ignore[union-attr]
    report = evaluate(data)
    assert finding(report, "theme_thin")["subjects"] == ["a"]
    data["themes"][3]["puzzles"] = 30  # type: ignore[index]
    data["structure"]["target_puzzles"] = 43  # type: ignore[index]
    assert finding(evaluate(data), "theme_overrepresented")["subjects"] == ["b"]


# ----------------------------------------------------------------- vocabulary


def pools(*entries: str, theme: str = "engines") -> dict[str, object]:
    data = complete_plan()
    pool = data["vocabulary"][0 if theme == "engines" else 1]  # type: ignore[index]
    pool["entries"] += [{"word": w} for w in entries]
    return data


def test_invalid_words_are_findings_with_the_engine_message() -> None:
    report = evaluate(pools("O-RING", "4WD", "CAFÉ", "A" * 51))
    invalid = [f for f in report.findings if f.rule.code == "word_invalid"]
    assert [f.actual for f in invalid] == ["O-RING", "4WD", "CAFÉ", "A" * 51]
    assert "ASCII letters and spaces" in invalid[0].message
    assert "at most 50 letters" in invalid[3].message
    assert report.state is State.NEEDS_CONTENT
    assert report.document.vocabulary[0].entries[-4].word == "O-RING"  # Never replaced.


def test_normalization_collisions_and_duplicates() -> None:
    report = evaluate(pools("FUEL PUMP", "fuelpump", "Piston"))
    dupes = [f for f in report.findings if f.rule.code == "word_duplicate"]
    assert [(f.actual, f.subjects) for f in dupes] == [
        ("FUELPUMP", ("fuelpump",)),
        ("PISTON", ("Piston",)),
    ]


def test_cross_theme_reuse_is_a_note_not_an_error() -> None:
    report = evaluate(pools("WRENCH"))
    f = finding(report, "word_cross_theme")
    assert f["severity"] == "info" and f["subjects"] == ["WRENCH", "engines", "tools"]
    assert report.state is State.READY_FOR_APPROVAL


def test_prohibited_and_length_constraints() -> None:
    data = pools("ASSEMBLY", "BADWORD", "CAM")
    data["constraints"]["prohibited_words"] = ["badword", "ass"]  # type: ignore[index]
    data["constraints"]["max_letters"] = 9  # type: ignore[index]
    data["constraints"]["min_letters"] = 4  # type: ignore[index]
    report = evaluate(data)
    assert finding(report, "word_prohibited")["subjects"] == ["BADWORD"]
    assert finding(report, "word_contains_prohibited")["subjects"] == ["ASSEMBLY"]
    assert finding(report, "word_short")["subjects"] == ["CAM"]
    long_words = [f.subjects[0] for f in report.findings if f.rule.code == "word_long"]
    assert long_words and all(len(w.replace(" ", "")) > 9 for w in long_words)


def test_project_prohibited_words_also_apply() -> None:
    garden = load_project(ROOT / "books" / "garden-demo").project
    assert garden.word_search is not None
    quality = replace(garden.word_search.quality, prohibited_words=("BADWORD",))
    policy = replace(garden, word_search=replace(garden.word_search, quality=quality))
    assert finding(evaluate(pools("BADWORD"), against=policy), "word_prohibited")
    assert "word_prohibited" not in codes(evaluate(pools("BADWORD"), against=garden))


def test_pools_must_fill_puzzles() -> None:
    data = complete_plan()
    data["vocabulary"][0]["entries"] = [{"word": w} for w in ENGINE_WORDS[:3]]  # type: ignore[index]
    data["puzzles"] = [p for p in data["puzzles"] if p["theme"] != "engines"]  # type: ignore[union-attr]
    data["themes"][0]["puzzles"] = 6  # type: ignore[index]
    report = evaluate(data)
    f = finding(report, "pool_insufficient")
    assert (f["actual"], f["expected"]) == (3, "at least 4")
    data["vocabulary"][0]["entries"] = [{"word": w} for w in ENGINE_WORDS[:10]]  # type: ignore[index]
    f = finding(evaluate(data), "pool_thin")
    assert (f["actual"], f["expected"]) == (10, "at least 12")
    data["vocabulary"].pop(0)  # type: ignore[union-attr]
    assert "pool_missing" in codes(evaluate(data))


def test_provenance_is_required_for_assigned_words_only() -> None:
    data = complete_plan()
    data["vocabulary"][0]["source"] = "unknown"  # type: ignore[index]
    report = evaluate(data)
    assert report.state is State.PRODUCTION_FEASIBLE
    f = finding(report, "provenance_unknown")
    assert f["gate"] == "decisions" and len(f["subjects"]) == 24  # type: ignore[arg-type]
    data["puzzles"] = [p for p in data["puzzles"] if p["theme"] != "engines"]  # type: ignore[union-attr]
    assert "provenance_unknown" not in codes(evaluate(data))


def test_ai_and_licensed_provenance_are_recorded_honestly() -> None:
    data = complete_plan()
    data["vocabulary"][0]["source"] = "ai_generated"  # type: ignore[index]
    data["vocabulary"][1]["entries"][0]["source"] = "licensed"  # type: ignore[index]
    report = evaluate(data)
    assert finding(report, "vocabulary_ai_generated")["actual"] == 24
    assert finding(report, "licensed_unreferenced")["subjects"] == ["WRENCH"]
    sources = report.to_dict()["vocabulary"][0]["sources"]  # type: ignore[index]
    assert sources == {"ai_generated": 24}
    assert report.state is State.READY_FOR_APPROVAL


# ----------------------------------------------------------------- puzzles


def test_puzzle_specification_counts() -> None:
    data = complete_plan()
    data["puzzles"] = data["puzzles"][:5]  # type: ignore[index]
    f = finding(evaluate(data), "puzzles_unspecified")
    assert (f["actual"], f["expected"]) == (5, 12)
    data = complete_plan()
    data["structure"]["target_puzzles"] = 10  # type: ignore[index]
    data["themes"][1]["puzzles"] = 4  # type: ignore[index]
    report = evaluate(data)
    assert {"puzzles_exceed_target", "theme_overspecified"} <= codes(report)


def test_puzzle_words_levels_and_references() -> None:
    data = complete_plan()
    puzzles = data["puzzles"]
    puzzles[0]["level"] = None  # type: ignore[index]
    puzzles[1]["words"] = []  # type: ignore[index]
    puzzles[2]["words"] = puzzles[2]["words"][:2]  # type: ignore[index]
    puzzles[3]["words"][0] = "NOT IN POOL"  # type: ignore[index]
    puzzles[4]["words"][1] = puzzles[4]["words"][0]  # type: ignore[index]
    puzzles[5]["theme"] = "nowhere"  # type: ignore[index]
    puzzles[6]["level"] = "nowhere"  # type: ignore[index]
    report = evaluate(data)
    found = codes(report)
    assert {
        "puzzle_level_missing",
        "puzzle_words_missing",
        "puzzle_word_count",
        "puzzle_word_not_in_pool",
        "puzzle_word_repeated",
        "reference_unknown",
    } <= found
    f = finding(report, "puzzle_word_count")
    assert (f["actual"], f["expected"]) == (2, "4-6")


def test_reuse_and_similarity_use_the_quality_measures() -> None:
    data = complete_plan()
    same = data["puzzles"][0]["words"]  # type: ignore[index]
    data["puzzles"][1]["words"] = list(same)  # type: ignore[index]
    data["puzzles"][2]["words"] = list(same)  # type: ignore[index]
    data["puzzles"][1]["title"] = data["puzzles"][0]["title"]  # type: ignore[index]
    report = evaluate(data)
    reuse = finding(report, "word_reuse")
    assert reuse["actual"] == 3 and reuse["expected"] == "at most 2"
    assert {"duplicate_word_sets", "puzzle_titles_duplicate"} <= codes(report)
    data["puzzles"][2]["words"] = [*same[:3], ENGINE_WORDS[20]]  # type: ignore[index]
    data["puzzles"][1]["words"] = [*same, ENGINE_WORDS[21]]  # type: ignore[index]
    data["puzzles"][1]["level"] = "hard"  # type: ignore[index]
    assert "similar_word_sets" in codes(evaluate(data))


# ----------------------------------------------------------------- difficulty


def levels_in_order(*levels: str, strategy: str) -> PlanningReadinessReport:
    data = complete_plan()
    data["difficulty"]["strategy"] = strategy  # type: ignore[index]
    for puzzle, level in zip(data["puzzles"], levels, strict=True):  # type: ignore[arg-type]
        puzzle["level"] = level
    return evaluate(data)


EASY_THEN_HARD = ("easy",) * 6 + ("hard",) * 6
ALTERNATING = ("easy", "hard") * 6


def test_progression_follows_the_strategy() -> None:
    assert levels_in_order(*EASY_THEN_HARD, strategy="gradual").state is State.READY_FOR_APPROVAL
    assert levels_in_order(*EASY_THEN_HARD, strategy="sections").state is State.READY_FOR_APPROVAL
    assert levels_in_order(*ALTERNATING, strategy="mixed").state is State.READY_FOR_APPROVAL
    for strategy, order in (
        ("gradual", ALTERNATING),
        ("sections", ALTERNATING),
        ("consistent", EASY_THEN_HARD),
    ):
        report = levels_in_order(*order, strategy=strategy)
        assert "progression_contradicts_strategy" in codes(report), strategy
        assert report.state is State.NEEDS_CONTENT
    report = levels_in_order(*(("hard",) * 6 + ("easy",) * 6), strategy="sections")
    assert codes(report) == {"sections_out_of_order"}
    assert levels_in_order(*("easy",) * 12, strategy="consistent").state is State.READY_FOR_APPROVAL


def test_jumps_unused_and_inverted_levels() -> None:
    data = complete_plan()
    data["difficulty"]["levels"].insert(
        1,
        {
            "id": "mid",
            "label": "Middle",
            "width": 11,  # type: ignore[union-attr]
            "height": 11,
            "directions": ["right", "down"],
            "words": {"min": 4, "max": 7},
        },
    )
    report = evaluate(data)
    assert finding(report, "difficulty_jump")["subjects"] == ["tools-3", "engines-4"]
    assert finding(report, "level_unused")["subjects"] == ["mid"]
    data["difficulty"]["levels"][1] = {
        "id": "mid",
        "label": "Middle",
        "width": 9,
        "height": 9,  # type: ignore[index]
        "directions": ["right"],
        "words": {"min": 4, "max": 5},
    }
    f = finding(evaluate(data), "level_order_inverted")
    assert f["severity"] == "warning" and "only some influences" in str(f["message"])


def test_levels_can_reuse_existing_project_profiles() -> None:
    garden = load_project(ROOT / "books" / "garden-demo").project
    assert garden.word_search is not None
    profile = garden.word_search.profiles[0]
    data = complete_plan()
    data["difficulty"]["levels"][0] = {
        "id": "easy",
        "label": "Easy",
        "profile": profile.id,  # type: ignore[index]
        "words": {"min": 4, "max": 6},
    }
    report = evaluate(data, against=garden)
    level = report.to_dict()["levels"][0]  # type: ignore[index]
    assert level["origin"] == "profile" and level["width"] == profile.config.size.width
    assert "level_profile_unknown" not in codes(report)
    assert "level_profile_unknown" in codes(evaluate(data))  # automotive has no profiles.
    data["difficulty"]["levels"][0] = {"id": "easy", "label": "Easy", "words": {"min": 4, "max": 6}}  # type: ignore[index]
    assert "level_settings_missing" in codes(evaluate(data))


# ----------------------------------------------------------------- feasibility


def test_puzzle_count_above_the_cap_is_described_but_unsupported() -> None:
    data = complete_plan()
    data["structure"]["target_puzzles"] = 120  # type: ignore[index]
    data["themes"][1]["puzzles"] = 114  # type: ignore[index]
    report = evaluate(data)
    f = finding(report, "puzzle_count_unsupported")
    assert (f["actual"], f["expected"]) == (120, "at most 100")
    assert item(report, "puzzle_count")["status"] == "unsupported"
    assert report.document.structure.target_puzzles == 120  # Never lowered.
    assert report.state is State.NEEDS_CONTENT  # 108 puzzles are also unspecified.
    data["structure"]["target_puzzles"] = 100  # type: ignore[index]
    data["themes"][1]["puzzles"] = 94  # type: ignore[index]
    assert item(evaluate(data), "puzzle_count")["status"] == "verified"


def test_unsupported_grids_words_and_print_sizes() -> None:
    data = complete_plan()
    level = data["difficulty"]["levels"][1]  # type: ignore[index]
    data["difficulty"]["levels"].append({**level, "id": "huge", "label": "Huge", "width": 60})  # type: ignore[union-attr]
    data["difficulty"]["levels"].append(
        {
            **level,
            "id": "big",
            "label": "Big",
            "width": 40,  # type: ignore[union-attr]
            "height": 40,
        }
    )
    data["difficulty"]["levels"].append(
        {
            **level,
            "id": "many",
            "label": "Many",  # type: ignore[union-attr]
            "words": {"min": 4, "max": 150},
        }
    )
    report = evaluate(data)
    assert finding(report, "grid_unsupported")["subjects"] == ["huge"]
    assert finding(report, "grid_print_unsupported")["subjects"] == ["big"]
    assert finding(report, "words_per_puzzle_unsupported")["actual"] == 150
    assert item(report, "puzzle_grids_print")["status"] == "unsupported"
    assert report.state is State.STRUCTURALLY_VALID


def test_solution_density_and_word_fit() -> None:
    data = complete_plan()
    data["structure"]["solutions_per_page"] = 6  # type: ignore[index]
    data["difficulty"]["levels"][1]["width"] = 30  # type: ignore[index]
    data["difficulty"]["levels"][1]["height"] = 30  # type: ignore[index]
    assert "solution_print_unsupported" in codes(evaluate(data))
    data = complete_plan()
    data["difficulty"]["levels"][0]["width"] = 5  # type: ignore[index]
    data["difficulty"]["levels"][0]["height"] = 5  # type: ignore[index]
    report = evaluate(data)
    fit = [f for f in report.findings if f.rule.code == "word_cannot_fit"]
    assert fit and all(len(f.subjects[1].replace(" ", "")) > 5 for f in fit)
    assert item(report, "word_fit")["status"] == "unsupported"


def test_print_profile_type_and_bank_caps() -> None:
    report = evaluate(variant(structure__print_profile="hardcover-6x9"))
    assert finding(report, "print_profile_unsupported")["actual"] == "hardcover-6x9"
    report = evaluate(variant(structure__puzzle_type="crossword"))
    assert "puzzle_type_unsupported" in codes(report)
    data = complete_plan()
    data["structure"]["target_puzzles"] = 12 + 19  # type: ignore[index]
    for n in range(19):
        data["themes"].append({"id": f"t{n}", "label": f"Theme {n}", "puzzles": 1})  # type: ignore[union-attr]
        data["vocabulary"].append(
            {
                "theme": f"t{n}",
                "source": "human",  # type: ignore[union-attr]
                "entries": [{"word": w} for w in ENGINE_WORDS[:6]],
            }
        )
    report = evaluate(data)
    f = finding(report, "bank_count_unsupported")
    assert (f["actual"], f["expected"]) == (21, "at most 20")


@pytest.mark.parametrize(
    ("target", "per_page", "front", "code", "spine"),
    [
        (12, 1, 3, None, "estimate"),  # 28-30 pages.
        (6, 1, 0, "page_estimate_below_minimum", "estimate"),  # At most 14 pages.
        (12, 1, None, None, "estimate"),  # At least 25 with front matter unknown: clears 24.
        (10, 1, None, "page_estimate_uncertain", "estimate"),  # At least 21, maximum unknown.
        (10, 2, 3, "page_estimate_below_minimum", "estimate"),  # 19-21 pages.
    ],
)
def test_page_estimates_are_ranges_against_kdp_constants(
    target: int, per_page: int, front: int | None, code: str | None, spine: str
) -> None:
    data = complete_plan()
    data["structure"].update(  # type: ignore[union-attr]
        target_puzzles=target, solutions_per_page=per_page, front_matter_pages=front
    )
    report = evaluate(data)
    page_codes = codes(report) & {"page_estimate_below_minimum", "page_estimate_uncertain"}
    assert page_codes == ({code} if code else set())
    assert item(report, "page_count")["status"] == "estimate"
    assert item(report, "spine_text")["status"] in {"estimate", "unknown"}


def test_spine_text_and_maximum_page_estimates() -> None:
    data = complete_plan()
    data["structure"]["target_puzzles"] = 60  # type: ignore[index]
    data["themes"][1]["puzzles"] = 54  # type: ignore[index]
    report = evaluate(data)
    assert item(report, "spine_text")["detail"].startswith("Likely")  # type: ignore[union-attr]
    assert report.pages.minimum == 124 and report.pages.maximum == 126
    data["structure"]["target_puzzles"] = 600  # type: ignore[index]
    data["themes"][1]["puzzles"] = 594  # type: ignore[index]
    assert "page_estimate_above_maximum" in codes(evaluate(data))


def test_generation_and_cover_are_always_unknown() -> None:
    report = evaluate(complete_plan())
    assert item(report, "generation")["status"] == "unknown"
    assert item(report, "cover")["status"] == "unknown"


# ----------------------------------------------------------------- decisions and editorial


def test_author_decisions_block_only_their_gate() -> None:
    report = evaluate(variant(structure__print_profile=None))
    assert report.state is State.PRODUCTION_FEASIBLE
    assert "Paper is never assumed" in str(finding(report, "print_profile_undecided")["message"])
    report = evaluate(variant(structure__solutions_per_page=None))
    assert finding(report, "solutions_undecided")["path"] == "structure.solutions_per_page"
    data = complete_plan()
    data["structure"].update(solutions="omit", solutions_per_page=None)  # type: ignore[union-attr]
    assert evaluate(data).pages.parts["solutions"] == 0


def test_editorial_findings_never_block() -> None:
    data = complete_plan()
    data["positioning"].update(  # type: ignore[union-attr]
        familiarity="undecided",
        secondary_audience="adult car enthusiasts",
        main_benefit="The best-selling, ultimate engine puzzle book.",
    )
    report = evaluate(data)
    assert {"familiarity_undecided", "audience_repeated", "promotional_language"} <= codes(report)
    assert finding(report, "promotional_language")["actual"] == "best-selling"
    assert report.state is State.READY_FOR_APPROVAL
    assert all(f.rule.gate is Gate.EDITORIAL for f in report.findings)


def test_report_is_deterministic_and_sorted() -> None:
    data = pools("O-RING", "fuelpump", "FUEL PUMP")
    first = report_bytes(evaluate(data))
    assert first == report_bytes(evaluate(copy.deepcopy(data)))
    report = evaluate(data)
    keys = [f.sort_key() for f in report.findings]
    assert keys == sorted(keys)
    assert b"\r" not in first and first.endswith(b"\n")
