"""A small, auditable provenance record for a publishing package.

Machine facts are what PuzzlePress computed or recomputed and anyone can check
again (identities, digests, versions, counts). Author declarations are what the
author stated in book.yaml; they are recorded, never verified. A digest
identifies bytes; it proves nothing about authorship, rights or ownership. No
paths, timestamps, camera metadata or location data are recorded.
"""

import json

from .. import __version__
from ..content import PIPELINE_VERSION
from .metadata import ATTESTATION_TEXT, kdp_ai_answers
from .readiness import PublishingReadinessReport
from .review import COVERS

# 2: each confirmation records the review identity it was given for.
PROVENANCE_VERSION = 2
LIMITS = (
    "SHA-256 digests identify exact bytes. They do not prove authorship, copyright or "
    "ownership of the text, word lists or photograph.",
    "Author declarations and confirmations are the author's statements. PuzzlePress records "
    "them as written and cannot verify them.",
    "A valid ISBN check digit does not show that the ISBN is registered to this book.",
    "Readiness covers the checks PuzzlePress models. Amazon KDP reviews the book and decides.",
)


def _manifest(data: bytes | None) -> dict[str, object]:
    if data is None:
        return {}
    value = json.loads(data.decode("utf-8"))
    return value if isinstance(value, dict) else {}


def provenance_record(report: PublishingReadinessReport) -> dict[str, object]:
    project = report.project
    config = project.publishing
    interior_pair = report.interior_bytes()
    cover_pair = report.cover_bytes()
    interior = _manifest(interior_pair[1] if interior_pair else None)
    cover = _manifest(cover_pair[1] if cover_pair else None)
    identities = report.identities()
    puzzles = project.word_search.puzzles if project.word_search else ()
    photo = cover.get("photo")
    photo_facts = (
        {
            "sha256": photo.get("sha256"),
            "format": photo.get("format"),
            "pixels": photo.get("pixels"),
            "in_cover_pdf": "re-encoded from bare pixels; EXIF, GPS, XMP, ICC and comments "
            "are not carried into cover.pdf",
        }
        if isinstance(photo, dict)
        else None
    )
    interior_pdf = interior.get("pdf")
    cover_pdf = cover.get("pdf")
    cover_toolchain = cover.get("toolchain")
    declarations: dict[str, object] | None = None
    if config is not None:
        declarations = {
            "ai_disclosure": kdp_ai_answers(config.ai_disclosure),
            "confirmations": [
                {
                    "name": c.name,
                    "statement": ATTESTATION_TEXT[c.name],
                    "covers": COVERS[c.name],
                    "confirmed": c.state == "confirmed",
                    "state": c.state,
                    "review_identity": c.confirmed if c.state == "confirmed" else None,
                }
                for c in report.metadata.confirmations
                if c.required
            ],
            "low_content": config.low_content,
            "isbn_mode": config.isbn.mode.value,
        }
    return {
        "provenance_version": PROVENANCE_VERSION,
        "book_id": project.book.id,
        "machine_facts": {
            "engine_version": __version__,
            "source_identity": identities["source"],
            "publishing_identity": identities["publishing"],
            "puzzles": {
                "count": len(puzzles),
                "generator": "PuzzlePress word-search generator: seeded, deterministic "
                "procedural placement, independently verified; no machine-learning model",
                "pipeline_version": PIPELINE_VERSION,
                "seeds": "derived per puzzle from build.seed and the puzzle ID",
            },
            "interior": None
            if not interior
            else {
                "interior_identity": interior.get("interior_identity"),
                "pdf_sha256": interior_pdf.get("sha256")
                if isinstance(interior_pdf, dict)
                else None,
                "page_count": interior.get("page_count"),
                "renderer_version": interior.get("renderer_version"),
                "raster_images": 0,
            },
            "cover": None
            if not cover
            else {
                "cover_identity": cover.get("cover_identity"),
                "pdf_sha256": cover_pdf.get("sha256") if isinstance(cover_pdf, dict) else None,
                "renderer_version": cover_toolchain.get("renderer_version")
                if isinstance(cover_toolchain, dict)
                else None,
                "photograph": photo_facts,
            },
        },
        "author_declarations": declarations,
        "limits": list(LIMITS),
    }
