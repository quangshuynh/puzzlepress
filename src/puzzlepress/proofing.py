"""Human proofing records: Print Previewer checks and physical proofs, as people report them.

PuzzlePress cannot see Amazon's Print Previewer or a printed copy. A proof
record is what the author writes down after doing that work: which artifacts
they reviewed (the interior and cover identities and PDF digests Python reports
for the files in the build directory at the time), the proof's status, dates
they type, the issues they observed and their decision. Records live in
proofs.yaml beside book.yaml, outside every production identity, so recording
one never changes a PDF. A record goes stale when the interior or cover in the
build directory is no longer the one it names. Nothing is approved, dated or
submitted by PuzzlePress, and nothing contacts Amazon.
"""

import hashlib
import json
import re
from dataclasses import dataclass, replace
from enum import StrEnum
from pathlib import Path

import yaml

from .content_validation import _Reader
from .errors import ProjectError, ValidationIssue
from .sidecar import read_sidecar, write_sidecar

PROOF_FILE = "proofs.yaml"
PROOF_VERSION = 1
MAX_PROOFS = 50
MAX_ISSUES = 50
MAX_TEXT = 1000
DATE = re.compile(r"\d{4}-\d{2}-\d{2}")
INTERIOR = re.compile(r"pp1-interior-sha256-[0-9a-f]{64}")
COVER = re.compile(r"pp1-cover-sha256-[0-9a-f]{64}")
DIGEST = re.compile(r"[0-9a-f]{64}")
PROOF_ID = re.compile(r"[a-z0-9]+(?:-[a-z0-9]+)*")


class ProofKind(StrEnum):
    PRINT_PREVIEWER = "print_previewer"  # KDP's online previewer, after a manual upload.
    PHYSICAL_PROOF = "physical_proof"  # A printed proof copy the author ordered.


class ProofStatus(StrEnum):
    ORDERED = "ordered"  # Physical proofs only.
    RECEIVED = "received"  # Physical proofs only.
    REVIEWED = "reviewed"


class ProofDecision(StrEnum):
    UNDECIDED = "undecided"
    CHANGES_NEEDED = "changes_needed"
    APPROVED = "approved"


@dataclass(frozen=True)
class ArtifactIdentities:
    """What a proof covers: the built interior and cover, by identity and PDF digest."""

    interior: str
    interior_pdf: str
    cover: str | None = None
    cover_pdf: str | None = None

    def to_dict(self) -> dict[str, object]:
        return {
            "interior": self.interior,
            "interior_pdf": self.interior_pdf,
            "cover": self.cover,
            "cover_pdf": self.cover_pdf,
        }


@dataclass(frozen=True)
class ProofRecord:
    id: str
    kind: ProofKind
    status: ProofStatus
    decision: ProofDecision
    artifacts: ArtifactIdentities
    received_on: str | None = None  # YYYY-MM-DD typed by the author.
    reviewed_on: str | None = None
    issues: tuple[str, ...] = ()  # What the person observed, in their words.
    note: str | None = None

    def to_dict(self) -> dict[str, object]:
        data: dict[str, object] = {
            "id": self.id,
            "kind": self.kind.value,
            "status": self.status.value,
            "decision": self.decision.value,
            "artifacts": self.artifacts.to_dict(),
        }
        for key in ("received_on", "reviewed_on", "note"):
            value = getattr(self, key)
            if value is not None:
                data[key] = value
        if self.issues:
            data["issues"] = list(self.issues)
        return data


@dataclass(frozen=True)
class ProofDocument:
    version: int = PROOF_VERSION
    proofs: tuple[ProofRecord, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {"proof_version": self.version, "proofs": [p.to_dict() for p in self.proofs]}


# ------------------------------------------------------------------ schema


def _text(reader: _Reader, value: object, path: str, multiline: bool = False) -> str | None:
    if value is None:
        return None
    if (
        not isinstance(value, str)
        or not value.strip()
        or len(value) > MAX_TEXT
        or any((ord(c) < 32 and not (multiline and c == "\n")) or ord(c) == 127 for c in value)
    ):
        reader.issue(path, "text", f"Expected 1..{MAX_TEXT} characters of plain text.")
        return None
    return value.strip()


def _date(reader: _Reader, value: object, path: str) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str) or not DATE.fullmatch(value):
        reader.issue(path, "date", "Use a date as YYYY-MM-DD.")
        return None
    return value


def _artifacts(reader: _Reader, value: object, path: str) -> ArtifactIdentities | None:
    data = reader.mapping(value, path, {"interior", "interior_pdf", "cover", "cover_pdf"})
    interior, interior_pdf = data.get("interior"), data.get("interior_pdf")
    cover, cover_pdf = data.get("cover"), data.get("cover_pdf")
    valid = True
    if not isinstance(interior, str) or not INTERIOR.fullmatch(interior):
        reader.issue(f"{path}.interior", "identity", "Expected an interior identity.")
        valid = False
    if not isinstance(interior_pdf, str) or not DIGEST.fullmatch(interior_pdf):
        reader.issue(f"{path}.interior_pdf", "digest", "Expected the interior PDF SHA-256.")
        valid = False
    if cover is not None and (not isinstance(cover, str) or not COVER.fullmatch(cover)):
        reader.issue(f"{path}.cover", "identity", "Expected a cover identity or null.")
        valid = False
    if (cover is None) != (cover_pdf is None) or (
        cover_pdf is not None
        and (not isinstance(cover_pdf, str) or not DIGEST.fullmatch(cover_pdf))
    ):
        reader.issue(
            f"{path}.cover_pdf", "digest", "Expected the cover PDF SHA-256 with its cover."
        )
        valid = False
    if not valid:
        return None
    assert isinstance(interior, str) and isinstance(interior_pdf, str)
    return ArtifactIdentities(
        interior,
        interior_pdf,
        cover if isinstance(cover, str) else None,
        cover_pdf if isinstance(cover_pdf, str) else None,
    )


def validate_proofs(value: object) -> tuple[ProofDocument | None, tuple[ValidationIssue, ...]]:
    reader = _Reader()
    data = reader.mapping(value, "proofs", {"proof_version", "proofs"})
    if not isinstance(value, dict):
        return None, tuple(reader.issues)
    if data.get("proof_version") != PROOF_VERSION:
        reader.issue(
            "proofs.proof_version",
            "unsupported_version",
            f"Proof version {data.get('proof_version')!r} is not supported. Supported: 1.",
        )
        return None, tuple(reader.issues)
    records: list[ProofRecord] = []
    seen: set[str] = set()
    for index, entry in enumerate(
        reader.sequence(data.get("proofs", []), "proofs.proofs", MAX_PROOFS, 0)
    ):
        path = f"proofs.proofs.{index}"
        item = reader.mapping(
            entry,
            path,
            {
                "id",
                "kind",
                "status",
                "decision",
                "artifacts",
                "received_on",
                "reviewed_on",
                "issues",
                "note",
            },
        )
        proof_id = item.get("id")
        if not isinstance(proof_id, str) or len(proof_id) > 40 or not PROOF_ID.fullmatch(proof_id):
            reader.issue(f"{path}.id", "id", "Use 1..40 lowercase letters, digits and hyphens.")
            continue
        if proof_id in seen:
            reader.issue(f"{path}.id", "duplicate", f"Proof {proof_id!r} is recorded twice.")
        seen.add(proof_id)
        values: dict[str, str | None] = {}
        for key, enum in (
            ("kind", ProofKind),
            ("status", ProofStatus),
            ("decision", ProofDecision),
        ):
            raw = item.get(key)
            if not isinstance(raw, str) or raw not in {m.value for m in enum}:
                reader.issue(
                    f"{path}.{key}", "choice", f"Use one of: {', '.join(m.value for m in enum)}."
                )
                raw = None
            values[key] = raw
        artifacts = _artifacts(reader, item.get("artifacts"), f"{path}.artifacts")
        issues = [
            _text(reader, text, f"{path}.issues.{n}")
            for n, text in enumerate(
                reader.sequence(item.get("issues", []), f"{path}.issues", MAX_ISSUES, 0)
            )
        ]
        kind_value, status_value = values["kind"], values["status"]
        decision_value = values["decision"]
        if kind_value is None or status_value is None or decision_value is None or not artifacts:
            continue
        kind, status = ProofKind(kind_value), ProofStatus(status_value)
        decision = ProofDecision(decision_value)
        if kind is ProofKind.PRINT_PREVIEWER and status is not ProofStatus.REVIEWED:
            reader.issue(
                f"{path}.status", "status", "A Print Previewer check is recorded once reviewed."
            )
        if decision is not ProofDecision.UNDECIDED and status is not ProofStatus.REVIEWED:
            reader.issue(
                f"{path}.decision", "decision", "Decide only after the proof has been reviewed."
            )
        records.append(
            ProofRecord(
                proof_id,
                kind,
                status,
                decision,
                artifacts,
                _date(reader, item.get("received_on"), f"{path}.received_on"),
                _date(reader, item.get("reviewed_on"), f"{path}.reviewed_on"),
                tuple(text for text in issues if text),
                _text(reader, item.get("note"), f"{path}.note", multiline=True),
            )
        )
    if reader.issues:
        return None, tuple(reader.issues)
    return ProofDocument(PROOF_VERSION, tuple(records)), ()


def _require(value: object) -> ProofDocument:
    document, issues = validate_proofs(value)
    if document is None:
        raise ProjectError(issues)
    return document


@dataclass(frozen=True)
class LoadedProofs:
    document: ProofDocument
    revision: str | None


def read_proofs(source_directory: Path) -> LoadedProofs:
    loaded = read_sidecar(source_directory, PROOF_FILE)
    if loaded.data is None:
        return LoadedProofs(ProofDocument(), loaded.revision)
    return LoadedProofs(_require(loaded.data), loaded.revision)


def write_proofs(source_directory: Path, document: ProofDocument, revision: str | None) -> str:
    text = yaml.safe_dump(document.to_dict(), allow_unicode=True, sort_keys=False, width=88)
    return write_sidecar(source_directory, PROOF_FILE, text, revision, _require)


# ------------------------------------------------------------------ current artifacts


def current_artifacts(directory: Path) -> ArtifactIdentities | None:
    """Identities and PDF digests of the interior and cover in a build directory.

    Read from the manifests and verified against the PDFs' bytes; None when no
    intact interior exists. A cover is included only when intact.
    """

    def pair(pdf_name: str, manifest_name: str, key: str) -> tuple[str, str] | None:
        pdf, manifest = directory / pdf_name, directory / manifest_name
        try:
            if any(p.is_symlink() or not p.is_file() for p in (pdf, manifest)):
                return None
            data = json.loads(manifest.read_text(encoding="utf-8"))
            digest = hashlib.sha256(pdf.read_bytes()).hexdigest()
        except (OSError, UnicodeError, ValueError):
            return None
        if not isinstance(data, dict) or data.get("pdf", {}).get("sha256") != digest:
            return None
        identity = data.get(key)
        return (identity, digest) if isinstance(identity, str) else None

    interior = pair("interior.pdf", "interior.json", "interior_identity")
    if interior is None:
        return None
    cover = pair("cover.pdf", "cover.json", "cover_identity")
    return ArtifactIdentities(
        interior[0], interior[1], cover[0] if cover else None, cover[1] if cover else None
    )


class ProofError(Exception):
    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


def record_proof(
    document: ProofDocument, record: ProofRecord, current: ArtifactIdentities | None
) -> ProofDocument:
    """Add or replace a record. A new or re-decided record must name the current artifacts.

    Editing an older record's notes keeps the artifacts it named; changing its
    decision requires that it still describes the built files.
    """
    if current is None:
        raise ProofError("interior_missing", "Build the interior before recording a proof.")
    previous = next((p for p in document.proofs if p.id == record.id), None)
    decided = previous is None or previous.decision is not record.decision
    if (decided or previous is None) and record.artifacts != current:
        raise ProofError(
            "artifacts_changed",
            "The interior or cover changed since you opened this proof. Reload and record "
            "the proof against the files you reviewed.",
        )
    if previous is not None and not decided and record.artifacts != previous.artifacts:
        raise ProofError("artifacts_changed", "A proof keeps the artifacts it was recorded for.")
    proofs = [p for p in document.proofs if p.id != record.id] + [record]
    candidate = replace(document, proofs=tuple(proofs))
    return _require(candidate.to_dict())


def remove_proof(document: ProofDocument, proof_id: str) -> ProofDocument:
    return replace(document, proofs=tuple(p for p in document.proofs if p.id != proof_id))


@dataclass(frozen=True)
class ProofState:
    record: ProofRecord
    current: bool  # It names the interior and cover in the build directory now.

    def to_dict(self) -> dict[str, object]:
        return {"record": self.record.to_dict(), "current": self.current}


def evaluate_proofs(
    document: ProofDocument, current: ArtifactIdentities | None
) -> dict[str, object]:
    """Each record's currency and the latest of each kind (by position in the file)."""
    states = [
        ProofState(p, current is not None and p.artifacts == current) for p in document.proofs
    ]

    def latest(kind: ProofKind) -> dict[str, object] | None:
        found = [s for s in states if s.record.kind is kind]
        return found[-1].to_dict() if found else None

    return {
        "artifacts": None if current is None else current.to_dict(),
        "proofs": [s.to_dict() for s in states],
        "print_previewer": latest(ProofKind.PRINT_PREVIEWER),
        "physical_proof": latest(ProofKind.PHYSICAL_PROOF),
    }
