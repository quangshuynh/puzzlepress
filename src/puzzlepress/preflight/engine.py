"""Run every preflight rule over an interior and assemble a deterministic report.

Preflight observes: it reads artifact bytes, rebuilds the expected interior in
memory with the same pure pipeline as `book build`, and compares. It never
writes, repairs, pads, regroups or re-renders anything on disk.
"""

import hashlib
from dataclasses import dataclass

from ..identity import build_identity
from ..interior.build import InteriorBuild, build_interior
from ..interior.inspection import read_pdf_facts
from ..interior.issues import InteriorError, LayoutIssue
from ..interior.model import InteriorLayout
from ..interior.spec import PROFILES, PrintSpecification, to_inches
from ..models import Project
from ..publication import PublicationPlan
from .context import Context, InteriorArtifacts, parse_manifest
from .model import Finding, Outcome, PreflightReport, RuleResult
from .rules import CATALOGUE


@dataclass(frozen=True)
class PreflightResult:
    report: PreflightReport
    # Present only when the PDF is byte-identical to the verified layout's render.
    layout: InteriorLayout | None
    plan: PublicationPlan | None


def _spec(manifest: dict[str, object] | None) -> PrintSpecification | None:
    if manifest is None:
        return None
    profile = manifest["print_profile"]
    assert isinstance(profile, dict)
    return PROFILES.get(str(profile.get("profile_id")))


def preflight_interior(
    project: Project, artifacts: InteriorArtifacts, expected: InteriorBuild | None = None
) -> PreflightResult:
    """Inspect artifacts against the project. `expected` may reuse a fresh build.

    A supplied build is used only if it was produced from this project with the
    manifest's profile; otherwise the expected interior is rebuilt.
    """
    source_identity = build_identity(project)
    manifest, manifest_problem = (
        parse_manifest(artifacts.manifest) if artifacts.manifest is not None else (None, None)
    )
    spec = _spec(manifest)
    facts_or_issue = read_pdf_facts(artifacts.pdf) if artifacts.pdf is not None else None
    facts = None if isinstance(facts_or_issue, LayoutIssue) else facts_or_issue
    build_error: InteriorError | None = None
    if spec is not None and not (
        expected is not None
        and expected.layout.spec == spec
        and expected.plan.identity == source_identity
    ):
        try:
            expected = build_interior(project, spec)
        except InteriorError as error:
            expected, build_error = None, error
    elif spec is None:
        expected = None
    ctx = Context(
        project=project,
        source_identity=source_identity,
        artifacts=artifacts,
        manifest=manifest,
        manifest_problem=manifest_problem,
        spec=spec,
        facts=facts,
        facts_problem=facts_or_issue if isinstance(facts_or_issue, LayoutIssue) else None,
        expected=expected,
        build_error=build_error,
    )
    results: list[RuleResult] = []
    findings: list[Finding] = []
    for definition, evaluate in CATALOGUE:
        check = evaluate(definition, ctx)
        outcome = check.outcome or (Outcome.FAILED if check.findings else Outcome.PASSED)
        results.append(
            RuleResult(
                definition,
                outcome,
                len(check.findings),
                None if outcome is Outcome.FAILED else check.note,
                check.measure,
            )
        )
        findings.extend(check.findings)
    report = PreflightReport(
        book_id=project.book.id,
        source_identity=source_identity,
        profile=_profile(spec),
        artifacts=_artifacts(ctx),
        page_count=facts.page_count if facts else None,
        pages=tuple(ctx.page(n) for n in range(1, facts.page_count + 1)) if facts else (),
        results=tuple(results),
        findings=tuple(sorted(findings, key=Finding.sort_key)),
    )
    return PreflightResult(report, ctx.layout, ctx.plan)


def _profile(spec: PrintSpecification | None) -> dict[str, object] | None:
    if spec is None:
        return None
    return {
        "id": spec.profile_id,
        "version": spec.profile_version,
        "description": spec.description,
        "trim": {
            "name": spec.trim.name,
            "width_in": to_inches(spec.trim.width),
            "height_in": to_inches(spec.trim.height),
        },
        "bleed": spec.bleed,
    }


def _artifacts(ctx: Context) -> dict[str, object]:
    """Identify exactly which bytes were inspected, so the report cannot be misapplied."""
    pdf, manifest = ctx.artifacts.pdf, ctx.artifacts.manifest
    return {
        "pdf": None
        if pdf is None
        else {"sha256": hashlib.sha256(pdf).hexdigest(), "bytes": len(pdf)},
        "manifest": None
        if manifest is None
        else {"sha256": hashlib.sha256(manifest).hexdigest(), "bytes": len(manifest)},
        "interior_identity": ctx.manifest["interior_identity"] if ctx.manifest else None,
        "expected_interior_identity": ctx.expected.manifest["interior_identity"]
        if ctx.expected
        else None,
        "matches_layout": ctx.matches_layout,
    }
