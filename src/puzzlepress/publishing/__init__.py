"""KDP paperback publishing: metadata validation, readiness and the package.

authored project ──> metadata validation (publishing.metadata)
interior + cover ──> fresh preflight verdicts (consumed, never reimplemented)
both ──────────────> PublishingReadinessReport ──> PublishingPackage ──> export

Nothing here contacts Amazon. A ready package means the supported checks
passed and the author confirmed what software cannot verify; KDP decides.
"""

from .identity import publishing_identity
from .metadata import MetadataReport, validate_metadata
from .rules import KDP_METADATA, KDP_RULES_CHECKED, RULES, RULESET_ID, RULESET_VERSION

__all__ = [
    "KDP_METADATA",
    "KDP_RULES_CHECKED",
    "RULES",
    "RULESET_ID",
    "RULESET_VERSION",
    "MetadataReport",
    "publishing_identity",
    "validate_metadata",
]
