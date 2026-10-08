"""KDP paperback publishing: metadata validation, readiness and the package.

authored project ──> metadata validation (publishing.metadata)
interior + cover ──> fresh preflight verdicts (consumed, never reimplemented)
both ──────────────> PublishingReadinessReport ──> PublishingPackage ──> export

Nothing here contacts Amazon. A ready package means the supported checks
passed and the author confirmed what software cannot verify; KDP decides.
"""

from .identity import publishing_identity

__all__ = ["publishing_identity"]
