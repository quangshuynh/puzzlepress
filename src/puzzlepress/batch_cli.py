"""Text and JSON adapters for the same reusable batch report."""

import argparse
import json
import sys

from .batch import generate_batch
from .project import load_project


def run_batch_command(args: argparse.Namespace) -> int:
    report = generate_batch(load_project(args.project).project)
    if args.json:
        print(
            json.dumps(
                report.to_dict(), ensure_ascii=True, sort_keys=True, indent=2, allow_nan=False
            )
        )
    else:
        print(f"Build identity: {report.identity}")
        for result in report.puzzles:
            print(f"\n{result.id}: {result.title}")
            print(f"Theme: {result.theme} | Difficulty: {result.difficulty} | Seed: {result.seed}")
            if result.puzzle is not None:
                print("\n".join(" ".join(row) for row in result.puzzle.grid.rows))
                print("Targets: " + "; ".join(t.display for t in result.puzzle.targets))
            for error in result.errors:
                print(f"{result.id} [{error.code}] {error.path}: {error.message}", file=sys.stderr)
        for finding in report.findings:
            print(f"[{finding.code}] {', '.join(finding.puzzle_ids)}: {finding.message}")
            if finding.words:
                print("  Words: " + ", ".join(finding.words))
        completed = sum(result.puzzle is not None for result in report.puzzles)
        print(
            f"\nGenerated: {completed}/{len(report.puzzles)}; "
            f"quality findings: {len(report.findings)}"
        )
        print("Use --json for occurrence coordinates, similarity metrics, and solutions.")
    return 0 if report.success and (not args.strict_quality or report.clean) else 1
