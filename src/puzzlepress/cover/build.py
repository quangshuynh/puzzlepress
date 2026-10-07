"""Cover build pipeline and its only filesystem writer.

interior.json + interior.pdf -> verified interior facts -> geometry
photograph (digest-pinned) -> decode -> layout -> layout validation
-> photo pixels -> PDF -> PDF inspection -> cover.pdf + cover.json.

`render_cover` is pure. `build_cover` reads the interior and the photograph;
`write_cover` is the single write boundary. Geometry comes only from a current
interior: its page count is counted in the PDF and must equal its manifest.
"""

import hashlib
import io
import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path

import PIL
from pypdf import PdfReader
from pypdf.errors import PyPdfError
from reportlab import Version as REPORTLAB_VERSION

from .. import __version__
from ..cover_config import CoverConfig
from ..identity import IDENTITY_VERSION, build_identity
from ..interior.build import (
    MANIFEST_NAME as INTERIOR_MANIFEST,
)
from ..interior.build import (
    _output_issue,
    _stage,
    check_output_directory,
    interior_identity,
    toolchain,
)
from ..interior.issues import InteriorError, LayoutIssue
from ..interior.spec import KDP_COVER, PROFILES, Paper, to_inches
from ..models import Project
from ..preflight.context import parse_manifest, read_interior_artifacts
from . import geometry as geometry_module
from .assets import Photo, decode_photo, read_asset
from .fonts import font_manifest
from .geometry import cover_geometry, trim_name
from .inspection import inspect_cover_pdf
from .issues import CoverError, cover_error
from .layout import CoverCopy, layout_cover
from .model import CoverLayout
from .render import JPEG_QUALITY, prepare_photo, render_cover_pdf
from .validation import validate_cover_layout

# Bump when cover drawing or layout changes output for identical inputs.
COVER_RENDERER_VERSION = 1
# Bump when cover geometry rules (KDP constants, design insets, barcode area) change.
COVER_PROFILE_VERSION = 1
MANIFEST_VERSION = 1
PDF_NAME = "cover.pdf"
MANIFEST_NAME = "cover.json"
PREFLIGHT_NAME = "cover-preflight.json"
COLOR_MODEL = (
    "DeviceRGB: sRGB-normalized photograph and fills; no CMYK conversion or ICC output intent"
)


@dataclass(frozen=True)
class InteriorFacts:
    """Physical facts of a current, verified interior build."""

    book_id: str
    interior_identity: str
    source_identity: str
    pdf_sha256: str
    page_count: int
    profile: dict[str, object]  # The print profile exactly as recorded.
    trim_width: float  # Points.
    trim_height: float
    paper: Paper

    def physical(self) -> dict[str, object]:
        """What the cover's geometry depends on; any change makes a cover stale."""
        return {
            "page_count": self.page_count,
            "profile_id": self.profile["profile_id"],
            "profile_version": self.profile["profile_version"],
            "trim_in": [to_inches(self.trim_width), to_inches(self.trim_height)],
            "paper": self.paper.value,
            "ink": self.profile["ink"],
        }


def _interior_error(code: str, message: str) -> CoverError:
    return cover_error("interior", code, message, region="interior")


def read_interior_facts(directory: Path, project: Project) -> InteriorFacts:
    """Read interior.pdf/interior.json and require them current for this project.

    Raises CoverError(stage 'interior'): interior_missing, interior_invalid,
    interior_foreign, interior_mismatch or interior_stale. Never builds or repairs.
    """
    artifacts = read_interior_artifacts(directory)
    if artifacts.pdf is None or artifacts.manifest is None:
        raise _interior_error(
            "interior_missing", "Build the interior first: the cover is sized from it."
        )
    manifest, problem = parse_manifest(artifacts.manifest)
    if manifest is None:
        raise _interior_error("interior_invalid", problem or "interior.json is unreadable.")
    if manifest["book_id"] != project.book.id:
        raise _interior_error("interior_foreign", "The interior belongs to another book.")
    pdf = manifest["pdf"]
    assert isinstance(pdf, dict)
    digest = hashlib.sha256(artifacts.pdf).hexdigest()
    if pdf["sha256"] != digest or pdf["bytes"] != len(artifacts.pdf):
        raise _interior_error(
            "interior_mismatch", "interior.pdf is not the file its manifest describes."
        )
    if interior_identity(manifest) != manifest["interior_identity"]:
        raise _interior_error("interior_mismatch", "interior.json's identity does not recompute.")
    if manifest["identity"] != build_identity(project):
        raise _interior_error(
            "interior_stale", "The interior predates the current source. Rebuild the interior."
        )
    recorded = manifest["print_profile"]
    assert isinstance(recorded, dict)
    spec = PROFILES.get(str(recorded.get("profile_id")))
    if spec is None or json.loads(json.dumps(spec.to_dict())) != recorded:
        raise _interior_error(
            "interior_stale", "The interior's print profile changed. Rebuild the interior."
        )
    current = json.loads(json.dumps(toolchain()))
    if any(manifest[key] != value for key, value in current.items()):
        raise _interior_error(
            "interior_stale", "The interior's renderer or fonts changed. Rebuild the interior."
        )
    try:
        pages = len(PdfReader(io.BytesIO(artifacts.pdf), strict=True).pages)
    except (PyPdfError, ValueError, KeyError, TypeError, OSError) as error:
        message = f"interior.pdf does not parse: {error}"
        raise _interior_error("interior_invalid", message) from error
    if pages != manifest["page_count"]:
        raise _interior_error(
            "interior_mismatch", "interior.pdf's page count differs from its manifest."
        )
    return InteriorFacts(
        project.book.id,
        str(manifest["interior_identity"]),
        str(manifest["identity"]),
        digest,
        pages,
        recorded,
        spec.trim.width,
        spec.trim.height,
        spec.paper,
    )


def cover_profile() -> dict[str, object]:
    """Output-affecting cover geometry rules (KDP values plus PuzzlePress choices)."""
    kdp = asdict(KDP_COVER)
    kdp["spine_per_page"] = [[paper.value, value] for paper, value in KDP_COVER.spine_per_page]
    return {
        "version": COVER_PROFILE_VERSION,
        "kdp": kdp,
        "design_inset": geometry_module.DESIGN_INSET,
        "barcode_offset": geometry_module.BARCODE_OFFSET,
        "barcode_clearance": geometry_module.BARCODE_CLEARANCE,
    }


def cover_toolchain() -> dict[str, object]:
    return {
        "renderer_version": COVER_RENDERER_VERSION,
        "engine_version": __version__,
        "pdf_library": f"reportlab {REPORTLAB_VERSION}",
        "image_library": f"pillow {PIL.__version__}",
        "fonts": font_manifest(),
    }


def semantic_config(config: CoverConfig) -> dict[str, object]:
    """Authored cover choices; the photo is identified by content, not by file name."""
    data = config.to_dict()
    data["image"] = {"sha256": config.image.sha256}
    return data


# Inputs whose canonical JSON is the cover identity.
IDENTITY_INPUTS = ("book_id", "cover", "copy", "interior", "cover_profile", "toolchain")


def cover_inputs(
    project: Project, config: CoverConfig, interior: InteriorFacts
) -> dict[str, object]:
    return {
        "book_id": project.book.id,
        "cover": semantic_config(config),
        "copy": CoverCopy.from_project(project).to_dict(),
        "interior": interior.physical(),
        "cover_profile": cover_profile(),
        "toolchain": cover_toolchain(),
    }


def _canonical(data: object) -> bytes:
    return json.dumps(
        data, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False
    ).encode("ascii")


def cover_identity(inputs: dict[str, object]) -> str:
    material = {key: inputs[key] for key in IDENTITY_INPUTS}
    digest = hashlib.sha256(_canonical(material)).hexdigest()
    return f"pp{IDENTITY_VERSION}-cover-sha256-{digest}"


@dataclass(frozen=True)
class CoverBuild:
    layout: CoverLayout
    pdf: bytes
    manifest: dict[str, object]
    image_size: tuple[int, int]


def render_cover(
    project: Project, interior: InteriorFacts, photo: Photo, asset_path: str | None = None
) -> CoverBuild:
    """Pure: lay out, validate, render and inspect. Raises CoverError."""
    config = project.cover
    if config is None:
        raise cover_error("config", "cover_missing", "This project has no cover section.")
    if photo.info.sha256 != config.image.sha256:
        raise cover_error(
            "asset", "asset_digest_mismatch", "The photo is not the configured one.", "cover.image"
        )
    geometry = cover_geometry(
        interior.page_count, interior.trim_width, interior.trim_height, interior.paper
    )
    copy = CoverCopy.from_project(project)
    layout = layout_cover(project.book.id, copy, config, geometry, photo.info)
    issues = validate_cover_layout(layout, interior.trim_width, interior.trim_height)
    if issues:
        raise CoverError("layout_validation", issues)
    jpeg, size = prepare_photo(photo, layout.photo)
    pdf = render_cover_pdf(layout, jpeg, size)
    pdf_issues = inspect_cover_pdf(pdf, layout, size)
    if pdf_issues:
        raise CoverError("pdf_verification", pdf_issues)
    inputs = cover_inputs(project, config, interior)
    manifest: dict[str, object] = {
        "manifest_version": MANIFEST_VERSION,
        "cover_identity": cover_identity(inputs),
        **inputs,
        "provenance": {
            "interior_identity": interior.interior_identity,
            "source_identity": interior.source_identity,
            "interior_pdf_sha256": interior.pdf_sha256,
            "photo_path": asset_path or config.image.path,
        },
        "geometry": {"trim": trim_name(interior.trim_width, interior.trim_height)}
        | geometry.to_dict(),
        "photo": photo.info.to_dict(),
        "resolution": layout.resolution.to_dict(),
        "embedded_photo": {
            "pixels": list(size),
            "encoding": f"baseline JPEG, quality {JPEG_QUALITY}, 4:4:4, no metadata",
        },
        "spine_text": layout.spine.to_dict(),
        "color": COLOR_MODEL,
        "pdf": {
            "file": PDF_NAME,
            "sha256": hashlib.sha256(pdf).hexdigest(),
            "bytes": len(pdf),
        },
    }
    return CoverBuild(layout, pdf, manifest, size)


def build_cover(project: Project, project_directory: Path, output: Path) -> CoverBuild:
    """Read the interior beside the cover and the pinned photo; render in memory."""
    if project.cover is None:
        raise cover_error("config", "cover_missing", "This project has no cover section.")
    try:
        directory = check_output_directory(output, project_directory)
    except InteriorError as error:
        raise CoverError("output", error.issues) from error
    interior = read_interior_facts(directory, project)
    photo = decode_photo(read_asset(project_directory, project.cover.image))
    return render_cover(project, interior, photo)


@dataclass(frozen=True)
class CoverOutput:
    pdf: Path
    manifest: Path


def _owned(directory: Path, book_id: str) -> None:
    """Write only beside this book's interior, replacing only this book's cover."""
    for name in (PDF_NAME, MANIFEST_NAME, PREFLIGHT_NAME):
        path = directory / name
        if path.is_symlink() or (path.exists() and not path.is_file()):
            raise CoverError("output", (LayoutIssue("output_collision", f"Refusing {name}."),))
    for name in (INTERIOR_MANIFEST, MANIFEST_NAME):
        path = directory / name
        if not path.exists():
            if name == INTERIOR_MANIFEST:
                raise CoverError(
                    "output", (LayoutIssue("output_missing", "No interior to write beside."),)
                )
            if (directory / PDF_NAME).exists():
                raise CoverError(
                    "output",
                    (
                        LayoutIssue(
                            "output_collision",
                            f"{PDF_NAME} exists without a PuzzlePress manifest; refusing it.",
                        ),
                    ),
                )
            continue
        try:
            existing = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, UnicodeError, ValueError) as error:
            raise CoverError(
                "output", (LayoutIssue("output_collision", f"{name} is unreadable: {error}"),)
            ) from error
        if not isinstance(existing, dict) or existing.get("book_id") != book_id:
            raise CoverError(
                "output", (LayoutIssue("output_collision", f"{name} belongs to another book."),)
            )


def manifest_bytes(manifest: dict[str, object]) -> bytes:
    text = json.dumps(manifest, sort_keys=True, indent=2, ensure_ascii=True, allow_nan=False)
    return (text + "\n").encode("ascii")


def write_cover(build: CoverBuild, output: Path, source_directory: Path) -> CoverOutput:
    """Replace cover.pdf and cover.json beside this book's interior.

    Both are staged, fsynced and read back, then moved with os.replace. The two
    replacements are not one transaction; cover.json's PDF SHA-256 exposes a pair
    that an interruption left mismatched.
    """
    try:
        directory = check_output_directory(output, source_directory)
    except InteriorError as error:
        raise CoverError("output", error.issues) from error
    if not directory.is_dir():
        raise CoverError("output", (LayoutIssue("output_missing", "No interior to write beside."),))
    _owned(directory, build.layout.book_id)
    data = manifest_bytes(build.manifest)
    staged: list[Path] = []
    try:
        staged.append(_stage(directory, build.pdf, ".pdf.tmp", ".cover-"))
        staged.append(_stage(directory, data, ".json.tmp", ".cover-"))
        pdf, manifest = directory / PDF_NAME, directory / MANIFEST_NAME
        os.replace(staged[0], pdf)
        os.replace(staged[1], manifest)
        staged.clear()
    except InteriorError as error:
        raise CoverError("output", error.issues) from error
    except OSError as error:
        raise CoverError("output", _output_issue("write_failed", str(error)).issues) from error
    finally:
        for path in staged:
            path.unlink(missing_ok=True)
    if hashlib.sha256(pdf.read_bytes()).digest() != hashlib.sha256(build.pdf).digest():
        raise CoverError(
            "output", (LayoutIssue("write_failed", "Written cover differs from verified bytes."),)
        )
    return CoverOutput(pdf, manifest)


def write_cover_preflight(data: bytes, book_id: str, output: Path, source_directory: Path) -> Path:
    """Replace cover-preflight.json beside an interior this book owns."""
    try:
        directory = check_output_directory(output, source_directory)
    except InteriorError as error:
        raise CoverError("output", error.issues) from error
    if not directory.is_dir():
        missing = LayoutIssue("output_missing", "No interior to report beside.")
        raise CoverError("output", (missing,))
    _owned(directory, book_id)
    target = directory / PREFLIGHT_NAME
    staged: Path | None = None
    try:
        staged = _stage(directory, data, ".preflight.tmp", ".cover-")
        os.replace(staged, target)
        staged = None
    except InteriorError as error:
        raise CoverError("output", error.issues) from error
    except OSError as error:
        raise CoverError("output", _output_issue("write_failed", str(error)).issues) from error
    finally:
        if staged is not None:
            staged.unlink(missing_ok=True)
    return target
