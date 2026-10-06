"""Versioned build-input encoding. No clocks, random state, or filesystem reads."""

import hashlib
import json

from . import __version__
from .composition import COMPOSITION_VERSION
from .content import PIPELINE_VERSION
from .models import Project

IDENTITY_VERSION = 1


def canonical_build_inputs(project: Project) -> bytes:
    """Return canonical UTF-8 JSON for normalized, semantically relevant inputs.

    Output location is operational and excluded. Content order is meaningful.
    Engine version is included so future behavior changes invalidate identities.
    """
    data = project.to_dict()
    del data["output"]
    envelope = {
        "identity_version": IDENTITY_VERSION,
        "engine_version": __version__,
        "project": data,
    }
    if project.word_search is not None:
        envelope["word_search_pipeline_version"] = PIPELINE_VERSION
    if project.composition is not None:
        envelope["composition_version"] = COMPOSITION_VERSION
    return json.dumps(
        envelope, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False
    ).encode("utf-8")


def build_identity(project: Project) -> str:
    """Return a tagged SHA-256 fingerprint, not a claim about future PDF bytes."""
    digest = hashlib.sha256(canonical_build_inputs(project)).hexdigest()
    return f"pp{IDENTITY_VERSION}-sha256-{digest}"
