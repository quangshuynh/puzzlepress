"""Studio adapter for interior builds, preflight and page previews.

Every decision is made by the same core APIs as `book build` and `book
preflight`; this module only locates the saved project's output directory,
serializes requests and presents results. It reads fixed artifact names only,
never a caller-supplied path, and builds only the saved source revision.
"""

import hashlib
import logging
import re
from collections import OrderedDict
from pathlib import Path

from puzzlepress.book_cli import describe
from puzzlepress.interior import DEFAULT_PROFILE, InteriorError, build_interior, write_interior
from puzzlepress.interior.build import check_output_directory, write_preflight_report
from puzzlepress.interior.model import Box, InteriorLayout
from puzzlepress.interior.spec import PROFILES
from puzzlepress.models import Project
from puzzlepress.preflight import (
    RULESET_VERSION,
    InteriorArtifacts,
    Outcome,
    PreflightResult,
    preflight_interior,
    read_interior_artifacts,
    report_bytes,
)
from puzzlepress.preflight.context import parse_manifest
from puzzlepress.preflight.rules import ink_bounds, kdp_safe_area
from puzzlepress.project import resolve_output_directory

from .preview import SCALES, PageOutOfRange, PageRasterizer, PreviewUnavailable
from .service import ProjectStore, StudioError, StudioService

LOGGER = logging.getLogger(__name__)
DIGEST = re.compile(r"[0-9a-f]{64}")
# Integrity rules whose failure means the artifact predates current inputs.
# A superseded status request (a reload, a resize) may still hold the generation
# lock; print requests queue briefly behind it instead of failing.
LOCK_WAIT = 60.0
STALE_RULES = ("source_current", "plan_current", "print_profile_current", "toolchain_current")


def _box(box: Box) -> dict[str, float]:
    return {k: round(getattr(box, k), 3) for k in ("x", "y", "width", "height")}


def _geometry(layout: InteriorLayout) -> list[dict[str, object]]:
    """Authoritative physical boxes for preview overlays, in PDF points."""
    count = len(layout.pages)
    pages: list[dict[str, object]] = []
    for page in layout.pages:
        frame = page.frame
        safe = kdp_safe_area(layout.spec, count, frame.recto)
        pages.append(
            {
                "physical_page": page.number,
                "trim": _box(frame.trim),
                "live": _box(frame.content),
                "kdp_safe": _box(safe) if safe else None,
                "elements": [
                    {"role": element.role, "box": _box(ink_bounds(element))}
                    for element in page.elements
                ],
            }
        )
    return pages


class PrintService:
    def __init__(self, service: StudioService, rasterizer: PageRasterizer | None = None) -> None:
        self.service = service
        self.store: ProjectStore = service.store
        self.rasterizer = rasterizer or PageRasterizer()
        self._reports: OrderedDict[tuple[str, ...], dict[str, object]] = OrderedDict()

    def _locate(self, key: str) -> tuple[Project, str, Path, Path]:
        project, revision = self.store.snapshot(key)
        if project.composition is None:
            raise StudioError(422, "no_composition", "This project has no book composition.")
        source = self.store.source(key).parent
        try:
            directory = check_output_directory(resolve_output_directory(project, source), source)
        except InteriorError as error:
            raise StudioError(
                503, "output_unavailable", "The project's output directory is unavailable."
            ) from error
        return project, revision, source, directory

    def status(self, key: str) -> dict[str, object]:
        with self.service.exclusive(wait=LOCK_WAIT):
            return self._status(key)

    def _status(self, key: str, built: PreflightResult | None = None) -> dict[str, object]:
        project, revision, source, directory = self._locate(key)
        artifacts = read_interior_artifacts(directory)
        base: dict[str, object] = {
            "key": key,
            "revision": revision,
            "ruleset": RULESET_VERSION,
            "profiles": [
                {"id": spec.profile_id, "description": spec.description, "paper": spec.paper.value}
                for spec in PROFILES.values()
            ],
            "profile": _built_profile(artifacts.manifest) or DEFAULT_PROFILE,
        }
        if artifacts.pdf is None and artifacts.manifest is None:
            return {**base, "state": "missing", "report": None, "preview": None}
        cache_key = (
            key,
            revision,
            _digest(artifacts.pdf),
            _digest(artifacts.manifest),
            str(RULESET_VERSION),
        )
        cached = self._reports.get(cache_key)
        if cached is None:
            result = built or preflight_interior(project, artifacts, source_directory=source)
            cached = self._present(result, artifacts)
            self._reports[cache_key] = cached
            while len(self._reports) > 8:
                self._reports.popitem(last=False)
        return {**base, **cached}

    def _present(self, result: PreflightResult, artifacts: InteriorArtifacts) -> dict[str, object]:
        report = result.report
        outcomes = {r.rule.code: r.outcome for r in report.results}
        stale = any(outcomes.get(code) is Outcome.FAILED for code in STALE_RULES)
        plan, layout = result.plan, result.layout
        pages = report.to_dict()["pages"]
        assert isinstance(pages, list)
        if plan is not None:
            for page in pages:
                page["description"] = describe(plan.pages[page["physical_page"] - 1], plan)
        preview = None
        if artifacts.pdf is not None and report.page_count:
            preview = {
                "pdf_sha256": hashlib.sha256(artifacts.pdf).hexdigest(),
                "page_count": report.page_count,
                "scales": SCALES,
                "pages": pages,
                "geometry": _geometry(layout) if layout else None,
            }
        return {
            "state": "stale" if stale else "current" if report.structurally_valid else "invalid",
            "report": report.to_dict(),
            "preview": preview,
        }

    def build(self, key: str, revision: str, profile: str | None = None) -> dict[str, object]:
        """Build the saved source exactly at `revision`, then preflight what was written.

        `profile` defaults to the built interior's profile, else the default profile.
        """
        with self.service.exclusive(wait=LOCK_WAIT):
            project, current, source, directory = self._locate(key)
            if current != revision:
                raise StudioError(
                    409, "source_changed", "Saved source changed. Reload before building."
                )
            chosen = profile or _built_profile(read_interior_artifacts(directory).manifest)
            if chosen is not None and chosen not in PROFILES:
                raise StudioError(422, "unsupported_profile", "Unknown print profile.")
            spec = PROFILES[chosen or DEFAULT_PROFILE]
            try:
                build = build_interior(project, spec, source)
                write_interior(build, directory, source)
            except InteriorError as error:
                return {
                    "build": {
                        "success": False,
                        "stage": error.stage,
                        "diagnostics": [issue.to_dict() for issue in error.issues],
                    },
                    **self._status(key),
                }
            artifacts = read_interior_artifacts(directory)
            result = preflight_interior(project, artifacts, expected=build, source_directory=source)
            try:
                write_preflight_report(
                    report_bytes(result.report), project.book.id, directory, source
                )
            except InteriorError:
                LOGGER.warning("Could not write preflight.json", exc_info=True)
            return {"build": {"success": True}, **self._status(key, result)}

    def page_image(self, key: str, page: int, size: str, pdf_digest: str) -> bytes:
        if size not in SCALES:
            raise StudioError(404, "not_found", "Unknown preview size.")
        if not DIGEST.fullmatch(pdf_digest):
            raise StudioError(422, "invalid_request", "Supply the PDF digest being previewed.")
        _, _, _, directory = self._locate(key)
        pdf = read_interior_artifacts(directory).pdf
        if pdf is None:
            raise StudioError(404, "interior_missing", "No interior has been built.")
        if hashlib.sha256(pdf).hexdigest() != pdf_digest:
            raise StudioError(
                409, "preview_stale", "The interior changed. Reload the print preview."
            )
        try:
            return self.rasterizer.png(pdf, pdf_digest, page, size)
        except PageOutOfRange as error:
            raise StudioError(404, "page_not_found", "The interior has no such page.") from error
        except PreviewUnavailable as error:
            raise StudioError(
                503, "preview_unavailable", "Install the studio extra (pypdfium2) for previews."
            ) from error


def _built_profile(manifest: bytes | None) -> str | None:
    """The built-in profile a readable interior.json was built with, if any."""
    if manifest is None:
        return None
    parsed, _ = parse_manifest(manifest)
    profile = parsed.get("print_profile") if parsed else None
    identifier = profile.get("profile_id") if isinstance(profile, dict) else None
    return identifier if isinstance(identifier, str) and identifier in PROFILES else None


def _digest(data: bytes | None) -> str:
    return hashlib.sha256(data).hexdigest() if data is not None else "-"
