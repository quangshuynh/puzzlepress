"""Shared structured errors, independent of project and puzzle models."""

from dataclasses import dataclass

MAX_SEED = 2**64 - 1


@dataclass(frozen=True)
class ValidationIssue:
    path: str
    code: str
    message: str
    line: int | None = None
    column: int | None = None


class ProjectError(Exception):
    """An expected source, configuration, or filesystem failure."""

    def __init__(self, issues: tuple[ValidationIssue, ...]) -> None:
        self.issues = issues
        super().__init__("; ".join(f"{issue.path}: {issue.message}" for issue in issues))
