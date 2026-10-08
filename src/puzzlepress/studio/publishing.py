"""Studio adapter for the Publishing workspace: readiness, draft checks and export.

Every decision is made by `puzzlepress.publishing`, exactly as for `puzzlepress
publish`; this module locates the saved project's folders, serializes requests,
caches reports by the bytes they depend on and presents results. Exports build
only from the saved source revision. Nothing contacts Amazon, and no caller-
supplied path is ever read or written.
"""

import hashlib
from collections import OrderedDict
from pathlib import Path

from puzzlepress.interior import InteriorError
from puzzlepress.interior.build import check_output_directory
from puzzlepress.models import Project
from puzzlepress.project import resolve_output_directory
from puzzlepress.publishing import (
    PackageError,
    PublishingReadinessReport,
    assemble_package,
    evaluate_readiness,
    export_state,
    validate_metadata,
    write_package,
)
from puzzlepress.publishing.package import ARCHIVE, DIRECTORY, MANIFEST, PURPOSES
from puzzlepress.publishing.submission import checklist_markdown, kdp_metadata

from .editing import DraftStore
from .service import StudioError, StudioService

LOCK_WAIT = 60.0
WATCHED = ("interior.pdf", "interior.json", "cover.pdf", "cover.json", "preflight.json",
           "cover-preflight.json", f"{DIRECTORY}/{MANIFEST}", ARCHIVE)  # fmt: skip


class PublishingService:
    def __init__(self, service: StudioService, drafts: DraftStore) -> None:
        self.service = service
        self.store = service.store
        self.drafts = drafts
        self._reports: OrderedDict[tuple[str, ...], dict[str, object]] = OrderedDict()

    def _folders(self, key: str, project: Project) -> tuple[Path, Path]:
        source = self.store.source(key).parent
        try:
            directory = check_output_directory(resolve_output_directory(project, source), source)
        except InteriorError as error:
            raise StudioError(
                503, "output_unavailable", "The project's output directory is unavailable."
            ) from error
        return source, directory

    # ------------------------------------------------------------ draft metadata

    def draft(self, key: str, source_data: object) -> dict[str, object]:
        """Python-authoritative metadata findings for an unsaved draft (no files)."""
        project = self.drafts.validate(key, source_data)
        return {"metadata": validate_metadata(project).to_dict()}

    # ------------------------------------------------------------ status

    def status(self, key: str) -> dict[str, object]:
        with self.service.exclusive(wait=LOCK_WAIT):
            return self._status(key)

    def _status(self, key: str) -> dict[str, object]:
        project, revision = self.store.snapshot(key)
        source, directory = self._folders(key, project)
        photo = source / project.cover.image.path if project.cover else source / "-"
        cache_key = (
            key,
            revision,
            *(_digest(directory / name) for name in WATCHED),
            _digest(photo),
        )
        cached = self._reports.get(cache_key)
        if cached is None:
            report = evaluate_readiness(project, source, directory)
            cached = self._present(project, report, source, directory)
            self._reports[cache_key] = cached
            while len(self._reports) > 8:
                self._reports.popitem(last=False)
        return {"key": key, "revision": revision, **cached}

    def _present(
        self, project: Project, report: PublishingReadinessReport, source: Path, directory: Path
    ) -> dict[str, object]:
        identity = assemble_package(report).identity if report.package_ready else None
        exported = export_state(directory, source, report.book_id, identity)
        cover = report.cover_bytes()
        return {
            "readiness": report.to_dict(),
            "metadata_record": kdp_metadata(report),
            "checklist": checklist_markdown(report),
            "package": {
                "identity": identity,
                "export": exported.to_dict(),
                "location": f"{project.output.directory}/{DIRECTORY}",
                "archive": f"{project.output.directory}/{ARCHIVE}",
                "files": [
                    {"name": name, "purpose": purpose} for name, purpose in sorted(PURPOSES.items())
                ]
                + [{"name": MANIFEST, "purpose": "File list, digests and the package identity."}],
            },
            "cover_preview": None
            if cover is None or report.cover_state != "current"
            else {"pdf_sha256": hashlib.sha256(cover[0]).hexdigest()},
        }

    # ------------------------------------------------------------ export

    def export(self, key: str, revision: str, archive: bool) -> dict[str, object]:
        """Export the package for the saved source exactly at `revision`."""
        with self.service.exclusive(wait=LOCK_WAIT):
            project, current = self.store.snapshot(key)
            if current != revision:
                raise StudioError(
                    409, "source_changed", "Saved source changed. Reload before exporting."
                )
            source, directory = self._folders(key, project)
            report = evaluate_readiness(project, source, directory)
            try:
                package = assemble_package(report)
                written = write_package(package, directory, source, archive=archive)
            except PackageError as error:
                return {
                    "export": {"success": False, "code": error.code, "message": str(error)},
                    **self._status(key),
                }
            return {
                "export": {
                    "success": True,
                    "identity": package.identity,
                    "archive": written.archive is not None,
                    "files": package.manifest["files"],
                },
                **self._status(key),
            }


def _digest(path: Path) -> str:
    try:
        if path.is_file() and not path.is_symlink():
            return hashlib.sha256(path.read_bytes()).hexdigest()
    except OSError:
        return "?"
    return "-"
