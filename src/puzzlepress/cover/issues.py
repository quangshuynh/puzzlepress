"""Expected cover failures, reusing the interior's structured issue shape."""

from ..interior.issues import LayoutIssue


class CoverError(Exception):
    """Expected failure of a cover stage; nothing was written.

    Stages: `config`, `interior`, `asset`, `geometry`, `layout`, `layout_validation`,
    `pdf_verification`, `output`.
    """

    def __init__(self, stage: str, issues: tuple[LayoutIssue, ...]) -> None:
        self.stage = stage
        self.issues = issues
        super().__init__("; ".join(f"{issue.code}: {issue.message}" for issue in issues))


def cover_error(
    stage: str,
    code: str,
    message: str,
    region: str | None = None,
    actual: str | None = None,
    required: str | None = None,
) -> CoverError:
    return CoverError(
        stage, (LayoutIssue(code, message, region=region, actual=actual, required=required),)
    )
