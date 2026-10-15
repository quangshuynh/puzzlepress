"""Authored YAML documents beside book.yaml: revision-checked reads and atomic writes.

Editorial reviews (reviews.yaml) and proof records (proofs.yaml) are authored
source in the project folder, outside every production identity: no build reads
them. A write checks the byte revision the author opened, stages the new text
beside the target, fsyncs, parses it back through the caller's validator,
checks the revision again and swaps it in with `os.replace`. A missing file has
no revision; creating one requires that it is still missing. Symlinks and
directories under the document's name are refused.
"""

import hashlib
import os
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from threading import Lock

from .errors import ProjectError, ValidationIssue
from .yaml_io import load_yaml

_WRITE_LOCK = Lock()


class SidecarWriteError(Exception):
    """An expected refusal: the file changed since it was opened, or could not be written."""

    def __init__(self, code: str, message: str) -> None:
        self.code = code
        super().__init__(message)


@dataclass(frozen=True)
class LoadedSidecar:
    path: Path
    data: object | None  # Decoded YAML; None when the file does not exist yet.
    revision: str | None  # sha256-<hex> of the bytes; None when absent.


def revision_of(data: bytes) -> str:
    return "sha256-" + hashlib.sha256(data).hexdigest()


def sidecar_path(source_directory: Path, name: str) -> Path:
    path = Path(source_directory) / name
    if path.is_symlink() or (path.exists() and not path.is_file()):
        raise ProjectError((ValidationIssue(name, "not_file", f"{name} must be a regular file."),))
    return path


def _read(path: Path, name: str) -> bytes | None:
    try:
        return path.read_bytes()
    except FileNotFoundError:
        return None
    except OSError as error:
        raise ProjectError((ValidationIssue(name, "io", f"Cannot read {name}."),)) from error


def read_sidecar(source_directory: Path, name: str) -> LoadedSidecar:
    path = sidecar_path(source_directory, name)
    data = _read(path, name)
    if data is None:
        return LoadedSidecar(path, None, None)
    try:
        text = data.decode("utf-8-sig")
    except UnicodeError as error:
        raise ProjectError(
            (ValidationIssue(name, "encoding", f"{name} must be UTF-8."),)
        ) from error
    return LoadedSidecar(path, load_yaml(text), revision_of(data))


def _check(path: Path, name: str, revision: str | None) -> None:
    data = _read(path, name)
    current = None if data is None else revision_of(data)
    if current != revision:
        raise SidecarWriteError(
            "source_changed",
            f"{name} changed since it was opened. Your change was not saved; reload and review it."
            if revision is not None
            else f"{name} was created by someone else. Reload and review it.",
        )


def write_sidecar(
    source_directory: Path,
    name: str,
    text: str,
    revision: str | None,
    verify: Callable[[object], object],
) -> str:
    """Replace `name` if it is still at `revision` (None: still missing); return the new one.

    `verify` validates decoded YAML and returns the normalized value; the staged
    file must decode to the same value as `text`.
    """
    with _WRITE_LOCK:
        path = sidecar_path(source_directory, name)
        expected = verify(load_yaml(text))
        temporary: Path | None = None
        replaced = False
        try:
            _check(path, name, revision)
            with tempfile.NamedTemporaryFile(
                mode="wb", prefix=".puzzlepress-", suffix=".tmp", dir=path.parent, delete=False
            ) as stream:
                temporary = Path(stream.name)
                stream.write(text.encode("utf-8"))
                stream.flush()
                os.fsync(stream.fileno())
            if verify(load_yaml(temporary.read_text(encoding="utf-8"))) != expected:
                raise RuntimeError(f"Staged {name} failed round-trip verification")
            sidecar_path(source_directory, name)
            _check(path, name, revision)
            os.replace(temporary, path)
            replaced = True
            saved = read_sidecar(source_directory, name)
            if saved.revision is None or verify(saved.data) != expected:
                raise SidecarWriteError(
                    "source_changed", f"{name} changed after saving. Reload to review."
                )
            return saved.revision
        except OSError as error:
            raise SidecarWriteError(
                "save_unconfirmed" if replaced else "save_failed",
                f"{name} was replaced but could not be confirmed. Reload before retrying."
                if replaced
                else f"Could not write {name}. Nothing was replaced.",
            ) from error
        finally:
            if temporary is not None and not replaced:
                temporary.unlink(missing_ok=True)
