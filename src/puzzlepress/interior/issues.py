"""Structured interior diagnostics shared by every build stage."""

from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class LayoutIssue:
    """Structured layout, integrity or output diagnostic with physical context."""

    code: str
    message: str
    page: int | None = None  # Logical plan index.
    physical_page: int | None = None  # 1-based PDF page.
    kind: str | None = None  # Plan entry kind.
    subject: str | None = None  # Puzzle ID where applicable.
    region: str | None = None
    actual: str | None = None
    required: str | None = None

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


class InteriorError(Exception):
    """Expected failure of an interior build stage; nothing was published."""

    def __init__(self, stage: str, issues: tuple[LayoutIssue, ...]) -> None:
        self.stage = stage
        self.issues = issues
        super().__init__("; ".join(f"{issue.code}: {issue.message}" for issue in issues))
