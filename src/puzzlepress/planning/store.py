"""planning.yaml beside book.yaml: reading, and the one writer of planning source.

The planning document is authored source in the project folder, never in a
build directory, and no build reads it. Reads are side-effect free. Writes go
through `write_planning` only: the byte revision the author opened is checked,
the normalized document is staged beside the target, fsynced, parsed back and
compared, the revision is checked again, and `os.replace` swaps it in. A
missing file has no revision; creating one requires that it is still missing.
Comments and formatting are not preserved (the same contract as book.yaml).
"""

import hashlib
import os
import tempfile
from dataclasses import dataclass
from pathlib import Path
from threading import Lock

import yaml

from ..errors import ProjectError, ValidationIssue
from ..yaml_io import load_yaml
from .model import PLANNING_FILE, PlanningDocument
from .schema import validate_planning

_WRITE_LOCK = Lock()


class PlanningWriteError(Exception):
    """An expected write refusal: the file changed, or the write could not finish."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


@dataclass(frozen=True)
class LoadedPlan:
    path: Path
    document: PlanningDocument | None  # None: no planning.yaml yet.
    revision: str | None  # sha256-<hex> of the file's bytes; None when absent.


def revision_of(data: bytes) -> str:
    return "sha256-" + hashlib.sha256(data).hexdigest()


def planning_path(source_directory: Path) -> Path:
    """planning.yaml in the project folder; a symlink or directory is refused."""
    path = Path(source_directory) / PLANNING_FILE
    if path.is_symlink() or (path.exists() and not path.is_file()):
        raise ProjectError(
            (ValidationIssue("planning", "not_file", f"{PLANNING_FILE} must be a regular file."),)
        )
    return path


def parse_planning(text: str) -> PlanningDocument:
    document, issues = validate_planning(load_yaml(text))
    if document is None:
        raise ProjectError(issues)
    return document


def dump_planning(document: PlanningDocument) -> str:
    """Normalized YAML in document order (concept first, approval last)."""
    return yaml.safe_dump(document.to_dict(), allow_unicode=True, sort_keys=False, width=88)


def _read(path: Path) -> bytes | None:
    try:
        return path.read_bytes()
    except FileNotFoundError:
        return None
    except OSError as error:
        raise ProjectError(
            (ValidationIssue("planning", "io", f"Cannot read {PLANNING_FILE}."),)
        ) from error


def read_planning(source_directory: Path) -> LoadedPlan:
    path = planning_path(source_directory)
    data = _read(path)
    if data is None:
        return LoadedPlan(path, None, None)
    try:
        text = data.decode("utf-8-sig")
    except UnicodeError as error:
        raise ProjectError(
            (ValidationIssue("planning", "encoding", f"{PLANNING_FILE} must be UTF-8."),)
        ) from error
    return LoadedPlan(path, parse_planning(text), revision_of(data))


def _check(path: Path, revision: str | None) -> None:
    data = _read(path)
    current = None if data is None else revision_of(data)
    if current != revision:
        raise PlanningWriteError(
            "source_changed",
            f"{PLANNING_FILE} changed since it was opened. Your draft is intact; reload and "
            "review the saved plan."
            if revision is not None
            else f"{PLANNING_FILE} was created by someone else. Reload and review it.",
        )


def write_planning(
    source_directory: Path, document: PlanningDocument, revision: str | None
) -> LoadedPlan:
    """Replace planning.yaml if it is still at `revision` (None: still missing)."""
    with _WRITE_LOCK:
        path = planning_path(source_directory)
        text = dump_planning(document)
        if parse_planning(text) != document:
            raise RuntimeError("Planning document failed round-trip verification")
        temporary: Path | None = None
        replaced = False
        try:
            _check(path, revision)
            with tempfile.NamedTemporaryFile(
                mode="wb", prefix=".puzzlepress-", suffix=".tmp", dir=path.parent, delete=False
            ) as stream:
                temporary = Path(stream.name)
                stream.write(text.encode("utf-8"))
                stream.flush()
                os.fsync(stream.fileno())
            if parse_planning(temporary.read_text(encoding="utf-8")) != document:
                raise RuntimeError("Staged planning document failed verification")
            planning_path(source_directory)
            _check(path, revision)
            os.replace(temporary, path)
            replaced = True
            saved = read_planning(source_directory)
            if saved.document != document:
                raise PlanningWriteError(
                    "source_changed", f"{PLANNING_FILE} changed after saving. Reload to review."
                )
            return saved
        except OSError as error:
            raise PlanningWriteError(
                "save_unconfirmed" if replaced else "save_failed",
                f"{PLANNING_FILE} was replaced but could not be confirmed. Reload before retrying."
                if replaced
                else f"Could not write {PLANNING_FILE}. Nothing was replaced; your draft is "
                "still available.",
            ) from error
        finally:
            if temporary is not None and not replaced:
                temporary.unlink(missing_ok=True)
