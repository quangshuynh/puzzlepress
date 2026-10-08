"""Publishing identity: the authored publishing record, separate from build identity.

It covers the publishing section and the book details it references (title,
subtitle, author, imprint, language), the publishing schema version and the
engine version. Keywords or a description never change the interior's build
identity; they change this one. No paths or times.
"""

import hashlib
import json

from .. import __version__
from ..identity import IDENTITY_VERSION
from ..models import Project
from ..publishing_config import PUBLISHING_VERSION


def publishing_inputs(project: Project) -> dict[str, object]:
    """What the publishing record says: book details it references plus the section."""
    book = project.book
    return {
        "book_id": book.id,
        "book": {
            "title": book.title,
            "subtitle": book.subtitle,
            "author": book.author,
            "imprint": book.imprint,
            "language": book.language,
        },
        "publishing": project.publishing.to_dict() if project.publishing else None,
        "publishing_version": PUBLISHING_VERSION,
        "engine_version": __version__,
    }


def canonical(data: object) -> bytes:
    return json.dumps(
        data, sort_keys=True, separators=(",", ":"), ensure_ascii=True, allow_nan=False
    ).encode("ascii")


def publishing_identity(project: Project) -> str | None:
    """Identity of the publishing record; None without a publishing section."""
    if project.publishing is None:
        return None
    digest = hashlib.sha256(canonical(publishing_inputs(project))).hexdigest()
    return f"pp{IDENTITY_VERSION}-publishing-sha256-{digest}"
