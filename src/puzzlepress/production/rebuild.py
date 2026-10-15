"""Rebuild outdated artifacts, one explicit and verified step at a time.

Only the steps an assessment lists run, in dependency order: the interior (with
its preflight report), then the cover (re-examined after an interior rebuild,
rebuilt only when it is out of date), then any saved preflight report that no
longer matches a fresh run. Each build goes through the same pure pipeline and
single writer as the CLI: a failed build writes nothing, so the previous valid
artifact stays in place, and every later step is skipped with a reason.

`before_write` is called immediately before each write. Studio passes a check
that the saved source is still the revision the author asked to rebuild, so an
edit saved during a build stops the run instead of writing output that would be
presented as current. Exporting the publishing package is never part of a
rebuild: it stays a deliberate action that needs the author's confirmations.
"""

from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path

from ..cover.build import build_cover, write_cover, write_cover_preflight
from ..cover.issues import CoverError
from ..cover.preflight import preflight_cover
from ..cover.preflight import report_bytes as cover_report_bytes
from ..interior import InteriorError, build_interior, write_interior
from ..interior.build import write_preflight_report
from ..interior.spec import PrintSpecification
from ..models import Project
from ..preflight import preflight_interior, read_interior_artifacts
from ..preflight import report_bytes as interior_report_bytes


class SourceChanged(Exception):
    """The saved source changed while a rebuild was running."""


@dataclass(frozen=True)
class StepResult:
    action: str
    status: str  # succeeded, failed, skipped, unchanged
    message: str
    stage: str | None = None
    diagnostics: tuple[dict[str, object], ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {
            "action": self.action,
            "status": self.status,
            "message": self.message,
            "stage": self.stage,
            "diagnostics": list(self.diagnostics),
        }


def rebuild(
    project: Project,
    source: Path,
    directory: Path,
    spec: PrintSpecification,
    actions: tuple[str, ...],
    before_write: Callable[[], None] = lambda: None,
) -> tuple[StepResult, ...]:
    """Run `actions` (an assessment's steps, in order). Raises SourceChanged."""
    results: list[StepResult] = []
    failed: str | None = None

    def skip(action: str) -> None:
        results.append(StepResult(action, "skipped", f"Skipped because {failed} failed."))

    for action in actions:
        if failed is not None:
            skip(action)
            continue
        if action in ("build_interior", "write_preflight"):
            try:
                if action == "build_interior":
                    built = build_interior(project, spec, source)
                    before_write()
                    write_interior(built, directory, source)
                    expected = built
                else:
                    expected = None
                result = preflight_interior(
                    project, read_interior_artifacts(directory), expected, source
                )
                before_write()
                write_preflight_report(
                    interior_report_bytes(result.report), project.book.id, directory, source
                )
            except InteriorError as error:
                failed = "the interior build" if action == "build_interior" else "preflight"
                results.append(
                    StepResult(
                        action,
                        "failed",
                        "The interior did not build; the previous interior is unchanged."
                        if action == "build_interior"
                        else "The preflight report could not be written.",
                        error.stage,
                        tuple(issue.to_dict() for issue in error.issues),
                    )
                )
                continue
            results.append(
                StepResult(
                    action,
                    "succeeded",
                    "Interior built and preflighted."
                    if action == "build_interior"
                    else "Preflight report refreshed.",
                )
            )
        elif action in ("build_cover", "write_cover_preflight"):
            if project.cover is None:
                results.append(StepResult(action, "skipped", "The book has no cover section."))
                continue
            report = preflight_cover(project, source, directory)
            if action == "build_cover" and report.state == "current":
                before_write()
                write_cover_preflight(
                    cover_report_bytes(report), project.book.id, directory, source
                )
                results.append(
                    StepResult(
                        action,
                        "unchanged",
                        "The cover is still current for this interior; its preflight report "
                        "was refreshed.",
                    )
                )
                continue
            try:
                if action == "build_cover":
                    cover = build_cover(project, source, directory)
                    before_write()
                    write_cover(cover, directory, source)
                    report = preflight_cover(project, source, directory, cover)
                before_write()
                write_cover_preflight(
                    cover_report_bytes(report), project.book.id, directory, source
                )
            except CoverError as error:
                failed = "the cover build" if action == "build_cover" else "cover preflight"
                results.append(
                    StepResult(
                        action,
                        "failed",
                        "The cover did not build; the previous cover is unchanged."
                        if action == "build_cover"
                        else "The cover preflight report could not be written.",
                        error.stage,
                        tuple(issue.to_dict() for issue in error.issues),
                    )
                )
                continue
            results.append(
                StepResult(
                    action,
                    "succeeded",
                    "Cover built and preflighted."
                    if action == "build_cover"
                    else "Cover preflight report refreshed.",
                )
            )
        else:
            raise ValueError(f"Unknown rebuild action {action!r}")
    return tuple(results)
