"""Reusable project APIs. Importing this package performs no I/O."""

__version__ = "0.1.0"

from .identity import build_identity, canonical_build_inputs
from .models import Book, Build, Content, Output, Project
from .project import LoadedProject, load_project, locate_project, resolve_output_directory
from .validation import ProjectError, ValidationIssue, ValidationResult, validate_project
from .yaml_io import dump_project, parse_project

__all__ = [
    "Book",
    "Build",
    "Content",
    "LoadedProject",
    "Output",
    "Project",
    "ProjectError",
    "ValidationIssue",
    "ValidationResult",
    "build_identity",
    "canonical_build_inputs",
    "dump_project",
    "load_project",
    "locate_project",
    "parse_project",
    "resolve_output_directory",
    "validate_project",
]
