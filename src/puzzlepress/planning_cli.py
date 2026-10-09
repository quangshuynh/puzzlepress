"""Terminal adapter for book planning: inspect, validate, report, approve, handoff.

Every decision is made by `puzzlepress.planning`; this module presents it. Only
`plan approve` writes, and only planning.yaml in the project folder. Nothing
reads or writes a build directory, book.yaml or the network. Exit codes: 0
success, 1 expected failure (missing, invalid or not ready), 2 usage.
"""

import argparse
import json
import sys
from dataclasses import asdict
from pathlib import Path
from typing import TYPE_CHECKING

from .errors import ProjectError
from .project import LoadedProject, load_project

if TYPE_CHECKING:
    from .planning import LoadedPlan, PlanningReadinessReport
    from .planning.rules import Finding

PROJECT_HELP = "YAML file or directory containing book.yaml"
GATE_HEADINGS = {
    "definition": "Definition",
    "research": "Research",
    "content": "Content",
    "structure": "Structure",
    "feasibility": "Feasibility",
    "decisions": "Decisions",
    "editorial": "Editorial review",
    "approval": "Approval",
}


def add_plan_command(commands: "argparse._SubParsersAction[argparse.ArgumentParser]") -> None:
    plan = commands.add_parser(
        "plan", help="Research and book planning: blueprint, coverage, readiness, approval"
    )
    actions = plan.add_subparsers(dest="plan_command", required=True)
    for name, text in (
        ("inspect", "Summarize the planning document, its identity and readiness (read-only)"),
        ("validate", "Check the planning schema, references and vocabulary rules (read-only)"),
        ("report", "Full planning readiness report: findings and feasibility (read-only)"),
        ("handoff", "Print the production handoff of an approved plan (read-only)"),
    ):
        command = actions.add_parser(name, help=text)
        command.add_argument("project", help=PROJECT_HELP)
        command.add_argument("--json", action="store_true", help="Print JSON")
    approve = actions.add_parser(
        "approve", help="Record your approval of the plan identity you reviewed (planning.yaml)"
    )
    approve.add_argument("project", help=PROJECT_HELP)
    choice = approve.add_mutually_exclusive_group(required=True)
    choice.add_argument("--identity", help="The planning identity you reviewed")
    choice.add_argument("--withdraw", action="store_true", help="Remove the recorded approval")


def _bytes(data: bytes) -> None:
    binary = getattr(sys.stdout, "buffer", None)
    if binary is None:
        sys.stdout.write(data.decode("ascii"))
    else:
        sys.stdout.flush()
        binary.write(data)
        binary.flush()


def _json(data: object) -> None:
    text = json.dumps(data, sort_keys=True, indent=2, ensure_ascii=True, allow_nan=False)
    _bytes((text + "\n").encode("ascii"))


def _issues(error: ProjectError) -> None:
    for issue in error.issues:
        location = f" (line {issue.line}, column {issue.column})" if issue.line else ""
        print(f"planning.yaml {issue.path} [{issue.code}]{location}: {issue.message}",
              file=sys.stderr)  # fmt: skip


def _load(loaded: LoadedProject) -> "LoadedPlan | None":
    from .planning import read_planning

    plan = read_planning(loaded.source_path.parent)
    if plan.document is None:
        print(
            f"No planning document: {plan.path.name} does not exist beside "
            f"{loaded.source_path.name}. See docs/book-planning.md to start one.",
            file=sys.stderr,
        )
        return None
    return plan


def run_plan_command(args: argparse.Namespace) -> int:
    loaded = load_project(args.project)
    try:
        plan = _load(loaded)
    except ProjectError as error:
        if getattr(args, "json", False):
            _json({"valid": False, "issues": [asdict(i) for i in error.issues]})
        _issues(error)
        return 1
    if plan is None:
        return 1
    from .planning import evaluate_plan

    assert plan.document is not None
    report = evaluate_plan(loaded.project, plan.document)
    command = args.plan_command
    if command == "validate":
        return _validate(report, args.json)
    if command == "inspect":
        return _inspect(report, plan, args.json)
    if command == "report":
        return _report(report, args.json)
    if command == "handoff":
        return _handoff(report, args.json)
    return _approve(loaded, plan, report, args)


def _show(finding: "Finding") -> str:
    measured = (
        f" (actual {finding.actual}; expected {finding.expected})"
        if finding.actual is not None and finding.expected is not None
        else ""
    )
    where = f" [{finding.path}]" if finding.path else ""
    return f"  {finding.severity.value.upper():7} {finding.rule.code}: {finding.message}" + (
        measured + where
    )


def _validate(report: "PlanningReadinessReport", as_json: bool) -> int:
    structural = [f for f in report.blocking() if f.rule.gate.value == "structure"]
    if as_json:
        _json(
            {
                "valid": not structural,
                "planning_identity": report.identity,
                "issues": [],
                "findings": [f.to_dict() for f in structural],
            }
        )
        return 0 if not structural else 1
    print(f"Planning document: {report.project.book.id} (schema valid)")
    print(f"Planning identity: {report.identity}")
    if structural:
        print(f"References and vocabulary: {len(structural)} blocking finding(s)")
        for finding in structural:
            print(_show(finding))
        return 1
    print("References and vocabulary: valid")
    print("Readiness is not judged here; run `puzzlepress plan report`.")
    return 0


def _summary(report: "PlanningReadinessReport") -> dict[str, object]:
    data = report.to_dict()
    return {
        key: data[key]
        for key in (
            "book",
            "planning_identity",
            "state",
            "statement",
            "gates",
            "approval",
            "summary",
            "feasibility",
            "page_estimate",
            "boundary",
        )
    }


def _inspect(report: "PlanningReadinessReport", plan: "LoadedPlan", as_json: bool) -> int:
    if as_json:
        _json(_summary(report))
        return 0
    doc = report.document
    s = doc.structure
    print(f"Book: {report.project.book.id} ({report.project.book.title})")
    print(f"Planning document: {plan.path.name}, version {doc.version}")
    print(f"Planning identity: {report.identity}")
    print(f"State: {report.state.value} - {report.to_dict()['statement']}")
    print(f"Approval: {report.approval.status}")
    print(f"Subject: {doc.concept.subject or 'not stated'}")
    print(f"Primary audience: {doc.positioning.primary_audience or 'not chosen'}")
    print(
        f"Puzzles: target {s.target_puzzles if s.target_puzzles is not None else 'not set'}, "
        f"allocated {sum(t.puzzles or 0 for t in doc.themes)}, specified {len(doc.puzzles)}"
    )
    print(
        f"Themes {len(doc.themes)} | levels {len(doc.difficulty.levels)} | candidate words "
        f"{sum(len(p.entries) for p in doc.vocabulary)} | research notes {len(doc.research)} "
        f"| comparables {len(doc.comparables)}"
    )
    for gate in report.gates:
        mark = "passed" if gate.passed else "blocked: " + ", ".join(gate.blocking)
        print(f"  {gate.label}: {mark}")
    return 0


def _report(report: "PlanningReadinessReport", as_json: bool) -> int:
    from .planning import RULESET_ID, RULESET_VERSION, report_bytes

    code = 0 if report.ready else 1
    if as_json:
        _bytes(report_bytes(report))
        return code
    print(f"Planning readiness: {report.project.book.id} ({RULESET_ID} v{RULESET_VERSION})")
    print(f"Planning identity: {report.identity}")
    print(f"State: {report.state.value} - {report.to_dict()['statement']}")
    approval = report.approval
    print(
        f"Approval: {approval.status}"
        + (f" ({approval.approved_identity})" if approval.approved_identity else "")
    )
    for gate in report.gates:
        print(f"  {gate.label}: {'passed' if gate.passed else 'BLOCKED'}")
    print("Feasibility:")
    for item in report.feasibility:
        print(f"  {item.label}: {item.status} - {item.detail}")
    for name, heading in GATE_HEADINGS.items():
        found = [f for f in report.findings if f.rule.gate.value == name]
        if found:
            print(f"{heading}: {len(found)}")
            for finding in found:
                print(_show(finding))
    if report.ready and approval.status != "current":
        print("To approve after reviewing this plan:")
        print(f"  puzzlepress plan approve PROJECT --identity {report.identity}")
    print(report.to_dict()["boundary"])
    return code


def _handoff(report: "PlanningReadinessReport", as_json: bool) -> int:
    from .planning import HandoffUnavailable, handoff_bytes, handoff_document

    try:
        if as_json:
            _bytes(handoff_bytes(report))
            return 0
        document = handoff_document(report)
    except HandoffUnavailable as error:
        print(f"No handoff: {error}", file=sys.stderr)
        return 1
    puzzles = document["puzzles"]
    assert isinstance(puzzles, list)
    print(f"Production handoff: {report.project.book.id}")
    print(f"Approved planning identity: {report.identity}")
    print(f"Planned puzzles: {len(puzzles)}")
    print("Use --json for the full handoff document. Nothing was generated or written.")
    return 0


def _approve(
    loaded: LoadedProject,
    plan: "LoadedPlan",
    report: "PlanningReadinessReport",
    args: argparse.Namespace,
) -> int:
    from .planning import (
        ApprovalError,
        PlanningWriteError,
        approve_plan,
        withdraw_approval,
        write_planning,
    )

    assert plan.document is not None
    try:
        if args.withdraw:
            document = withdraw_approval(plan.document)
        else:
            document = approve_plan(loaded.project, plan.document, args.identity)
        if document == plan.document:
            print("Nothing to change: planning.yaml already records this.")
            return 0
        write_planning(Path(loaded.source_path.parent), document, plan.revision)
    except (ApprovalError, PlanningWriteError) as error:
        print(f"Not recorded: {error}", file=sys.stderr)
        return 1
    if args.withdraw:
        print("Approval withdrawn. planning.yaml was rewritten as normalized YAML.")
    else:
        print(f"Approved: {report.identity}")
        print("planning.yaml was rewritten as normalized YAML (comments are not preserved).")
        print("Any later edit to the plan makes this approval stale.")
    return 0
