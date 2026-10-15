"""Artifact dependency assessment: which built files are current, and why not.

    source + composition -> publication plan -> interior.pdf/.json -> preflight.json
    interior physical facts -> cover geometry -> cover.pdf/.json -> cover-preflight.json
    every artifact + metadata + confirmations -> publishing package

Assessment observes. It reads the build directory by fixed names through the
same authoritative checks as `book preflight`, `cover preflight` and `publish
inspect` (via the publishing readiness report, which reruns both preflights)
and never trusts a saved report. A rebuild plan lists only the steps whose
inputs changed: a cover typography change rebuilds the cover alone, a keyword
change rebuilds nothing, and an interior rebuild re-examines the cover
afterwards (it changes only if the page count, paper or profile did).
"""

from dataclasses import dataclass
from pathlib import Path

from ..cover.preflight import STALE_RULES as COVER_STALE_RULES
from ..cover.preflight import report_bytes as cover_report_bytes
from ..interior.build import PREFLIGHT_NAME
from ..models import Project
from ..preflight import report_bytes as interior_report_bytes
from ..preflight.model import Outcome
from ..publishing import PublishingReadinessReport, assemble_package, export_state
from ..publishing.readiness import INTERIOR_STALE_RULES

COVER_PREFLIGHT_NAME = "cover-preflight.json"
STEPS = ("build_interior", "build_cover", "write_preflight", "write_cover_preflight")


@dataclass(frozen=True)
class ArtifactState:
    name: str  # interior, interior_preflight, cover, cover_preflight, package
    state: str  # missing, current, stale, invalid, not_applicable, unavailable
    reasons: tuple[str, ...]
    depends_on: tuple[str, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "name": self.name,
            "state": self.state,
            "reasons": list(self.reasons),
            "depends_on": list(self.depends_on),
        }


@dataclass(frozen=True)
class RebuildStep:
    action: str  # One of STEPS.
    artifact: str
    why: str
    conditional: bool = False  # Runs only if the step before it changes its inputs.

    def to_dict(self) -> dict[str, object]:
        return {
            "action": self.action,
            "artifact": self.artifact,
            "why": self.why,
            "conditional": self.conditional,
        }


@dataclass(frozen=True)
class Assessment:
    artifacts: tuple[ArtifactState, ...]
    steps: tuple[RebuildStep, ...]
    manual: tuple[str, ...]  # Steps PuzzlePress never runs for you (export).

    def state(self, name: str) -> ArtifactState:
        return next(a for a in self.artifacts if a.name == name)

    def to_dict(self) -> dict[str, object]:
        return {
            "artifacts": [a.to_dict() for a in self.artifacts],
            "steps": [s.to_dict() for s in self.steps],
            "manual": list(self.manual),
            "outdated": bool(self.steps),
        }


def _saved(directory: Path, name: str) -> bytes | None:
    path = directory / name
    try:
        if path.is_symlink() or not path.is_file():
            return None
        return path.read_bytes()
    except OSError:
        return None


def _messages(
    results: dict[str, Outcome], findings: list[tuple[str, str]], codes: tuple[str, ...]
) -> tuple[str, ...]:
    failed = {code for code in codes if results.get(code) is Outcome.FAILED}
    # Findings may open with their issue code in brackets; reasons are for people.
    return tuple(
        message.split("] ", 1)[1] if message.startswith("[") and "] " in message else message
        for code, message in findings
        if code in failed
    )


def assess(
    project: Project, report: PublishingReadinessReport, source: Path, directory: Path
) -> Assessment:
    """What is out of date in `directory` and the steps that bring it current."""
    artifacts: list[ArtifactState] = []
    steps: list[RebuildStep] = []
    interior_state = report.interior_state
    interior = report.interior
    if project.composition is None:
        artifacts.append(ArtifactState("interior", "not_applicable", ("No composition.",), ()))
    else:
        reasons: tuple[str, ...] = ()
        if interior is not None:
            outcomes = {r.rule.code: r.outcome for r in interior.report.results}
            found = [(f.rule.code, f.message) for f in interior.report.findings]
            reasons = _messages(outcomes, found, INTERIOR_STALE_RULES)
            if interior_state == "invalid":
                reasons = tuple(
                    f.message
                    for f in interior.report.findings
                    if f.rule.scope.value == "structural" and f.rule.severity.value == "error"
                )[:6]
        if interior_state == "missing":
            reasons = ("No interior has been built.",)
        artifacts.append(ArtifactState("interior", interior_state, reasons, ("source",)))
        if interior_state in ("missing", "stale", "invalid"):
            steps.append(
                RebuildStep(
                    "build_interior",
                    "interior",
                    "; ".join(reasons) or "The interior is not current.",
                )
            )
        if interior is not None and interior_state not in ("missing", "unavailable"):
            saved = _saved(directory, PREFLIGHT_NAME)
            fresh = interior_report_bytes(interior.report)
            state = "missing" if saved is None else "current" if saved == fresh else "stale"
            why = (
                "No saved report."
                if saved is None
                else "The saved report differs from a fresh preflight."
                if state == "stale"
                else ""
            )
            artifacts.append(
                ArtifactState("interior_preflight", state, (why,) if why else (), ("interior",))
            )
            if state != "current" and not any(s.action == "build_interior" for s in steps):
                steps.append(RebuildStep("write_preflight", "interior_preflight", why))
    cover_state = report.cover_state
    cover = report.cover
    if project.cover is None:
        artifacts.append(ArtifactState("cover", "not_applicable", ("No cover section.",), ()))
    else:
        reasons = ()
        if cover is not None:
            outcomes = {r.rule.code: r.outcome for r in cover.results}
            found = [(f.rule.code, f.message) for f in cover.findings]
            reasons = _messages(outcomes, found, COVER_STALE_RULES)
        if cover_state == "missing":
            reasons = ("No cover has been built.",)
        artifacts.append(ArtifactState("cover", cover_state, reasons, ("interior", "source")))
        interior_rebuild = any(s.action == "build_interior" for s in steps)
        own_change = cover is not None and any(
            r.rule.code == "cover_current" and r.outcome is Outcome.FAILED for r in cover.results
        )
        if cover_state == "missing" or (
            cover_state in ("stale", "invalid") and (own_change or not interior_rebuild)
        ):
            steps.append(
                RebuildStep(
                    "build_cover",
                    "cover",
                    "; ".join(reasons) or "The cover is not current.",
                )
            )
        elif interior_rebuild:
            steps.append(
                RebuildStep(
                    "build_cover",
                    "cover",
                    "Checked again after the interior rebuild; rebuilt only if the cover or the "
                    "interior's page count, paper or print profile changed.",
                    conditional=True,
                )
            )
        if cover is not None and cover_state not in ("missing", "no_config", "unavailable"):
            saved = _saved(directory, COVER_PREFLIGHT_NAME)
            fresh = cover_report_bytes(cover)
            state = "missing" if saved is None else "current" if saved == fresh else "stale"
            why = (
                "No saved report."
                if saved is None
                else "The saved report differs from a fresh preflight."
                if state == "stale"
                else ""
            )
            artifacts.append(
                ArtifactState("cover_preflight", state, (why,) if why else (), ("cover",))
            )
            if state != "current" and not any(s.action == "build_cover" for s in steps):
                steps.append(RebuildStep("write_cover_preflight", "cover_preflight", why))
    identity = assemble_package(report).identity if report.package_ready else None
    exported = export_state(directory, source, report.book_id, identity).to_dict()
    package_state = str(exported.get("state", "none"))
    package_reasons: tuple[str, ...] = ()
    manual: list[str] = []
    if package_state == "stale":
        package_reasons = ("The exported package no longer matches the current artifacts.",)
        manual.append("Export the publishing package again from Publishing.")
    elif package_state == "damaged":
        package_reasons = ("The exported package does not verify.",)
        manual.append("Export the publishing package again from Publishing.")
    artifacts.append(
        ArtifactState(
            "package",
            {"none": "missing"}.get(package_state, package_state),
            package_reasons,
            ("interior", "cover", "metadata"),
        )
    )
    return Assessment(tuple(artifacts), tuple(steps), tuple(manual))
