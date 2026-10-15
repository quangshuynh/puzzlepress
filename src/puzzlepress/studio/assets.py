"""Studio adapter for the asset library: listing, reference-checked removal, restore.

Every decision is `puzzlepress.asset_library`'s. This module locates the saved
project folder, validates the unsaved draft the browser sends (so references in
it are protected), and serializes removal with source saves: the save lock is
held while the saved revision is rechecked, references are analyzed and the
file is moved, so no Studio save can add a reference in between. Callers name
assets by their project reference only; no path from the browser is joined
onto the filesystem.
"""

from puzzlepress.asset_library import (
    AssetError,
    library,
    list_trash,
    purge_asset,
    restore_asset,
    trash_asset,
    unmanaged,
)
from puzzlepress.models import Project

from .editing import _SAVE_LOCK, DraftStore
from .service import StudioError, StudioService

STATUS = {
    "asset_in_use": 409,
    "asset_changed": 409,
    "asset_collision": 409,
    "asset_missing": 404,
    "not_in_trash": 404,
    "asset_unsafe": 422,
}


def _error(error: AssetError) -> StudioError:
    studio = StudioError(STATUS.get(error.code, 422), error.code, str(error))
    studio.uses = [use.to_dict() for use in error.uses]  # type: ignore[attr-defined]
    return studio


class AssetService:
    def __init__(self, service: StudioService, drafts: DraftStore) -> None:
        self.store = service.store
        self.drafts = drafts

    def _draft(self, key: str, source: object | None) -> Project | None:
        return None if source is None else self.drafts.validate(key, source)

    def listing(self, key: str, source: object | None = None) -> dict[str, object]:
        saved, revision = self.store.snapshot(key)
        folder = self.store.source(key).parent
        draft = self._draft(key, source)
        try:
            entries = library(folder, saved, draft)
        except AssetError as error:
            raise _error(error) from error
        return {
            "revision": revision,
            "assets": [entry.to_dict() for entry in entries],
            "unmanaged": list(unmanaged(folder)),
            "trash": [entry.to_dict() for entry in list_trash(folder)],
        }

    def trash(
        self, key: str, path: str, sha256: str, revision: str, source: object | None
    ) -> dict[str, object]:
        draft = self._draft(key, source)
        folder = self.store.source(key).parent
        with _SAVE_LOCK:
            saved, current = self.store.snapshot(key)
            if current != revision:
                raise StudioError(
                    409, "source_changed", "The saved book changed. Reload before removing assets."
                )
            try:
                moved = trash_asset(folder, path, sha256, saved, draft)
            except AssetError as error:
                raise _error(error) from error
        return {"trashed": moved.to_dict(), **self.listing(key, source)}

    def restore(self, key: str, trashed: str) -> dict[str, object]:
        folder = self.store.source(key).parent
        with _SAVE_LOCK:
            try:
                reference = restore_asset(folder, trashed)
            except AssetError as error:
                raise _error(error) from error
        return {"restored": reference, **self.listing(key)}

    def purge(self, key: str, trashed: str, sha256: str) -> dict[str, object]:
        folder = self.store.source(key).parent
        with _SAVE_LOCK:
            try:
                purge_asset(folder, trashed, sha256)
            except AssetError as error:
                raise _error(error) from error
        return {"purged": trashed, **self.listing(key)}
