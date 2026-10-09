"""PlanningReadinessReport: where a plan stands, why, and what an approval covers.

The state is the first gate that still has a blocking (error) finding:

    definition   -> draft
    research     -> needs_research
    content      -> needs_content
    structure    -> needs_content
    feasibility  -> structurally_valid   (consistent, but not producible today)
    decisions    -> production_feasible  (producible; author decisions remain)
    (none)       -> ready_for_approval
    + approval   -> approved             (approval equals the current identity)

Each gate is reported separately, never collapsed into one boolean. Warnings
and notes never block. Approval is the author's: it stores the planning
identity they reviewed and applies only while that identity is current, so any
material edit makes it stale and restoring the approved content restores it.
Planning approval is not publishing approval and is not market validation.
"""

import json
from dataclasses import dataclass, replace
from enum import StrEnum

from ..models import Project
from ..preflight.model import Severity
from .analysis import PlanAnalysis
from .feasibility import Feasibility, Item, PageEstimate
from .identity import planning_identity
from .model import PlanningDocument
from .rules import CATALOGUE, RULESET_ID, RULESET_VERSION, Finding, Gate

REPORT_VERSION = 1


class State(StrEnum):
    DRAFT = "draft"
    NEEDS_RESEARCH = "needs_research"
    NEEDS_CONTENT = "needs_content"
    STRUCTURALLY_VALID = "structurally_valid"
    PRODUCTION_FEASIBLE = "production_feasible"
    READY_FOR_APPROVAL = "ready_for_approval"
    APPROVED = "approved"


# Blocking gates in order, and the state a plan holds while that gate blocks.
LADDER = (
    (Gate.DEFINITION, State.DRAFT, "Blueprint defined"),
    (Gate.RESEARCH, State.NEEDS_RESEARCH, "Research and evidence in order"),
    (Gate.CONTENT, State.NEEDS_CONTENT, "Content planned"),
    (Gate.STRUCTURE, State.NEEDS_CONTENT, "References and vocabulary valid"),
    (Gate.FEASIBILITY, State.STRUCTURALLY_VALID, "Producible with current PuzzlePress"),
    (Gate.DECISIONS, State.PRODUCTION_FEASIBLE, "Author decisions made"),
)
STATE_TEXT = {
    State.DRAFT: "Draft: the blueprint is not fully defined yet.",
    State.NEEDS_RESEARCH: "Needs research: blocking questions or unattributed evidence remain.",
    State.NEEDS_CONTENT: "Needs content: planned puzzles, allocations or vocabulary are "
    "incomplete or invalid.",
    State.STRUCTURALLY_VALID: "Structurally valid, but the current PuzzlePress cannot produce "
    "this plan as written.",
    State.PRODUCTION_FEASIBLE: "Production-feasible; decisions only the author can make remain.",
    State.READY_FOR_APPROVAL: "Ready for author approval.",
    State.APPROVED: "Approved: this exact plan is approved for production handoff.",
}
BOUNDARY = (
    "Planning approval records the author's own review of this plan. It is not publishing "
    "approval, KDP acceptance or evidence that the book will sell."
)


@dataclass(frozen=True)
class GateResult:
    gate: Gate
    label: str
    passed: bool
    blocking: tuple[str, ...]  # Codes of the error findings that block it.

    def to_dict(self) -> dict[str, object]:
        return {
            "gate": self.gate.value,
            "label": self.label,
            "passed": self.passed,
            "blocking": list(self.blocking),
        }


@dataclass(frozen=True)
class Approval:
    status: str  # none | current | stale
    approved_identity: str | None
    counts: bool  # Current and every gate passes.

    def to_dict(self) -> dict[str, object]:
        return {
            "status": self.status,
            "approved_identity": self.approved_identity,
            "counts": self.counts,
        }


@dataclass(frozen=True)
class PlanningReadinessReport:
    project: Project
    document: PlanningDocument
    identity: str
    state: State
    gates: tuple[GateResult, ...]
    approval: Approval
    findings: tuple[Finding, ...]
    feasibility: tuple[Item, ...]
    pages: PageEstimate
    views: dict[str, object]

    @property
    def ready(self) -> bool:
        return self.state in (State.READY_FOR_APPROVAL, State.APPROVED)

    @property
    def approved(self) -> bool:
        return self.state is State.APPROVED

    def blocking(self) -> tuple[Finding, ...]:
        return tuple(f for f in self.findings if f.severity is Severity.ERROR)

    def to_dict(self) -> dict[str, object]:
        doc = self.document
        counts = {severity.value: 0 for severity in Severity}
        for finding in self.findings:
            counts[finding.severity.value] += 1
        return {
            "report_version": REPORT_VERSION,
            "ruleset": {"id": RULESET_ID, "version": RULESET_VERSION},
            "book": {"id": self.project.book.id, "title": self.project.book.title},
            "planning_identity": self.identity,
            "state": self.state.value,
            "statement": STATE_TEXT[self.state],
            "gates": [gate.to_dict() for gate in self.gates],
            "approval": self.approval.to_dict(),
            "summary": {
                "target_puzzles": doc.structure.target_puzzles,
                "allocated_puzzles": sum(t.puzzles or 0 for t in doc.themes),
                "specified_puzzles": len(doc.puzzles),
                "themes": len(doc.themes),
                "levels": len(doc.difficulty.levels),
                "candidate_words": sum(len(p.entries) for p in doc.vocabulary),
                "findings": counts,
            },
            "allocation": self.views["allocation"],
            "levels": self.views["levels"],
            "progression": self.views["progression"],
            "vocabulary": self.views["vocabulary"],
            "research": self.views["research"],
            "feasibility": [item.to_dict() for item in self.feasibility],
            "page_estimate": self.pages.to_dict(),
            "findings": [finding.to_dict() for finding in self.findings],
            "rules": [rule.to_dict() for rule in CATALOGUE],
            "boundary": BOUNDARY,
        }


def evaluate_plan(project: Project, document: PlanningDocument) -> PlanningReadinessReport:
    """Evaluate a schema-valid plan against its project and the running engine (pure)."""
    analysis = PlanAnalysis(project, document)
    feasibility = Feasibility(analysis)
    identity = planning_identity(project.book.id, document)
    findings = analysis.findings
    gates: list[GateResult] = []
    state: State | None = None
    for gate, blocked_state, label in LADDER:
        codes = tuple(
            sorted(
                {
                    f.rule.code
                    for f in findings.items
                    if f.rule.gate is gate and f.severity is Severity.ERROR
                }
            )
        )
        gates.append(GateResult(gate, label, not codes, codes))
        if codes and state is None:
            state = blocked_state
    ready = state is None
    approved = document.approval
    if approved is None:
        approval = Approval("none", None, False)
    elif approved == identity:
        approval = Approval("current", approved, ready)
        if not ready:
            findings.add(
                "approval_not_ready",
                "An approval is recorded for this exact plan, but blocking findings remain, "
                "so it does not count for production.",
                path="approval",
            )
    else:
        approval = Approval("stale", approved, False)
        findings.add(
            "approval_stale",
            "The plan changed after it was approved. Review it and approve again; "
            "restoring the approved content would restore the approval.",
            path="approval",
            actual=identity,
            expected=approved,
        )
    if state is None:
        state = State.APPROVED if approval.counts else State.READY_FOR_APPROVAL
    return PlanningReadinessReport(
        project=project,
        document=document,
        identity=identity,
        state=state,
        gates=tuple(gates),
        approval=approval,
        findings=findings.sorted(),
        feasibility=tuple(feasibility.items),
        pages=feasibility.estimate,
        views={
            "allocation": analysis.allocation_view(),
            "levels": analysis.levels_view(),
            "progression": analysis.progression_view(),
            "vocabulary": analysis.vocabulary_view(),
            "research": analysis.research_view(),
        },
    )


def report_bytes(report: PlanningReadinessReport) -> bytes:
    """Canonical report JSON: sorted keys, ASCII, LF. Same plan, same bytes."""
    text = json.dumps(report.to_dict(), sort_keys=True, indent=2, ensure_ascii=True,
                      allow_nan=False)  # fmt: skip
    return (text + "\n").encode("ascii")


class ApprovalError(Exception):
    """An approval PuzzlePress refuses to record; nothing is written."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


def approve_plan(project: Project, document: PlanningDocument, reviewed: str) -> PlanningDocument:
    """The document with `reviewed` recorded as its approval.

    `reviewed` is the planning identity the author reviewed. It must equal the
    plan's current identity, and the plan must be ready: PuzzlePress never
    approves a plan by itself, never approves content the author did not see,
    and never approves a plan with blocking findings.
    """
    report = evaluate_plan(project, document)
    if reviewed != report.identity:
        raise ApprovalError(
            "identity_mismatch",
            "The plan changed since this identity was reported. Review the current plan "
            f"({report.identity}) before approving.",
        )
    if not report.ready:
        raise ApprovalError(
            "not_ready",
            f"Only a plan ready for approval can be approved. {STATE_TEXT[report.state]}",
        )
    return replace(document, approval=reviewed)


def withdraw_approval(document: PlanningDocument) -> PlanningDocument:
    return replace(document, approval=None)
