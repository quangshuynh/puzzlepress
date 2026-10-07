"""Read-only print preflight: structural validity and modeled KDP readiness.

Importing this package loads the interior engine (ReportLab, pypdf) but performs
no file I/O. Preflight observes artifacts and never mutates or repairs them.
"""

from .context import InteriorArtifacts, read_interior_artifacts
from .engine import PreflightResult, preflight_interior
from .model import (
    REPORT_VERSION,
    RULESET_ID,
    RULESET_VERSION,
    Finding,
    Outcome,
    PreflightReport,
    Scope,
    Severity,
    report_bytes,
)
from .rules import RULES

__all__ = [
    "REPORT_VERSION",
    "RULES",
    "RULESET_ID",
    "RULESET_VERSION",
    "Finding",
    "InteriorArtifacts",
    "Outcome",
    "PreflightReport",
    "PreflightResult",
    "Scope",
    "Severity",
    "preflight_interior",
    "read_interior_artifacts",
    "report_bytes",
]
