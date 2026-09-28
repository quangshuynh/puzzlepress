"""Read-only filesystem boundary for loading projects and planning output paths."""

from dataclasses import dataclass
from pathlib import Path

from .models import Project
from .validation import ProjectError, ValidationIssue
from .yaml_io import parse_project


def _failure(path: str, code: str, message: str) -> ProjectError:
    return ProjectError((ValidationIssue(path, code, message),))


def locate_project(path: str | Path) -> Path:
    """Resolve a file or a directory containing book.yaml; never search parents."""
    try:
        candidate = Path(path).expanduser().resolve()
        if candidate.is_dir():
            candidate = (candidate / "book.yaml").resolve()
        if not candidate.is_file():
            raise _failure("source", "not_found", f"Project file not found: {candidate}")
        return candidate
    except (OSError, RuntimeError, ValueError) as error:
        raise _failure("source", "io", f"Cannot locate project: {error}") from error


def resolve_output_directory(project: Project, source_directory: str | Path) -> Path:
    """Resolve output outside the entire source tree, without creating anything.

    Also reject output ancestors of source: deleting a build must not delete source.
    Symlinks are resolved. A future writer must recheck this at write time.
    """
    try:
        source = Path(source_directory).resolve()
        output = (source / project.output.directory).resolve()
        if output.is_relative_to(source) or source.is_relative_to(output):
            raise _failure(
                "output.directory",
                "source_overlap",
                "Output and source directories must be disjoint (no ancestor overlap).",
            )
        if output.exists() and not output.is_dir():
            raise _failure(
                "output.directory", "not_directory", f"Output is not a directory: {output}"
            )
        return output
    except (OSError, RuntimeError, ValueError) as error:
        raise _failure(
            "output.directory", "io", f"Cannot resolve output directory: {error}"
        ) from error


@dataclass(frozen=True)
class LoadedProject:
    project: Project
    source_path: Path
    output_directory: Path


def load_project(path: str | Path) -> LoadedProject:
    """Load UTF-8 YAML and validate schema plus filesystem output separation."""
    source = locate_project(path)
    try:
        text = source.read_text(encoding="utf-8-sig")
    except (OSError, UnicodeError) as error:
        raise _failure("source", "io", f"Cannot read {source}: {error}") from error
    project = parse_project(text)
    output = resolve_output_directory(project, source.parent)
    return LoadedProject(project, source, output)
