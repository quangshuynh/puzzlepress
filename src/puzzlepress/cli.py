"""Terminal presentation only; all project behavior lives in reusable APIs."""

import argparse
import sys
from collections.abc import Sequence

from . import __version__
from .identity import build_identity
from .project import load_project
from .validation import ProjectError


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="puzzlepress", description="Inspect and validate book projects."
    )
    parser.add_argument("--version", action="version", version=f"PuzzlePress {__version__}")
    commands = parser.add_subparsers(dest="command", required=True)
    for name, help_text in (
        ("validate", "Validate a book project"),
        ("inspect", "Show normalized project and build identity"),
    ):
        command = commands.add_parser(name, help=help_text)
        command.add_argument("project", help="YAML file or directory containing book.yaml")
    args = parser.parse_args(argv)
    try:
        loaded = load_project(args.project)
    except ProjectError as error:
        for issue in error.issues:
            location = f" (line {issue.line}, column {issue.column})" if issue.line else ""
            print(
                f"{issue.path or 'project'} [{issue.code}]{location}: {issue.message}",
                file=sys.stderr,
            )
        return 1
    project = loaded.project
    if args.command == "validate":
        print(f"Valid: {project.book.id} ({loaded.source_path})")
    else:
        for label, value in (
            ("Book ID", project.book.id),
            ("Title", project.book.title),
            ("Schema version", project.schema_version),
            ("Language", project.book.language),
            ("Seed", project.build.seed),
            ("Content items", len(project.content.items)),
            ("Build identity", build_identity(project)),
            ("Source", loaded.source_path),
            ("Output directory", loaded.output_directory),
        ):
            print(f"{label}: {value}")
    return 0
