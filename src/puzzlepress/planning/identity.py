"""Planning identity: what an approval covers, separate from every production identity.

`pp1-planning-sha256-` is SHA-256 over canonical JSON of the normalized planning
document without its approval, the book ID it plans, the planning document
version and the planning identity version. YAML comments, key order, formatting,
omitted versus explicit defaults and the order of direction names do not change
it; authored list order does (it is the planned book order). No paths, times,
engine or toolchain versions: approval binds to the authored plan, and findings
are always recomputed against the running engine.

Planning never enters build, interior, cover, publishing or package identities,
so editing a plan never stales a built book.
"""

import hashlib
import json

from ..identity import IDENTITY_VERSION
from .model import PlanningDocument

# Bump when what the identity covers changes: every recorded approval goes stale.
PLANNING_IDENTITY_VERSION = 1


def canonical(data: object) -> bytes:
    return json.dumps(
        data, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False
    ).encode("ascii")


def planning_inputs(book_id: str, document: PlanningDocument) -> dict[str, object]:
    return {
        "planning_identity_version": PLANNING_IDENTITY_VERSION,
        "book_id": book_id,
        "plan": document.content(),
    }


def planning_identity(book_id: str, document: PlanningDocument) -> str:
    digest = hashlib.sha256(canonical(planning_inputs(book_id, document))).hexdigest()
    return f"pp{IDENTITY_VERSION}-planning-sha256-{digest}"
