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
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from pathlib import Path

import PIL
from pypdf import PdfReader
from pypdf.errors import PyPdfError
from reportlab import Version as REPORTLAB_VERSION

from .. import __version__
from ..cover_config import CoverConfig, CoverImage
from ..cover_design import EDITING_FIELDS, PhotoElement
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
from .font_assets import NO_FONTS, CoverFonts, load_cover_fonts
from .fonts import font_manifest
from .geometry import cover_geometry, trim_name
from .inspection import inspect_cover_pdf
from .issues import CoverError, cover_error
from .layout import CoverCopy, cover_display, layout_cover
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
    # Why the interior is out of date, when it was read without requiring currency.
    stale: str | None = None

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


def read_interior_facts(
    directory: Path, project: Project, require_current: bool = True
) -> InteriorFacts:
    """Read interior.pdf/interior.json and, by default, require them current.

    Raises CoverError(stage 'interior'): interior_missing, interior_invalid,
    interior_foreign, interior_mismatch or interior_stale. With `require_current`
    false (Studio draft previews) a stale but intact interior is returned with its
    `stale` reason; integrity is always required. Never builds or repairs.
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
    recorded = manifest["print_profile"]
    assert isinstance(recorded, dict)
    spec = PROFILES.get(str(recorded.get("profile_id")))
    if spec is None:
        raise _interior_error("interior_invalid", "The interior's print profile is unknown.")
    stale: str | None = None
    if manifest["identity"] != build_identity(project):
        stale = "The interior predates the current source. Rebuild the interior."
    elif json.loads(json.dumps(spec.to_dict())) != recorded:
        stale = "The interior's print profile changed. Rebuild the interior."
    elif any(manifest[k] != v for k, v in json.loads(json.dumps(toolchain())).items()):
        stale = "The interior's renderer or fonts changed. Rebuild the interior."
    if stale and require_current:
        raise _interior_error("interior_stale", stale)
    if stale and recorded != json.loads(json.dumps(spec.to_dict())):
        # Physical facts come from the recorded profile, never a redefined one.
        raise _interior_error("interior_stale", stale)
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
        stale,
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
    """Authored cover choices; photo and fonts are identified by content, not file name.

    A font's recorded license and source are provenance, not output: they are left
    out so recording them never makes a cover stale.
    """
    data = config.to_dict()
    if config.image is not None:
        data["image"] = {"sha256": config.image.sha256}
    if config.designed:
        elements = []
        for element in config.elements:
            item = {k: v for k, v in element.to_dict().items() if k not in EDITING_FIELDS}
            if isinstance(element, PhotoElement):
                item["image"] = {"sha256": element.image.sha256}
            elements.append(item)
        data["elements"] = elements
    if config.fonts:
        data["fonts"] = [{"id": font.id, "sha256": font.sha256} for font in config.fonts]
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
    image_sizes: tuple[tuple[int, int], ...]  # Embedded pixels of each photograph, in order.
    layout_issues: tuple[LayoutIssue, ...] = ()  # Only from allow_layout_issues previews.

    @property
    def image_size(self) -> tuple[int, int]:
        """The embedded photograph of a version 1 or 2 cover."""
        return self.image_sizes[0]


ENCODING = f"baseline JPEG, quality {JPEG_QUALITY}, 4:4:4, no metadata"


def render_cover(
    project: Project,
    interior: InteriorFacts,
    photo: Photo | Mapping[str, Photo],
    asset_path: str | None = None,
    fonts: CoverFonts = NO_FONTS,
    allow_layout_issues: bool = False,
) -> CoverBuild:
    """Pure: lay out, validate, render and inspect. Raises CoverError.

    `photo` is the decoded photograph, or every photograph the configuration
    references keyed by SHA-256 (version 3). `fonts` are the configuration's
    imported fonts, already loaded. With `allow_layout_issues` (Studio draft
    previews only) a layout that fails validation, such as text moved out of its
    safe area, still renders and its issues are returned in
    `CoverBuild.layout_issues`; builds never pass it.
    """
    config = project.cover
    if config is None:
        raise cover_error("config", "cover_missing", "This project has no cover section.")
    missing = [font.id for font in config.fonts if font.id not in fonts.by_id]
    if missing:
        raise cover_error(
            "asset",
            "font_missing",
            f"Imported fonts are not loaded: {', '.join(missing)}.",
            "cover.fonts",
        )
    photos = photo if isinstance(photo, Mapping) else {photo.info.sha256: photo}
    for image in config.images():
        if image.sha256 not in photos or photos[image.sha256].info.sha256 != image.sha256:
            raise cover_error(
                "asset",
                "asset_digest_mismatch",
                "The photo is not the configured one.",
                "cover.image",
            )
    geometry = cover_geometry(
        interior.page_count, interior.trim_width, interior.trim_height, interior.paper
    )
    copy = CoverCopy.from_project(project)
    infos = {digest: decoded.info for digest, decoded in photos.items()}
    layout = layout_cover(project.book.id, copy, config, geometry, infos, fonts)
    issues = validate_cover_layout(layout, interior.trim_width, interior.trim_height)
    if issues and not allow_layout_issues:
        raise CoverError("layout_validation", issues)
    encoded = [prepare_photo(photos[item.sha256], item) for item in layout.photos]
    sizes = tuple(size for _, size in encoded)
    pdf = render_cover_pdf(layout, encoded)
    pdf_issues = inspect_cover_pdf(pdf, layout, sizes)
    if pdf_issues:
        raise CoverError("pdf_verification", pdf_issues)
    inputs = cover_inputs(project, config, interior)
    provenance: dict[str, object] = {
        "interior_identity": interior.interior_identity,
        "source_identity": interior.source_identity,
        "interior_pdf_sha256": interior.pdf_sha256,
    }
    resolution = layout.resolution
    pictures: dict[str, object]
    if config.image is not None:
        provenance["photo_path"] = asset_path or config.image.path
        pictures = {
            "photo": photos[config.image.sha256].info.to_dict(),
            "resolution": None if resolution is None else resolution.to_dict(),
            "embedded_photo": {"pixels": list(sizes[0]), "encoding": ENCODING},
        }
    else:
        provenance["photo_paths"] = sorted({image.path for image in config.images()})
        pictures = {
            "photos": [
                {
                    "role": item.role,
                    "photo": photos[item.sha256].info.to_dict(),
                    "resolution": res.to_dict(),
                    "embedded": {"pixels": list(size), "encoding": ENCODING},
                }
                for item, res, size in zip(layout.photos, layout.resolutions, sizes, strict=True)
            ],
            "resolution": None if resolution is None else resolution.to_dict(),
            "design_warnings": [issue.to_dict() for issue in layout.warnings],
        }
    manifest: dict[str, object] = {
        "manifest_version": MANIFEST_VERSION,
        "cover_identity": cover_identity(inputs),
        **inputs,
        "provenance": provenance,
        "geometry": {"trim": trim_name(interior.trim_width, interior.trim_height)}
        | geometry.to_dict(),
        **pictures,
        "spine_text": layout.spine.to_dict(),
        # What the front and back print for each book detail (None: hidden or absent).
        "display": cover_display(config, copy),
        "color": COLOR_MODEL,
        "pdf": {
            "file": PDF_NAME,
            "sha256": hashlib.sha256(pdf).hexdigest(),
            "bytes": len(pdf),
        },
    }
    return CoverBuild(layout, pdf, manifest, sizes, issues)


def build_cover(project: Project, project_directory: Path, output: Path) -> CoverBuild:
    """Read the interior beside the cover and the pinned photo; render in memory."""
    if project.cover is None:
        raise cover_error("config", "cover_missing", "This project has no cover section.")
    try:
        directory = check_output_directory(output, project_directory)
    except InteriorError as error:
        raise CoverError("output", error.issues) from error
    interior = read_interior_facts(directory, project)
    photos = load_photos(project_directory, project.cover.images())
    fonts = load_cover_fonts(project_directory, project.cover)
    return render_cover(project, interior, photos, fonts=fonts)


def load_photos(project_directory: Path, images: tuple[CoverImage, ...]) -> dict[str, Photo]:
    """Read, verify and decode every referenced photograph. Raises CoverError."""
    photos: dict[str, Photo] = {}
    for image in images:
        if image.sha256 not in photos:
            photos[image.sha256] = decode_photo(read_asset(project_directory, image))
    return photos


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
