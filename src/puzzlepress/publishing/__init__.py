"""KDP paperback publishing: metadata validation, readiness and the package.

authored project ──> metadata validation (publishing.metadata)
interior + cover ──> fresh preflight verdicts (consumed, never reimplemented)
both ──────────────> PublishingReadinessReport ──> PublishingPackage ──> export

Nothing here contacts Amazon. A ready package means the supported checks
passed and the author confirmed what software cannot verify; KDP decides.
"""

from .identity import publishing_identity
from .metadata import MetadataReport, validate_metadata
from .package import (
    ExportState,
    PackageError,
    PublishingPackage,
    assemble_package,
    export_state,
    write_package,
)
from .readiness import PublishingReadinessReport, evaluate_readiness, readiness_bytes
from .rules import KDP_METADATA, KDP_RULES_CHECKED, RULES, RULESET_ID, RULESET_VERSION

__all__ = [
    "KDP_METADATA",
    "KDP_RULES_CHECKED",
    "RULES",
    "RULESET_ID",
    "RULESET_VERSION",
    "ExportState",
    "MetadataReport",
    "PackageError",
    "PublishingPackage",
    "PublishingReadinessReport",
    "assemble_package",
    "evaluate_readiness",
    "export_state",
    "publishing_identity",
    "readiness_bytes",
    "validate_metadata",
    "write_package",
]
