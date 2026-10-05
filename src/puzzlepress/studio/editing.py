"""Project-level drafts and single-file, optimistic source transactions."""

import hashlib
import logging
import os
import tempfile
from pathlib import Path
from threading import Lock

from puzzlepress.errors import ProjectError
from puzzlepress.models import Project
from puzzlepress.project import load_project, resolve_output_directory
from puzzlepress.validation import validate_project
from puzzlepress.yaml_io import dump_project

from .service import ProjectStore, StudioError, project_detail

# All app instances in this process serialize saves. External editors are detected
# by byte revision immediately before replacement, not a cooperative file lock.
_SAVE_LOCK = Lock()
LOGGER = logging.getLogger(__name__)


class DraftStore:
    def __init__(self, store: ProjectStore) -> None:
        self.store = store

    def validate(self, key: str, source: object) -> Project:
        path = self.store.source(key)
        project = validate_project(source).require_project()
        resolve_output_directory(project, path.parent)
        return project

    def save(self, key: str, source: object, revision: str) -> dict[str, object]:
        with _SAVE_LOCK:
            project = self.validate(key, source)
            path = self.store.source(key)
            temporary: Path | None = None
            replaced = False
            try:
                self._check_revision(path, revision)
                # A sibling temporary file keeps replacement on the same filesystem.
                with tempfile.NamedTemporaryFile(
                    mode="wb", prefix=".puzzlepress-", suffix=".tmp", dir=path.parent, delete=False
                ) as stream:
                    temporary = Path(stream.name)
                    stream.write(dump_project(project).encode("utf-8"))
                    stream.flush()
                    os.fsync(stream.fileno())
                if load_project(temporary).project != project:
                    raise RuntimeError("Serialized draft failed round-trip verification")
                # Recheck routing/output boundaries and the external-editor revision
                # after staging, as close to replacement as portable APIs allow.
                if self.store.source(key) != path:
                    raise StudioError(409, "source_changed", "Source moved. Reload before saving.")
                resolve_output_directory(project, path.parent)
                self._check_revision(path, revision)
                os.replace(temporary, path)
                replaced = True
                try:
                    saved, saved_revision = self.store.snapshot(key)
                except (ProjectError, StudioError) as error:
                    raise StudioError(
                        503,
                        "save_unconfirmed",
                        "Source was replaced but reload failed. Reload to review before retrying.",
                    ) from error
                if saved != project:
                    raise StudioError(
                        409, "source_changed", "Source changed after saving. Reload to review."
                    )
                return project_detail(key, saved, saved_revision)
            except OSError as error:
                message = (
                    "Source was replaced but could not be confirmed. Reload before retrying."
                    if replaced
                    else "Save failed. The source was not replaced; your draft is still available."
                )
                raise StudioError(
                    503, "save_unconfirmed" if replaced else "save_failed", message
                ) from error
            finally:
                if temporary is not None and not replaced:
                    try:
                        temporary.unlink(missing_ok=True)
                    except OSError:
                        LOGGER.warning("Could not remove staged Studio file", exc_info=True)

    @staticmethod
    def _check_revision(path: Path, revision: str) -> None:
        current = "sha256-" + hashlib.sha256(path.read_bytes()).hexdigest()
        if current != revision:
            raise StudioError(
                409,
                "source_changed",
                "Source changed since this draft was opened. Your draft is intact. "
                "Reload and review the saved source.",
            )
