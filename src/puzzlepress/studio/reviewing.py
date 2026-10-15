"""Studio adapter for editorial reviews and proof records.

Reviews judge the saved book: a judgment must carry the saved book.yaml
revision the author was looking at and the review identity Python reported for
that puzzle, so an unsaved or concurrent edit can never be marked reviewed.
Proof records must name the interior and cover currently in the build
directory. Both files have their own byte revisions; writing one never touches
book.yaml or any build artifact.
"""

from pathlib import Path

from puzzlepress.editorial import (
    ReviewError,
    ReviewStatus,
    evaluate_reviews,
    read_reviews,
    record_review,
    set_policy,
    write_reviews,
)
from puzzlepress.errors import ProjectError
from puzzlepress.interior import InteriorError
from puzzlepress.interior.build import check_output_directory
from puzzlepress.project import resolve_output_directory
from puzzlepress.proofing import (
    ProofError,
    ProofRecord,
    current_artifacts,
    evaluate_proofs,
    read_proofs,
    record_proof,
    remove_proof,
    validate_proofs,
    write_proofs,
)
from puzzlepress.sidecar import SidecarWriteError

from .service import StudioError, StudioService

STATUS = {
    "source_changed": 409,
    "content_changed": 409,
    "artifacts_changed": 409,
    "save_failed": 503,
    "save_unconfirmed": 503,
    "unknown_puzzle": 404,
    "interior_missing": 409,
}


class ReviewService:
    def __init__(self, service: StudioService) -> None:
        self.store = service.store

    def _folder(self, key: str) -> Path:
        return self.store.source(key).parent

    def _directory(self, key: str) -> Path:
        project = self.store.load(key)
        source = self._folder(key)
        try:
            return check_output_directory(resolve_output_directory(project, source), source)
        except InteriorError as error:
            raise StudioError(
                503, "output_unavailable", "The project's output directory is unavailable."
            ) from error

    # ------------------------------------------------------------ reviews

    def reviews(self, key: str) -> dict[str, object]:
        project, revision = self.store.snapshot(key)
        loaded = read_reviews(self._folder(key))
        return {
            "source_revision": revision,
            "revision": loaded.revision,
            "report": evaluate_reviews(project, loaded.document).to_dict(),
        }

    def record(
        self,
        key: str,
        source_revision: str,
        revision: str | None,
        puzzle: str,
        status: str,
        identity: str | None,
        note: str | None,
        reviewer: str | None,
        reviewed_on: str | None,
    ) -> dict[str, object]:
        project, current = self.store.snapshot(key)
        if current != source_revision:
            raise StudioError(
                409,
                "source_changed",
                "The saved book changed. Reload, then review the saved puzzle.",
            )
        if status not in {s.value for s in ReviewStatus}:
            raise StudioError(422, "invalid_request", "Unknown review status.")
        folder = self._folder(key)
        loaded = read_reviews(folder)
        if loaded.revision != revision:
            raise StudioError(409, "source_changed", "reviews.yaml changed. Reload it first.")
        try:
            document = record_review(
                project,
                loaded.document,
                puzzle,
                ReviewStatus(status),
                identity,
                note,
                reviewer,
                reviewed_on,
            )
            write_reviews(folder, document, revision)
        except (ReviewError, SidecarWriteError) as error:
            raise StudioError(STATUS.get(error.code, 422), error.code, str(error)) from error
        except ProjectError as error:
            raise StudioError(422, "invalid_review", str(error)) from error
        return self.reviews(key)

    def policy(self, key: str, revision: str | None, require_all: bool) -> dict[str, object]:
        folder = self._folder(key)
        loaded = read_reviews(folder)
        if loaded.revision != revision:
            raise StudioError(409, "source_changed", "reviews.yaml changed. Reload it first.")
        try:
            write_reviews(folder, set_policy(loaded.document, require_all), revision)
        except SidecarWriteError as error:
            raise StudioError(STATUS.get(error.code, 422), error.code, str(error)) from error
        return self.reviews(key)

    # ------------------------------------------------------------ proofs

    def proofs(self, key: str) -> dict[str, object]:
        loaded = read_proofs(self._folder(key))
        current = current_artifacts(self._directory(key))
        return {"revision": loaded.revision, **evaluate_proofs(loaded.document, current)}

    def record_proof(self, key: str, revision: str | None, record: object) -> dict[str, object]:
        folder = self._folder(key)
        loaded = read_proofs(folder)
        if loaded.revision != revision:
            raise StudioError(409, "source_changed", "proofs.yaml changed. Reload it first.")
        parsed, issues = validate_proofs({"proof_version": 1, "proofs": [record]})
        if parsed is None:
            raise StudioError(422, "invalid_proof", "; ".join(i.message for i in issues))
        (proof,) = parsed.proofs
        assert isinstance(proof, ProofRecord)
        try:
            document = record_proof(loaded.document, proof, current_artifacts(self._directory(key)))
            write_proofs(folder, document, revision)
        except (ProofError, SidecarWriteError) as error:
            raise StudioError(STATUS.get(error.code, 422), error.code, str(error)) from error
        return self.proofs(key)

    def remove_proof(self, key: str, revision: str | None, proof_id: str) -> dict[str, object]:
        folder = self._folder(key)
        loaded = read_proofs(folder)
        if loaded.revision != revision:
            raise StudioError(409, "source_changed", "proofs.yaml changed. Reload it first.")
        try:
            write_proofs(folder, remove_proof(loaded.document, proof_id), revision)
        except SidecarWriteError as error:
            raise StudioError(STATUS.get(error.code, 422), error.code, str(error)) from error
        return self.proofs(key)
