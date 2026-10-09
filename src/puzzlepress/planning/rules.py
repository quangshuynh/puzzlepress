"""Planning rule catalogue: stable finding codes, what they block, and their basis.

Every rule belongs to one gate. Error rules block their gate; warnings and
notes never block anything. A rule's basis says what kind of statement its
findings are: a hard constraint (the plan contradicts itself, the generator's
input rules, a production cap or a print constant), an evidence-integrity rule,
a decision only the author can make, or an editorial heuristic. Heuristic
findings are prompts for judgment, never measurements of quality.
"""

from dataclasses import dataclass
from enum import StrEnum

from ..preflight.model import Severity

RULESET_ID = "puzzlepress-planning"
RULESET_VERSION = 1


class Gate(StrEnum):
    """Ordered questions a plan answers on its way to approval."""

    DEFINITION = "definition"  # Is the blueprint defined: concept, audience, structure?
    RESEARCH = "research"  # Are blocking questions resolved and evidence attributable?
    CONTENT = "content"  # Is every planned puzzle specified, allocated and filled?
    STRUCTURE = "structure"  # Do references, labels and words satisfy their rules?
    FEASIBILITY = "feasibility"  # Can the current PuzzlePress produce this plan?
    DECISIONS = "decisions"  # Has the author made the decisions only they can make?
    EDITORIAL = "editorial"  # Review prompts. Never blocks.
    APPROVAL = "approval"  # Does a recorded approval cover this plan?


class Basis(StrEnum):
    PLAN_CONSISTENCY = "plan_consistency"  # The plan contradicts itself or is incomplete.
    EVIDENCE_INTEGRITY = "evidence_integrity"  # Research must stay attributable.
    ENGINE_RULE = "engine_rule"  # The word-search generator's input rules.
    PRODUCTION_CAP = "production_cap"  # A current schema cap (docs/book-planning.md).
    PRINT_CONSTANT = "print_constant"  # Print profile geometry and KDP constants.
    QUALITY_MEASURE = "quality_measure"  # The word-search quality measures and defaults.
    AUTHOR_DECISION = "author_decision"  # Only the author can decide.
    EDITORIAL_HEURISTIC = "editorial_heuristic"  # A judgment aid with stated limits.


@dataclass(frozen=True)
class Rule:
    code: str
    gate: Gate
    severity: Severity
    basis: Basis
    title: str

    def to_dict(self) -> dict[str, object]:
        return {
            "code": self.code,
            "gate": self.gate.value,
            "severity": self.severity.value,
            "basis": self.basis.value,
            "title": self.title,
        }


E, W, N = Severity.ERROR, Severity.WARNING, Severity.INFO
D, R, C, S, F, X, ED, A = (
    Gate.DEFINITION,
    Gate.RESEARCH,
    Gate.CONTENT,
    Gate.STRUCTURE,
    Gate.FEASIBILITY,
    Gate.DECISIONS,
    Gate.EDITORIAL,
    Gate.APPROVAL,
)
PC, EV, EN, CAP, PR, QM, AD, H = (
    Basis.PLAN_CONSISTENCY,
    Basis.EVIDENCE_INTEGRITY,
    Basis.ENGINE_RULE,
    Basis.PRODUCTION_CAP,
    Basis.PRINT_CONSTANT,
    Basis.QUALITY_MEASURE,
    Basis.AUTHOR_DECISION,
    Basis.EDITORIAL_HEURISTIC,
)

CATALOGUE = (
    # Definition: what a blueprint must state before anything else is judged.
    Rule("concept_missing", D, E, AD, "The book concept is stated"),
    Rule("subject_missing", D, E, AD, "The subject or niche is stated"),
    Rule("audience_missing", D, E, AD, "A primary audience is chosen"),
    Rule("differentiation_missing", D, E, AD, "What makes the book different is stated"),
    Rule("puzzle_type_missing", D, E, AD, "The puzzle type is stated"),
    Rule("target_missing", D, E, AD, "A target puzzle count is stated"),
    Rule("strategy_undecided", D, E, AD, "A difficulty strategy is chosen"),
    Rule("themes_missing", D, E, PC, "At least one theme is planned"),
    Rule("levels_missing", D, E, PC, "At least one difficulty level is planned"),
    # Research: blocking questions and attributable evidence.
    Rule("question_blocking_open", R, E, AD, "Blocking questions are resolved"),
    Rule("evidence_source_missing", R, E, EV, "Sourced evidence cites its source"),
    Rule("comparable_unsourced", R, E, EV, "Comparable books cite where they were observed"),
    Rule("claim_unsupported", R, E, EV, "Positioning claims cite verified evidence"),
    Rule("evidence_undated", R, W, EV, "Verified sources record when they were observed"),
    Rule("comparable_price_undated", R, W, EV, "Observed prices record when they were observed"),
    Rule("source_url_format", R, W, EV, "Source URLs are web addresses"),
    Rule("claim_weak_evidence", R, W, EV, "Claims rest on verified rather than reported evidence"),
    Rule("assumption_unresolved", R, W, EV, "Decisions do not rest on hypotheses alone"),
    Rule("question_open", R, N, AD, "Open questions"),
    # Content: allocation and planned puzzles.
    Rule("allocation_missing", C, E, PC, "Every theme has a planned allocation"),
    Rule("allocation_total_mismatch", C, E, PC, "Theme allocations add up to the target"),
    Rule("required_theme_empty", C, E, PC, "Required themes receive puzzles"),
    Rule("puzzles_unspecified", C, E, PC, "Every planned puzzle is specified"),
    Rule("puzzles_exceed_target", C, E, PC, "Specified puzzles do not exceed the target"),
    Rule("theme_overspecified", C, E, PC, "Specified puzzles stay within their theme's allocation"),
    Rule("puzzle_level_missing", C, E, PC, "Every planned puzzle has a level"),
    Rule("puzzle_words_missing", C, E, PC, "Every planned puzzle has words"),
    Rule("puzzle_word_count", C, E, PC, "Puzzles have the word count their level expects"),
    Rule("pool_missing", C, E, PC, "Allocated themes have candidate vocabulary"),
    Rule("pool_insufficient", C, E, PC, "Pools hold enough valid words for one puzzle"),
    Rule("level_settings_missing", C, E, PC, "Levels state grid and directions"),
    Rule("progression_contradicts_strategy", C, E, PC, "Level order follows the strategy"),
    # Structure: references, labels and vocabulary rules.
    Rule("reference_unknown", S, E, PC, "References name existing plan items"),
    Rule("theme_cycle", S, E, PC, "Theme parents do not form a cycle"),
    Rule("theme_label_duplicate", S, E, PC, "Theme labels are distinct"),
    Rule("level_profile_unknown", S, E, PC, "Levels name existing project profiles"),
    Rule("word_invalid", S, E, EN, "Words satisfy the generator's input rules"),
    Rule("word_duplicate", S, E, EN, "Words in one pool normalize to distinct forms"),
    Rule("word_prohibited", S, E, QM, "Words are not on the prohibited list"),
    Rule("puzzle_word_not_in_pool", S, E, PC, "Puzzle words come from their theme's pool"),
    Rule("puzzle_word_repeated", S, E, EN, "A puzzle lists each word once"),
    # Feasibility: what the current PuzzlePress can produce.
    Rule("puzzle_type_unsupported", F, E, CAP, "The puzzle type is supported"),
    Rule("puzzle_count_unsupported", F, E, CAP, "The puzzle count is within the project cap"),
    Rule("bank_count_unsupported", F, E, CAP, "Theme pools fit the word-bank cap"),
    Rule("profile_count_unsupported", F, E, CAP, "Levels fit the difficulty-profile cap"),
    Rule("grid_unsupported", F, E, EN, "Level grids are within the generator's limits"),
    Rule("grid_print_unsupported", F, E, PR, "Puzzle grids can print at the minimum letter size"),
    Rule("solution_print_unsupported", F, E, PR, "Solution grids can print at their minimum"),
    Rule("words_per_puzzle_unsupported", F, E, EN, "Word counts are within the generator's limit"),
    Rule("word_cannot_fit", F, E, EN, "Assigned words fit their level's grid"),
    Rule("print_profile_unsupported", F, E, CAP, "The print profile is supported"),
    Rule("page_estimate_below_minimum", F, E, PR, "The planned book reaches KDP's minimum length"),
    Rule("page_estimate_above_maximum", F, E, PR, "The planned book stays within KDP's maximum"),
    Rule("page_estimate_uncertain", F, W, PR, "The page estimate clears KDP's limits"),
    Rule("bank_size_exceeds", F, W, CAP, "Pools fit one word bank"),
    # Decisions only the author can make.
    Rule("print_profile_undecided", X, E, AD, "Print profile (trim and paper) is chosen"),
    Rule("solutions_undecided", X, E, AD, "Solution placement is decided"),
    Rule("provenance_unknown", X, E, AD, "Assigned words record where they came from"),
    # Editorial review: never blocks.
    Rule("theme_labels_similar", ED, W, H, "Theme labels are clearly distinct"),
    Rule("theme_vocabulary_overlap", ED, W, H, "Theme pools do not largely overlap"),
    Rule("theme_overrepresented", ED, W, H, "No theme dominates the allocation"),
    Rule("theme_thin", ED, N, H, "No theme is much thinner than the others"),
    Rule("theme_without_puzzles", ED, W, PC, "Themes receive puzzles"),
    Rule("pool_thin", ED, W, QM, "Pools can fill their puzzles within the reuse limit"),
    Rule("word_reuse", ED, W, QM, "Words stay within the reuse limit"),
    Rule("duplicate_word_sets", ED, W, QM, "Planned puzzles use different word sets"),
    Rule("similar_word_sets", ED, W, QM, "Planned word sets are not too similar"),
    Rule("puzzle_titles_duplicate", ED, W, H, "Planned puzzle titles are distinct"),
    Rule("word_short", ED, W, AD, "Words meet the authored minimum length"),
    Rule("word_long", ED, W, AD, "Words meet the authored maximum length"),
    Rule("word_contains_prohibited", ED, W, QM, "Words do not contain prohibited forms"),
    Rule("word_cross_theme", ED, N, H, "Words shared between themes"),
    Rule("difficulty_jump", ED, W, H, "Gradual plans do not skip levels"),
    Rule("sections_out_of_order", ED, W, H, "Difficulty sections run from easiest to hardest"),
    Rule("level_order_inverted", ED, W, H, "Harder levels differ from easier ones"),
    Rule("level_unused", ED, N, PC, "Every level is used"),
    Rule("familiarity_undecided", ED, W, AD, "Reader familiarity is stated"),
    Rule("audience_repeated", ED, W, H, "Secondary audience differs from the primary"),
    Rule("promotional_language", ED, W, H, "Positioning avoids promotional wording"),
    Rule("vocabulary_ai_generated", ED, N, AD, "AI-generated vocabulary is recorded"),
    Rule("licensed_unreferenced", ED, W, AD, "Licensed vocabulary records its licence"),
    Rule("pool_unused", ED, N, PC, "Pools belong to allocated themes"),
    # Approval.
    Rule("approval_stale", A, W, AD, "Approval covers the current plan"),
    Rule("approval_not_ready", A, W, AD, "Approval is recorded for a ready plan"),
)
RULES = {rule.code: rule for rule in CATALOGUE}
if len(RULES) != len(CATALOGUE):
    raise RuntimeError("Duplicate planning rule code")

Value = int | float | str


@dataclass(frozen=True)
class Finding:
    rule: Rule
    message: str
    path: str | None = None  # planning.yaml path, e.g. themes.2.puzzles.
    actual: Value | None = None
    expected: Value | None = None
    action: str | None = None
    subjects: tuple[str, ...] = ()  # Plan IDs or words the finding is about.

    @property
    def severity(self) -> Severity:
        return self.rule.severity

    def sort_key(self) -> tuple[object, ...]:
        return (
            list(Gate).index(self.rule.gate),
            list(Severity).index(self.rule.severity),
            self.rule.code,
            self.path or "",
            self.subjects,
            self.message,
        )

    def to_dict(self) -> dict[str, object]:
        return {
            "code": self.rule.code,
            "gate": self.rule.gate.value,
            "severity": self.rule.severity.value,
            "basis": self.rule.basis.value,
            "message": self.message,
            "path": self.path,
            "actual": self.actual,
            "expected": self.expected,
            "action": self.action,
            "subjects": list(self.subjects),
        }


class Findings:
    """Collects findings in any order; the report sorts them."""

    def __init__(self) -> None:
        self.items: list[Finding] = []

    def add(
        self,
        code: str,
        message: str,
        *,
        path: str | None = None,
        actual: Value | None = None,
        expected: Value | None = None,
        action: str | None = None,
        subjects: tuple[str, ...] = (),
    ) -> None:
        self.items.append(Finding(RULES[code], message, path, actual, expected, action, subjects))

    def sorted(self) -> tuple[Finding, ...]:
        return tuple(sorted(self.items, key=Finding.sort_key))
