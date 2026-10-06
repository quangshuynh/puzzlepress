"""Terminal adapter for renderer-independent publication plans. Writes no files."""

import argparse
import json
import sys

from .project import load_project
from .publication import PageKind, PlanPage, PublicationPlan, build_publication
from .publication_verification import publication_payload, verify_publication_plan


def add_book_command(commands: "argparse._SubParsersAction[argparse.ArgumentParser]") -> None:
    book = commands.add_parser("book", help="Book composition tools")
    actions = book.add_subparsers(dest="book_command", required=True)
    plan = actions.add_parser("plan", help="Plan and verify the logical publication order")
    plan.add_argument("project", help="YAML file or directory containing book.yaml")
    plan.add_argument("--json", action="store_true", help="Print the structured plan")


def describe(page: PlanPage, plan: PublicationPlan) -> str:
    def label(index: int | None) -> str:
        return plan.pages[index - 1].number.label if index else "?"

    if page.kind is PageKind.BLANK:
        before = page.blank_before.value.replace("_", " ") if page.blank_before else "?"
        return f"Blank: {before} start on recto"
    if page.puzzle is not None:
        ref = page.puzzle
        where = f"; solution p. {label(page.solution_page)}" if page.solution_page else ""
        return f"Puzzle {ref.ordinal}: {ref.title} [{ref.id}]{where}"
    if page.solutions:
        listed = ", ".join(
            f"{item.puzzle.ordinal} (p. {label(item.puzzle_page)})" for item in page.solutions
        )
        heading = f" | heading: {page.heading}" if page.heading else ""
        return f"Solutions for puzzle {listed}{heading}"
    name = page.kind.value.replace("_", " ").capitalize()
    title = page.matter.title if page.matter else None
    return f"{name}: {title}" if title else name


def run_book_command(args: argparse.Namespace) -> int:
    project = load_project(args.project).project
    report, plan = build_publication(project)
    verification = verify_publication_plan(plan, project, report)
    if not verification.valid:
        raise RuntimeError(f"Publication plan failed verification: {verification.issues!r}")
    if args.json:
        print(
            json.dumps(
                publication_payload(report, plan, verification),
                ensure_ascii=True,
                sort_keys=True,
                indent=2,
                allow_nan=False,
            )
        )
    else:
        stats = plan.statistics
        print(f"Build identity: {plan.identity}")
        print(
            f"Publication plan v{plan.plan_version} for {plan.book_id}: "
            f"{stats.logical_pages} logical pages, verified"
        )
        print(f"{'Page':>4}  {'Side':<5}  {'Folio':<7}  {'Section':<12}  Entry")
        for page in plan.pages:
            folio = page.number.label if page.number.displayed else f"({page.number.label})"
            section = page.section.value.replace("_", " ")
            print(
                f"{page.index:>4}  {page.side.value:<5}  {folio:<7}  {section:<12}  "
                f"{describe(page, plan)}"
            )
        print(
            f"\nFront matter: {stats.front_matter_pages} | puzzles: {stats.puzzle_pages} | "
            f"solution pages: {stats.solution_pages} ({stats.solutions} solutions) | "
            f"back matter: {stats.back_matter_pages} | blanks: {stats.blank_pages}"
        )
        first = stats.first_solution_page
        first_solution = f"page {first}" if first else "none"
        print(f"First puzzle: page {stats.first_puzzle_page} | first solution: {first_solution}")
        print(f"Quality findings: {len(report.findings)} (inspect with puzzle batch)")
        print("Parenthesized folios count but are not displayed.")
        print("Logical pages are not a final printed page count; layout is not planned.")
    for issue in plan.diagnostics:
        print(f"{issue.path} [{issue.code}]: {issue.message}", file=sys.stderr)
    return 0 if plan.complete else 1
