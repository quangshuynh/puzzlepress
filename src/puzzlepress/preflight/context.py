"""What preflight observes: persisted artifacts beside the expected interior.

The expected interior is rebuilt from authoritative source by the same pure
pipeline as `book build`, so geometry is never re-derived here. Layout-based
rules apply to the PDF only when its bytes equal that deterministic rendering.
"""

import json
from dataclasses import dataclass
from pathlib import Path

from ..interior.build import MANIFEST_NAME, PDF_NAME, InteriorBuild
from ..interior.inspection import PdfFacts
from ..interior.issues import InteriorError, LayoutIssue
from ..interior.model import InteriorLayout
from ..interior.spec import PrintSpecification
from ..models import Project
from ..publication import PublicationPlan
from .model import PageContext

MANIFEST_VERSION = 1
# Required manifest fields and their JSON types.
MANIFEST_FIELDS: dict[str, type | tuple[type, ...]] = {
    "manifest_version": int,
    "book_id": str,
    "interior_identity": str,
    "identity": str,
    "plan_digest": str,
    "print_profile": dict,
    "renderer_version": int,
    "engine_version": str,
    "pdf_library": str,
    "fonts": list,
    "page_count": int,
    "pdf": dict,
    "trim": dict,
    "warnings": list,
}


@dataclass(frozen=True)
class InteriorArtifacts:
    """Bytes of the two build artifacts as found; None where unavailable."""

    pdf: bytes | None
    manifest: bytes | None
    problems: tuple[LayoutIssue, ...] = ()


def read_interior_artifacts(directory: Path) -> InteriorArtifacts:
    """Read only the fixed artifact names in an already boundary-checked directory.

    Symlinks and non-files are reported, never followed. Nothing is written.
    """
    problems: list[LayoutIssue] = []

    def read(name: str) -> bytes | None:
        path = directory / name
        try:
            if path.is_symlink():
                problems.append(
                    LayoutIssue("artifact_symlink", f"{name} is a symlink.", region=name)
                )
                return None
            if not path.exists():
                problems.append(LayoutIssue("artifact_missing", f"{name} is missing.", region=name))
                return None
            if not path.is_file():
                problems.append(
                    LayoutIssue("artifact_not_file", f"{name} is not a file.", region=name)
                )
                return None
            return path.read_bytes()
        except OSError as error:
            problems.append(
                LayoutIssue("artifact_unreadable", f"Cannot read {name}: {error}", region=name)
            )
            return None

    return InteriorArtifacts(read(PDF_NAME), read(MANIFEST_NAME), tuple(problems))


def parse_manifest(data: bytes) -> tuple[dict[str, object] | None, str | None]:
    """(manifest, problem): a well-formed manifest of a supported version, or why not."""
    try:
        value = json.loads(data.decode("utf-8"))
    except (UnicodeError, ValueError) as error:
        return None, f"interior.json is not valid JSON: {error}"
    if not isinstance(value, dict):
        return None, "interior.json is not a JSON object."
    if value.get("manifest_version") != MANIFEST_VERSION:
        return None, f"Unsupported manifest version {value.get('manifest_version')!r}."
    for key, kind in MANIFEST_FIELDS.items():
        if not isinstance(value.get(key), kind) or isinstance(value.get(key), bool):
            return None, f"interior.json field {key!r} is missing or malformed."
    pdf = value["pdf"]
    assert isinstance(pdf, dict)
    if not isinstance(pdf.get("sha256"), str) or not isinstance(pdf.get("bytes"), int):
        return None, "interior.json field 'pdf' lacks sha256 or bytes."
    return value, None


@dataclass(frozen=True)
class Context:
    project: Project
    source_identity: str
    artifacts: InteriorArtifacts
    manifest: dict[str, object] | None
    manifest_problem: str | None
    spec: PrintSpecification | None
    facts: PdfFacts | None
    facts_problem: LayoutIssue | None
    expected: InteriorBuild | None
    build_error: InteriorError | None

    @property
    def matches_layout(self) -> bool:
        """The PDF is byte-identical to a fresh render of the verified layout."""
        return (
            self.expected is not None
            and self.artifacts.pdf is not None
            and self.artifacts.pdf == self.expected.pdf
        )

    @property
    def layout(self) -> InteriorLayout | None:
        return self.expected.layout if self.expected and self.matches_layout else None

    @property
    def plan(self) -> PublicationPlan | None:
        return self.expected.plan if self.expected and self.matches_layout else None

    def page(self, number: int) -> PageContext:
        """Physical page with its plan meaning when the PDF matches the layout."""
        side = "recto" if number % 2 else "verso"
        plan = self.plan
        if plan is None or not 1 <= number <= len(plan.pages):
            return PageContext(number, side=side)
        entry = plan.pages[number - 1]
        return PageContext(
            number,
            logical_page=entry.index,
            kind=entry.kind.value,
            side=entry.side.value,
            folio=entry.number.label if entry.number.displayed else None,
        )
