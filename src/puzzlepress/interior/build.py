"""Interior build pipeline and its only filesystem writer.

project -> generation -> plan -> plan verification -> digest binding -> layout
-> layout validation -> PDF -> PDF inspection -> atomic write of PDF + manifest.
`build_interior` is pure; `write_interior` is the single write boundary.
"""

import hashlib
import json
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path

from reportlab import Version as REPORTLAB_VERSION

from .. import __version__
from ..batch import BatchReport
from ..identity import IDENTITY_VERSION
from ..models import Project
from ..publication import PublicationPlan, build_publication
from ..publication_verification import verify_publication_plan
from .engine import RENDERER_VERSION, layout_interior
from .fonts import font_manifest
from .inspection import inspect_pdf
from .issues import InteriorError, LayoutIssue
from .model import InteriorLayout
from .render import render_pdf
from .spec import PrintSpecification, to_inches
from .validation import validate_layout

MANIFEST_VERSION = 1
PDF_NAME = "interior.pdf"
MANIFEST_NAME = "interior.json"
PREFLIGHT_NAME = "preflight.json"


@dataclass(frozen=True)
class InteriorBuild:
    report: BatchReport
    plan: PublicationPlan
    layout: InteriorLayout
    pdf: bytes
    manifest: dict[str, object]


@dataclass(frozen=True)
class InteriorOutput:
    pdf: Path
    manifest: Path


def _canonical(data: object) -> bytes:
    return json.dumps(
        data, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False
    ).encode("ascii")


def build_interior(project: Project, spec: PrintSpecification) -> InteriorBuild:
    """Run the full pipeline in memory. Raises ProjectError or InteriorError."""
    report, plan = build_publication(project)
    verification = verify_publication_plan(plan, project, report)
    if not verification.valid:
        raise RuntimeError(f"Publication plan failed verification: {verification.issues!r}")
    layout = layout_interior(plan, report, spec)
    layout_issues = validate_layout(layout, plan, report)
    if layout_issues:
        raise InteriorError("layout_validation", layout_issues)
    pdf = render_pdf(layout)
    pdf_issues = inspect_pdf(pdf, layout)
    if pdf_issues:
        raise InteriorError("pdf_verification", pdf_issues)
    return InteriorBuild(report, plan, layout, pdf, interior_manifest(layout, pdf))


# Manifest fields that, together, are the interior identity's inputs.
IDENTITY_INPUTS = (
    "identity",
    "plan_digest",
    "print_profile",
    "renderer_version",
    "engine_version",
    "pdf_library",
    "fonts",
)


def toolchain() -> dict[str, object]:
    """Output-affecting renderer inputs other than source, plan and profile."""
    return {
        "renderer_version": RENDERER_VERSION,
        "engine_version": __version__,
        "pdf_library": f"reportlab {REPORTLAB_VERSION}",
        "fonts": font_manifest(),
    }


def interior_identity(inputs: dict[str, object]) -> str:
    material = {key: inputs[key] for key in IDENTITY_INPUTS}
    digest = hashlib.sha256(_canonical(material)).hexdigest()
    return f"pp{IDENTITY_VERSION}-interior-sha256-{digest}"


def interior_manifest(layout: InteriorLayout, pdf: bytes) -> dict[str, object]:
    """Deterministic traceability record. It contains no timestamps or paths."""
    spec = layout.spec
    inputs = {
        "identity": layout.identity,
        "plan_digest": layout.plan_digest,
        "print_profile": spec.to_dict(),
        **toolchain(),
    }
    return {
        "manifest_version": MANIFEST_VERSION,
        "book_id": layout.book_id,
        "interior_identity": interior_identity(inputs),
        **inputs,
        "trim": {
            "name": spec.trim.name,
            "width_in": to_inches(spec.trim.width),
            "height_in": to_inches(spec.trim.height),
            "bleed": spec.bleed,
        },
        "page_count": len(layout.pages),
        "pdf": {
            "file": PDF_NAME,
            "sha256": hashlib.sha256(pdf).hexdigest(),
            "bytes": len(pdf),
        },
        "warnings": [issue.to_dict() for issue in layout.warnings],
    }


def _output_issue(code: str, message: str) -> InteriorError:
    return InteriorError("output", (LayoutIssue(code, message, region="output"),))


def check_output_directory(output: Path, source_directory: Path) -> Path:
    """Resolve at write time and keep generated files disjoint from source."""
    try:
        resolved = output.resolve()
        source = source_directory.resolve()
    except (OSError, RuntimeError) as error:
        raise _output_issue("output_unavailable", f"Cannot resolve output: {error}") from error
    if resolved.is_relative_to(source) or source.is_relative_to(resolved):
        raise _output_issue("source_overlap", "Output and source directories must be disjoint.")
    if resolved.exists() and not resolved.is_dir():
        raise _output_issue("not_directory", f"Output is not a directory: {resolved}")
    return resolved


def _check_ownership(directory: Path, book_id: str) -> None:
    """Replace only an interior this book previously wrote; never unrelated files."""
    pdf, manifest = directory / PDF_NAME, directory / MANIFEST_NAME
    for path in (pdf, manifest):
        if path.is_symlink() or (path.exists() and not path.is_file()):
            raise _output_issue("output_collision", f"Refusing to replace {path.name}.")
    if not manifest.exists():
        if pdf.exists():
            raise _output_issue(
                "output_collision",
                f"{PDF_NAME} exists without a PuzzlePress manifest; refusing to replace it.",
            )
        return
    try:
        existing = json.loads(manifest.read_text(encoding="utf-8"))
    except (OSError, UnicodeError, ValueError) as error:
        raise _output_issue(
            "output_collision", f"Existing {MANIFEST_NAME} is unreadable: {error}"
        ) from error
    if not isinstance(existing, dict) or existing.get("book_id") != book_id:
        raise _output_issue(
            "output_collision", f"{MANIFEST_NAME} belongs to another book; refusing to replace it."
        )


def _stage(directory: Path, data: bytes, suffix: str, prefix: str = ".interior-") -> Path:
    handle, name = tempfile.mkstemp(prefix=prefix, suffix=suffix, dir=directory)
    path = Path(name)
    try:
        with os.fdopen(handle, "wb") as stream:
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        if path.read_bytes() != data:
            raise _output_issue("write_failed", "Staged output does not match rendered bytes.")
    except BaseException:
        path.unlink(missing_ok=True)
        raise
    return path


def write_interior(build: InteriorBuild, output: Path, source_directory: Path) -> InteriorOutput:
    """Atomically replace interior.pdf and interior.json in the output directory.

    Files are staged beside their targets, verified, then moved with os.replace,
    so a failure never leaves a partial PDF under the final name.
    """
    directory = check_output_directory(output, source_directory)
    manifest_bytes = (
        json.dumps(build.manifest, sort_keys=True, indent=2, ensure_ascii=True, allow_nan=False)
        + "\n"
    ).encode("ascii")
    staged: list[Path] = []
    try:
        directory.mkdir(parents=True, exist_ok=True)
        # Recheck after creation: a symlinked or racing directory must still be disjoint.
        directory = check_output_directory(directory, source_directory)
        _check_ownership(directory, build.layout.book_id)
        staged.append(_stage(directory, build.pdf, ".pdf.tmp"))
        staged.append(_stage(directory, manifest_bytes, ".json.tmp"))
        pdf, manifest = directory / PDF_NAME, directory / MANIFEST_NAME
        os.replace(staged[0], pdf)
        os.replace(staged[1], manifest)
        staged.clear()
    except OSError as error:
        raise _output_issue("write_failed", f"Cannot write interior: {error}") from error
    finally:
        for path in staged:
            path.unlink(missing_ok=True)
    if hashlib.sha256(pdf.read_bytes()).hexdigest() != hashlib.sha256(build.pdf).hexdigest():
        raise _output_issue("write_failed", "Written PDF does not match the verified bytes.")
    return InteriorOutput(pdf, manifest)


def write_preflight_report(data: bytes, book_id: str, output: Path, source_directory: Path) -> Path:
    """Atomically replace preflight.json beside an interior this book owns.

    The report is written only next to an existing manifest naming the same
    book; it never creates an output directory or touches the PDF or manifest.
    """
    directory = check_output_directory(output, source_directory)
    manifest, target = directory / MANIFEST_NAME, directory / PREFLIGHT_NAME
    if not directory.is_dir() or not manifest.is_file() or manifest.is_symlink():
        raise _output_issue("output_missing", "No interior manifest to report beside.")
    _check_ownership(directory, book_id)
    if target.is_symlink() or (target.exists() and not target.is_file()):
        raise _output_issue("output_collision", f"Refusing to replace {PREFLIGHT_NAME}.")
    staged: Path | None = None
    try:
        staged = _stage(directory, data, ".preflight.tmp")
        os.replace(staged, target)
        staged = None
    except OSError as error:
        raise _output_issue("write_failed", f"Cannot write preflight report: {error}") from error
    finally:
        if staged is not None:
            staged.unlink(missing_ok=True)
    return target
