"""Studio adapter for Cover Studio: status, draft previews, photo import and builds.

Every decision is made by the core cover APIs used by `puzzlepress cover`; this
module locates the saved project's folders, caches decoded photos and rendered
draft PDFs in memory, and presents results. Previews are PDFium rasters of real
cover PDFs (a draft's PDF or cover.pdf), never recreated in the browser. Only
fixed artifact names and validated project asset references are ever read.
"""

import hashlib
import re
from collections import OrderedDict
from pathlib import Path
from threading import Lock

from puzzlepress.cover.assets import (
    MAX_ASSET_BYTES,
    Photo,
    decode_photo,
    import_photo,
    list_assets,
    read_asset,
)
from puzzlepress.cover.build import (
    PDF_NAME,
    CoverBuild,
    build_cover,
    read_interior_facts,
    render_cover,
    write_cover,
    write_cover_preflight,
)
from puzzlepress.cover.issues import CoverError
from puzzlepress.cover.model import CoverLayout
from puzzlepress.cover.preflight import RULESET_VERSION, preflight_cover, report_bytes
from puzzlepress.cover.validation import panel_of
from puzzlepress.interior import InteriorError
from puzzlepress.interior.build import check_output_directory
from puzzlepress.interior.model import Box
from puzzlepress.interior.spec import KDP
from puzzlepress.models import Project
from puzzlepress.project import resolve_output_directory

from .editing import DraftStore
from .preview import PageOutOfRange, PageRasterizer, PreviewUnavailable
from .service import StudioError, StudioService

DIGEST = re.compile(r"[0-9a-f]{64}")
# A full 8.5 x 11 in wrap is about 1260 x 810 pt: ~1 px/pt to view, 2.5 to inspect.
COVER_SCALES = {"preview": 1.0, "detail": 2.5}
LOCK_WAIT = 60.0
DRAFT_BUDGET = 160 * 1024 * 1024
PHOTO_CACHE = 2


def _box(box: Box) -> dict[str, float]:
    return {k: round(getattr(box, k), 3) for k in ("x", "y", "width", "height")}


def present_layout(layout: CoverLayout) -> dict[str, object]:
    """Authoritative geometry for overlays and crop interaction, in PDF points."""
    g = layout.geometry
    photo = layout.photo
    left, top, right, bottom = photo.window.normalized()
    return {
        "geometry": g.to_dict(),
        "texts": [
            {
                "role": text.role,
                "text": text.text,
                "panel": panel_of(text),
                "size": text.size,
                "rotated": text.rotated,
                "box": _box(text.bounds),
            }
            for text in layout.texts
        ],
        "panels": [{"role": p.role, "box": _box(p.box)} for p in layout.panels],
        "photo": {
            "region": _box(photo.region),
            "window": {"left": left, "top": top, "right": right, "bottom": bottom},
            "center": list(photo.window.center),
            "pixels": list(photo.pixels),
        },
        "resolution": layout.resolution.to_dict(),
        "spine_text": layout.spine.to_dict(),
    }


def layout_checks(layout: CoverLayout, page_count: int) -> list[dict[str, str]]:
    """Readiness facts a draft can know before a cover is built (no artifacts yet)."""
    checks: list[dict[str, str]] = []
    res = layout.resolution
    if res.status == "image_too_small":
        checks.append(
            {
                "code": "image_too_small",
                "severity": "error",
                "message": f"The photo reaches at most {res.max_dpi:.0f} DPI here; KDP needs "
                f"{res.minimum_dpi:g}. Use a larger photograph.",
            }
        )
    elif res.status == "image_low_effective_dpi":
        checks.append(
            {
                "code": "image_low_effective_dpi",
                "severity": "error",
                "message": f"This crop prints at {res.effective_dpi:.0f} DPI; KDP needs "
                f"{res.minimum_dpi:g}. Zoom out (up to {res.max_dpi:.0f} DPI available).",
            }
        )
    if page_count < KDP.min_pages:
        checks.append(
            {
                "code": "kdp_minimum_page_count",
                "severity": "error",
                "message": f"The interior has {page_count} pages; KDP paperbacks need "
                f"{KDP.min_pages}. The cover still previews and builds.",
            }
        )
    reasons = {
        "page_count": "Spine text is omitted: KDP prints it only from 80 pages.",
        "spine_too_narrow": "Spine text is omitted: the spine cannot hold 7 pt type.",
        "authored": "Spine text is off for this cover.",
    }
    if layout.spine.reason:
        checks.append(
            {
                "code": "spine_text_omitted",
                "severity": "info",
                "message": reasons[layout.spine.reason],
            }
        )
    return checks


class CoverService:
    def __init__(self, service: StudioService, drafts: DraftStore) -> None:
        self.service = service
        self.store = service.store
        self.drafts = drafts
        self.rasterizer = PageRasterizer(scales=COVER_SCALES)
        self._lock = Lock()
        self._photos: OrderedDict[str, Photo] = OrderedDict()
        self._pdfs: OrderedDict[str, bytes] = OrderedDict()
        self._pdf_bytes = 0
        self._reports: OrderedDict[tuple[str, ...], dict[str, object]] = OrderedDict()

    # ------------------------------------------------------------ locating

    def _folders(self, key: str, project: Project) -> tuple[Path, Path]:
        source = self.store.source(key).parent
        try:
            directory = check_output_directory(resolve_output_directory(project, source), source)
        except InteriorError as error:
            raise StudioError(
                503, "output_unavailable", "The project's output directory is unavailable."
            ) from error
        return source, directory

    def _photo(self, source: Path, project: Project) -> Photo:
        assert project.cover is not None
        digest = project.cover.image.sha256
        with self._lock:
            cached = self._photos.get(digest)
            if cached is not None:
                self._photos.move_to_end(digest)
        data = read_asset(source, project.cover.image)  # Always re-verify the file.
        if cached is not None:
            return cached
        photo = decode_photo(data)
        with self._lock:
            self._photos[digest] = photo
            while len(self._photos) > PHOTO_CACHE:
                self._photos.popitem(last=False)
        return photo

    def _remember(self, pdf: bytes) -> str:
        digest = hashlib.sha256(pdf).hexdigest()
        with self._lock:
            if digest not in self._pdfs:
                self._pdfs[digest] = pdf
                self._pdf_bytes += len(pdf)
            self._pdfs.move_to_end(digest)
            while self._pdf_bytes > DRAFT_BUDGET and len(self._pdfs) > 1:
                _, evicted = self._pdfs.popitem(last=False)
                self._pdf_bytes -= len(evicted)
        return digest

    # ------------------------------------------------------------ assets

    def assets(self, key: str) -> dict[str, object]:
        source = self.store.source(key).parent
        try:
            entries = list_assets(source)
        except CoverError as error:
            raise StudioError(422, error.issues[0].code, error.issues[0].message) from error
        return {
            "assets": [
                {
                    "path": entry.path,
                    "problem": entry.problem,
                    **(entry.info.to_dict() if entry.info else {}),
                }
                for entry in entries
            ]
        }

    def import_photo(self, key: str, data: bytes, name: str) -> dict[str, object]:
        if len(data) > MAX_ASSET_BYTES:
            raise StudioError(413, "image_unsupported", "The photograph file is too large.")
        source = self.store.source(key).parent
        try:
            imported = import_photo(source, data, name)
        except CoverError as error:
            issue = error.issues[0]
            status = 503 if issue.code == "write_failed" else 422
            raise StudioError(status, issue.code, issue.message) from error
        return {
            "asset": {"path": imported.path, "reused": imported.reused, **imported.info.to_dict()},
            **self.assets(key),
        }

    # ------------------------------------------------------------ status and build

    def status(self, key: str) -> dict[str, object]:
        with self.service.exclusive(wait=LOCK_WAIT):
            return self._status(key)

    def _status(self, key: str, built: CoverBuild | None = None) -> dict[str, object]:
        project, revision = self.store.snapshot(key)
        base: dict[str, object] = {"key": key, "revision": revision, "ruleset": RULESET_VERSION}
        if project.cover is None:
            return {**base, "state": "no_config", "report": None, "preview": None}
        source, directory = self._folders(key, project)
        files = [
            directory / name
            for name in ("cover.pdf", "cover.json", "interior.pdf", "interior.json")
        ]
        photo = source / project.cover.image.path
        cache_key = (key, revision, *(_digest(path) for path in [*files, photo]))
        cached = self._reports.get(cache_key)
        if cached is None:
            report = preflight_cover(project, source, directory, built)
            data = report.to_dict()
            pdf = report.context.artifacts.pdf
            expected = report.context.expected
            cached = {
                "state": report.state,
                "report": data,
                "layout": present_layout(expected.layout) if expected else None,
                "preview": None
                if pdf is None
                else {"pdf_sha256": hashlib.sha256(pdf).hexdigest(), "scales": COVER_SCALES},
            }
            self._reports[cache_key] = cached
            while len(self._reports) > 8:
                self._reports.popitem(last=False)
        return {**base, **cached}

    def build(self, key: str, revision: str) -> dict[str, object]:
        """Build the saved source exactly at `revision`, then preflight what was written."""
        with self.service.exclusive(wait=LOCK_WAIT):
            project, current = self.store.snapshot(key)
            if current != revision:
                raise StudioError(
                    409, "source_changed", "Saved source changed. Reload before building."
                )
            if project.cover is None:
                raise StudioError(422, "no_cover", "This project has no cover section.")
            source, directory = self._folders(key, project)
            try:
                build = build_cover(project, source, directory)
                write_cover(build, directory, source)
            except CoverError as error:
                return {
                    "build": {
                        "success": False,
                        "stage": error.stage,
                        "diagnostics": [issue.to_dict() for issue in error.issues],
                    },
                    **self._status(key),
                }
            report = preflight_cover(project, source, directory, build)
            try:
                write_cover_preflight(report_bytes(report), project.book.id, directory, source)
            except CoverError:
                pass  # The report is still returned; cover-preflight.json is optional.
            return {"build": {"success": True}, **self._status(key, build)}

    # ------------------------------------------------------------ draft preview

    def draft(self, key: str, source_data: object) -> dict[str, object]:
        """Render the unsaved draft's cover in memory against the built interior."""
        project = self.drafts.validate(key, source_data)
        if project.cover is None:
            raise StudioError(422, "no_cover", "This draft has no cover section.")
        with self.service.exclusive(wait=LOCK_WAIT):
            source, directory = self._folders(key, project)
            try:
                interior = read_interior_facts(directory, project, require_current=False)
                photo = self._photo(source, project)
                build = render_cover(project, interior, photo)
            except CoverError as error:
                return {
                    "success": False,
                    "stage": error.stage,
                    "diagnostics": [issue.to_dict() for issue in error.issues],
                }
            digest = self._remember(build.pdf)
            return {
                "success": True,
                "interior": {
                    **interior.physical(),
                    "stale": interior.stale,
                    "interior_identity": interior.interior_identity,
                },
                "cover_identity": build.manifest["cover_identity"],
                "layout": present_layout(build.layout),
                "checks": layout_checks(build.layout, interior.page_count),
                "preview": {"pdf_sha256": digest, "scales": COVER_SCALES},
            }

    # ------------------------------------------------------------ rasters

    def image(self, key: str, pdf_digest: str, size: str) -> bytes:
        if size not in COVER_SCALES:
            raise StudioError(404, "not_found", "Unknown preview size.")
        if not DIGEST.fullmatch(pdf_digest):
            raise StudioError(422, "invalid_request", "Supply the cover PDF digest.")
        project = self.store.load(key)
        with self._lock:
            pdf = self._pdfs.get(pdf_digest)
        if pdf is None:
            _, directory = self._folders(key, project)
            path = directory / PDF_NAME
            data = path.read_bytes() if path.is_file() and not path.is_symlink() else None
            if data is None or hashlib.sha256(data).hexdigest() != pdf_digest:
                raise StudioError(
                    409, "preview_stale", "This cover preview is no longer available."
                )
            pdf = data
        try:
            return self.rasterizer.png(pdf, pdf_digest, 1, size)
        except PageOutOfRange as error:
            raise StudioError(404, "page_not_found", "The cover has no such page.") from error
        except PreviewUnavailable as error:
            raise StudioError(
                503, "preview_unavailable", "Install the studio extra (pypdfium2) for previews."
            ) from error


def _digest(path: Path) -> str:
    try:
        if path.is_file() and not path.is_symlink():
            return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return "?"
    return "-"
