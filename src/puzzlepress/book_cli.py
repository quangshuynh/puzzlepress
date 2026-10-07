"""Terminal adapter for publication plans (read-only) and interior builds."""

import argparse
import hashlib
import json
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from .project import load_project
from .publication import PageKind, PlanPage, PublicationPlan, build_publication
from .publication_verification import publication_payload, verify_publication_plan

if TYPE_CHECKING:
    from .interior import LayoutIssue


def add_book_command(commands: "argparse._SubParsersAction[argparse.ArgumentParser]") -> None:
    book = commands.add_parser("book", help="Book composition tools")
    actions = book.add_subparsers(dest="book_command", required=True)
    plan = actions.add_parser("plan", help="Plan and verify the logical publication order")
    plan.add_argument("project", help="YAML file or directory containing book.yaml")
    plan.add_argument("--json", action="store_true", help="Print the structured plan")
    build = actions.add_parser("build", help="Lay out and write the print interior PDF")
    build.add_argument("project", help="YAML file or directory containing book.yaml")
    build.add_argument(
        "--output", metavar="DIR", help="Output directory (default: the project's output.directory)"
    )
    build.add_argument("--profile", help="Print profile (default: paperback-8.5x11)")
    build.add_argument("--json", action="store_true", help="Print a structured build result")


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
    if args.book_command == "build":
        return run_build_command(args)
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


def run_build_command(args: argparse.Namespace) -> int:
    # Imported here so read-only commands never load the PDF toolchain.
    from .interior import (
        DEFAULT_PROFILE,
        InteriorError,
        LayoutIssue,
        build_interior,
        print_profile,
        write_interior,
    )

    loaded = load_project(args.project)
    try:
        spec = print_profile(args.profile or DEFAULT_PROFILE)
        if isinstance(spec, LayoutIssue):
            raise InteriorError("print_spec", (spec,))
        build = build_interior(loaded.project, spec)
        output = Path(args.output) if args.output else loaded.output_directory
        written = write_interior(build, output, loaded.source_path.parent)
    except InteriorError as error:
        if args.json:
            print(
                json.dumps(
                    {
                        "success": False,
                        "stage": error.stage,
                        "diagnostics": [issue.to_dict() for issue in error.issues],
                    },
                    ensure_ascii=True,
                    sort_keys=True,
                    indent=2,
                )
            )
        print(f"Interior build failed at {error.stage}; no interior was written.", file=sys.stderr)
        for issue in error.issues:
            print(f"  {_describe_issue(issue)}", file=sys.stderr)
        return 1
    manifest = build.manifest
    if args.json:
        print(
            json.dumps(
                {
                    "success": True,
                    "output": {"pdf": str(written.pdf), "manifest": str(written.manifest)},
                    "manifest": manifest,
                },
                ensure_ascii=True,
                sort_keys=True,
                indent=2,
            )
        )
    else:
        trim = spec.trim
        print(f"Interior: {written.pdf}")
        print(f"Manifest: {written.manifest}")
        print(
            f"Pages: {manifest['page_count']} | trim {trim.name} in, no bleed | "
            f"profile {spec.profile_id} v{spec.profile_version}"
        )
        print(f"Interior identity: {manifest['interior_identity']}")
        print(f"PDF SHA-256: {hashlib.sha256(build.pdf).hexdigest()}")
        print("Layout validated; PDF reopened and structurally verified.")
    for warning in build.layout.warnings:
        print(f"Warning: {_describe_issue(warning)}", file=sys.stderr)
    return 0


def _describe_issue(issue: "LayoutIssue") -> str:
    where = [
        f"page {issue.page}" if issue.page is not None else None,
        f"pdf page {issue.physical_page}" if issue.physical_page is not None else None,
        issue.kind,
        issue.subject,
        issue.region,
    ]
    context = ", ".join(part for part in where if part)
    measured = f" (actual {issue.actual}; required {issue.required})" if issue.actual else ""
    return f"[{issue.code}] {issue.message}{measured}" + (f" [{context}]" if context else "")
