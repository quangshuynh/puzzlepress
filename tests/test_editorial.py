"""Editorial reviews and proof records: identities, staleness, storage and isolation."""

import pytest

from puzzlepress.editorial import (
    REVIEW_FILE,
    ReviewDocument,
    ReviewError,
    ReviewStatus,
    evaluate_reviews,
    read_reviews,
    record_review,
    review_identity,
    set_policy,
    validate_reviews,
    write_reviews,
)
from puzzlepress.errors import ProjectError
from puzzlepress.identity import build_identity
from puzzlepress.interior import build_interior
from puzzlepress.interior.spec import PAPERBACK_LETTER
from puzzlepress.proofing import (
    ArtifactIdentities,
    ProofDecision,
    ProofDocument,
    ProofError,
    ProofKind,
    ProofRecord,
    ProofStatus,
    current_artifacts,
    evaluate_proofs,
    read_proofs,
    record_proof,
    validate_proofs,
    write_proofs,
)
from puzzlepress.sidecar import SidecarWriteError
from tests.helpers import demo_variant

PUZZLE = "shoreline"


def edited(**changes):
    def mutate(data):
        puzzle = data["word_search"]["puzzles"][0]
        puzzle.update(changes)

    return demo_variant(mutate)


def test_identity_covers_content_not_formatting_or_other_puzzles():
    base = demo_variant()
    identity = review_identity(base, PUZZLE)
    assert identity.startswith("pp1-puzzle-review-sha256-")

    def other(data):
        data["word_search"]["puzzles"][1]["title"] = "A different puzzle"
        data["word_search"]["puzzles"].reverse()
        data["build"]["seed"] = 99

    assert review_identity(demo_variant(other), PUZZLE) == identity
    assert review_identity(edited(title="New title"), PUZZLE) != identity
    assert review_identity(edited(theme="New theme"), PUZZLE) != identity
    assert review_identity(edited(target_ids=["shell", "wave"]), PUZZLE) != identity
    assert review_identity(edited(difficulty="varied"), PUZZLE) != identity
    assert review_identity(base, "missing") is None


def test_reviews_go_stale_on_edit_and_return_on_revert():
    base = demo_variant()
    document = record_review(
        base, ReviewDocument(), PUZZLE, ReviewStatus.REVIEWED, review_identity(base, PUZZLE)
    )
    assert evaluate_reviews(base, document).puzzles[0].state == "reviewed"
    changed = edited(title="Edited")
    assert evaluate_reviews(changed, document).puzzles[0].state == "stale"
    assert (
        evaluate_reviews(edited(title="Along the Shoreline"), document).puzzles[0].state
        == "reviewed"
    )


def test_judgments_must_name_the_current_content():
    base = demo_variant()
    with pytest.raises(ReviewError) as error:
        record_review(
            base,
            ReviewDocument(),
            PUZZLE,
            ReviewStatus.REVIEWED,
            "pp1-puzzle-review-sha256-" + "0" * 64,
        )
    assert error.value.code == "content_changed"
    with pytest.raises(ReviewError):
        record_review(base, ReviewDocument(), "nope", ReviewStatus.REVIEWED, None)


def test_notes_progress_policy_and_reset():
    base = demo_variant()
    identity = review_identity(base, PUZZLE)
    document = record_review(
        base,
        ReviewDocument(),
        PUZZLE,
        ReviewStatus.NEEDS_CHANGES,
        identity,
        note="Replace KELP with a more common word.",
        reviewer="E. Huynh",
        reviewed_on="2026-10-15",
    )
    report = evaluate_reviews(base, document)
    assert report.summary() == {
        "total": 4,
        "reviewed": 0,
        "needs_changes": 1,
        "not_reviewed": 3,
        "stale": 0,
        "complete": False,
        "require_all": False,
    }
    reset = record_review(
        base,
        document,
        PUZZLE,
        ReviewStatus.NOT_REVIEWED,
        None,
        note="Replace KELP with a more common word.",
    )
    (kept,) = reset.puzzles
    assert kept.status is ReviewStatus.NOT_REVIEWED and kept.content is None and kept.note
    assert record_review(base, reset, PUZZLE, ReviewStatus.NOT_REVIEWED, None).puzzles == ()
    everything = ReviewDocument()
    for definition in base.word_search.puzzles:
        everything = record_review(
            base,
            everything,
            definition.id,
            ReviewStatus.REVIEWED,
            review_identity(base, definition.id),
        )
    assert evaluate_reviews(base, set_policy(everything, True)).summary()["complete"] is True


def test_no_review_is_ever_inferred_from_quality():
    report = evaluate_reviews(demo_variant(), ReviewDocument())
    assert {p.state for p in report.puzzles} == {"not_reviewed"}
    assert all(p.recorded is None for p in report.puzzles)


@pytest.mark.parametrize(
    ("value", "code"),
    [
        ({"review_version": 2}, "unsupported_version"),
        ({"review_version": 1, "puzzles": [{"puzzle": "a", "status": "approved"}]}, "choice"),
        ({"review_version": 1, "puzzles": [{"puzzle": "a", "status": "reviewed"}]}, "identity"),
        (
            {
                "review_version": 1,
                "puzzles": [{"puzzle": "a", "status": "not_reviewed", "reviewed_on": "15/10/2026"}],
            },
            "date",
        ),
        (
            {
                "review_version": 1,
                "puzzles": [
                    {"puzzle": "a", "status": "not_reviewed"},
                    {"puzzle": "a", "status": "not_reviewed"},
                ],
            },
            "duplicate",
        ),
    ],
)
def test_review_schema_refusals(value, code):
    document, issues = validate_reviews(value)
    assert document is None and code in {i.code for i in issues}


def test_reviews_file_is_revision_checked_and_outside_production(tmp_path):
    base = demo_variant()
    identity_before = build_identity(base)
    pdf_before = build_interior(base, PAPERBACK_LETTER).pdf
    loaded = read_reviews(tmp_path)
    assert loaded.revision is None and loaded.document == ReviewDocument()
    document = record_review(
        base, loaded.document, PUZZLE, ReviewStatus.REVIEWED, review_identity(base, PUZZLE)
    )
    revision = write_reviews(tmp_path, document, None)
    assert read_reviews(tmp_path).document == document
    with pytest.raises(SidecarWriteError) as error:
        write_reviews(tmp_path, document, None)  # Someone else created it meanwhile.
    assert error.value.code == "source_changed"
    (tmp_path / REVIEW_FILE).write_text(
        (tmp_path / REVIEW_FILE).read_text() + "\n", encoding="utf-8"
    )
    with pytest.raises(SidecarWriteError):
        write_reviews(tmp_path, document, revision)
    assert build_identity(base) == identity_before
    assert build_interior(base, PAPERBACK_LETTER).pdf == pdf_before


# ------------------------------------------------------------------ proofs


def _artifacts(n="1"):
    return ArtifactIdentities(
        "pp1-interior-sha256-" + n * 64, n * 64, "pp1-cover-sha256-" + n * 64, n * 64
    )


def _proof(**fields):
    values = {
        "id": "proof-1",
        "kind": ProofKind.PHYSICAL_PROOF,
        "status": ProofStatus.RECEIVED,
        "decision": ProofDecision.UNDECIDED,
        "artifacts": _artifacts(),
    }
    values.update(fields)
    return ProofRecord(**values)


def test_proofs_bind_to_the_artifacts_reviewed_and_go_stale():
    current = _artifacts()
    document = record_proof(ProofDocument(), _proof(), current)
    state = evaluate_proofs(document, current)
    assert state["physical_proof"]["current"] is True and state["print_previewer"] is None
    rebuilt = _artifacts("2")
    assert evaluate_proofs(document, rebuilt)["physical_proof"]["current"] is False
    with pytest.raises(ProofError) as error:
        record_proof(document, _proof(id="proof-2"), rebuilt)  # Named the old files.
    assert error.value.code == "artifacts_changed"
    with pytest.raises(ProofError):
        record_proof(ProofDocument(), _proof(), None)


def test_proof_decisions_need_a_review_and_are_never_automatic():
    current = _artifacts()
    with pytest.raises(ProjectError) as error:
        record_proof(ProofDocument(), _proof(decision=ProofDecision.APPROVED), current)
    assert "decision" in {i.code for i in error.value.issues}
    reviewed = _proof(status=ProofStatus.REVIEWED, issues=("Gutter text close to the fold.",))
    document = record_proof(ProofDocument(), reviewed, current)
    assert document.proofs[0].decision is ProofDecision.UNDECIDED
    approved = record_proof(
        document, _proof(status=ProofStatus.REVIEWED, decision=ProofDecision.APPROVED), current
    )
    assert approved.proofs[0].decision is ProofDecision.APPROVED
    _, issues = validate_proofs(
        {
            "proof_version": 1,
            "proofs": [{**_proof(kind=ProofKind.PRINT_PREVIEWER).to_dict(), "status": "ordered"}],
        }
    )
    assert "status" in {i.code for i in issues}


def test_proof_file_round_trips(tmp_path):
    document = record_proof(ProofDocument(), _proof(received_on="2026-10-20"), _artifacts())
    write_proofs(tmp_path, document, None)
    assert read_proofs(tmp_path).document == document


def test_current_artifacts_reads_verified_manifests(tmp_path):
    from puzzlepress.interior import write_interior

    source = tmp_path / "book"
    source.mkdir()
    built = build_interior(demo_variant(), PAPERBACK_LETTER)
    write_interior(built, tmp_path / "out", source)
    found = current_artifacts(tmp_path / "out")
    assert found is not None and found.interior == built.manifest["interior_identity"]
    assert found.cover is None
    (tmp_path / "out" / "interior.pdf").write_bytes(b"%PDF-tampered")
    assert current_artifacts(tmp_path / "out") is None
