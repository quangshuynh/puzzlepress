"""Built-in and custom cover templates on disk.

Built-in templates ship inside the package (`cover/templates/*.json`), are
validated when first read and can never be changed or deleted. Custom templates
are authored source in the project's `cover-templates/` directory, one canonical
JSON file per template named by its id, outside every production identity: no
build reads them. Writes stage the file beside the target, fsync, read it back
through the template validator and swap it in with `os.replace`; replacing or
deleting a template requires the identity the author last saw. Symlinks and
directories under a template's name are refused.

A custom template's imported fonts are project assets: it applies only in a
project that holds the same font files (same path and SHA-256). Photographs are
never stored; they are slots filled from the cover being redesigned.
"""

import functools
import hashlib
import os
import tempfile
from dataclasses import dataclass, replace
from importlib import resources
from pathlib import Path
from threading import Lock

from .cover_template import (
    MAX_TEMPLATE_BYTES,
    CoverTemplate,
    TemplateCategory,
    TemplateError,
    parse_template,
    template_bytes,
)
from .errors import ValidationIssue

DIRECTORY = "cover-templates"
MAX_CUSTOM = 100
# Gallery order of the built-in templates.
BUILTIN_ORDER = (
    "photographic-editorial",
    "bold-garage",
    "motorsport-energy",
    "vintage-motoring",
    "modern-minimal",
    "technical-blueprint",
    "classic-puzzle-collection",
    "premium-editorial",
)
_WRITE_LOCK = Lock()


@functools.cache
def builtin_templates() -> tuple[CoverTemplate, ...]:
    """The shipped templates, validated, in gallery order. A broken one is a bug: it raises."""
    folder = resources.files("puzzlepress") / "cover" / "templates"
    found = {
        entry.name.removesuffix(".json"): parse_template(entry.read_bytes(), builtin=True)
        for entry in folder.iterdir()
        if entry.name.endswith(".json")
    }
    if set(found) != set(BUILTIN_ORDER) or any(t.id != key for key, t in found.items()):
        raise RuntimeError("The built-in cover templates do not match their manifest")
    return tuple(found[key] for key in BUILTIN_ORDER)


def builtin_ids() -> frozenset[str]:
    return frozenset(BUILTIN_ORDER)


@dataclass(frozen=True)
class TemplateProblem:
    """A custom template file that could not be read; it is listed, never hidden."""

    file: str
    code: str
    message: str

    def to_dict(self) -> dict[str, str]:
        return {"file": self.file, "code": self.code, "message": self.message}


def _directory(source_directory: Path) -> Path:
    path = Path(source_directory) / DIRECTORY
    if path.is_symlink() or (path.exists() and not path.is_dir()):
        raise TemplateError("not_directory", f"{DIRECTORY} must be a regular directory.")
    return path


def _path(source_directory: Path, template_id: str) -> Path:
    path = _directory(source_directory) / f"{template_id}.json"
    if path.is_symlink() or (path.exists() and not path.is_file()):
        raise TemplateError("not_file", f"{DIRECTORY}/{template_id}.json must be a regular file.")
    return path


def custom_templates(
    source_directory: Path,
) -> tuple[tuple[CoverTemplate, ...], tuple[TemplateProblem, ...]]:
    directory = _directory(source_directory)
    if not directory.exists():
        return (), ()
    templates: list[CoverTemplate] = []
    problems: list[TemplateProblem] = []
    entries = sorted(p for p in directory.iterdir() if p.suffix == ".json")
    for path in entries[:MAX_CUSTOM]:
        name = f"{DIRECTORY}/{path.name}"
        if path.is_symlink() or not path.is_file():
            problems.append(TemplateProblem(name, "not_file", "Not a regular file."))
            continue
        try:
            if path.stat().st_size > MAX_TEMPLATE_BYTES:
                raise TemplateError("template_too_large", "The file is too large.")
            template = parse_template(path.read_bytes())
        except TemplateError as error:
            problems.append(TemplateProblem(name, error.code, str(error)))
            continue
        except OSError:
            problems.append(TemplateProblem(name, "io", "The file cannot be read."))
            continue
        if template.id != path.stem or template.id in BUILTIN_ORDER:
            problems.append(
                TemplateProblem(
                    name, "id_mismatch", "The file name must be the template id, not a built-in id."
                )
            )
            continue
        templates.append(template)
    if len(entries) > MAX_CUSTOM:
        problems.append(
            TemplateProblem(
                DIRECTORY, "too_many", f"Only the first {MAX_CUSTOM} templates are listed."
            )
        )
    templates.sort(key=lambda t: (t.name.casefold(), t.id))
    return tuple(templates), tuple(problems)


def find_template(source_directory: Path | None, template_id: str) -> CoverTemplate:
    for template in builtin_templates():
        if template.id == template_id:
            return template
    if source_directory is not None:
        path = _path(source_directory, template_id)
        if path.is_file():
            template = parse_template(path.read_bytes())
            if template.id == template_id:
                return template
    raise TemplateError("template_not_found", f"There is no template {template_id!r}.")


def check_assets(template: CoverTemplate, source_directory: Path) -> None:
    """Refuse a template whose imported fonts are not this project's files, byte for byte."""
    root = Path(source_directory).resolve()
    issues: list[ValidationIssue] = []
    for index, font in enumerate(template.fonts):
        path = root / font.path
        try:
            inside = path.resolve().is_relative_to(root) and not path.is_symlink()
            digest = hashlib.sha256(path.read_bytes()).hexdigest() if inside else None
        except OSError:
            digest = None
        if digest != font.sha256:
            issues.append(
                ValidationIssue(
                    f"template.fonts.{index}",
                    "template_font_missing",
                    f"The font {font.path} ({font.id}) is not in this project with the same "
                    "contents. Import the font first, then the template.",
                )
            )
    if issues:
        raise TemplateError(
            "template_font_missing",
            "This template uses fonts this project does not have.",
            tuple(issues),
        )


def _write(path: Path, template: CoverTemplate) -> None:
    data = template_bytes(template)
    temporary: Path | None = None
    try:
        with tempfile.NamedTemporaryFile(
            mode="wb", prefix=".puzzlepress-", suffix=".tmp", dir=path.parent, delete=False
        ) as stream:
            temporary = Path(stream.name)
            stream.write(data)
            stream.flush()
            os.fsync(stream.fileno())
        if parse_template(temporary.read_bytes()) != template:
            raise RuntimeError("A staged cover template failed round-trip verification")
        os.replace(temporary, path)
        temporary = None
    except OSError as error:
        raise TemplateError("save_failed", "The template could not be written.") from error
    finally:
        if temporary is not None:
            temporary.unlink(missing_ok=True)


def save_template(
    source_directory: Path, template: CoverTemplate, identity: str | None = None
) -> CoverTemplate:
    """Create a custom template, or replace the one at `identity`. Returns what was saved."""
    if template.id in BUILTIN_ORDER:
        raise TemplateError("template_builtin", "Built-in templates cannot be replaced.")
    template = replace(template, category=TemplateCategory.CUSTOM, builtin=False)
    with _WRITE_LOCK:
        directory = _directory(source_directory)
        directory.mkdir(exist_ok=True)
        path = _path(source_directory, template.id)
        current = parse_template(path.read_bytes()) if path.is_file() else None
        if current is None and identity is not None:
            raise TemplateError("source_changed", "The template was deleted. Reload the gallery.")
        if current is not None and current.identity() != identity:
            raise TemplateError(
                "template_exists" if identity is None else "source_changed",
                f"A template named {template.id!r} already exists."
                if identity is None
                else "The template changed since it was opened. Reload the gallery.",
            )
        if current is None:
            custom, _ = custom_templates(source_directory)
            if len(custom) >= MAX_CUSTOM:
                raise TemplateError("too_many", f"A project keeps at most {MAX_CUSTOM} templates.")
        _write(path, template)
    return template


def delete_template(source_directory: Path, template_id: str, identity: str) -> None:
    """Delete a custom template the author confirmed at `identity`."""
    if template_id in BUILTIN_ORDER:
        raise TemplateError("template_builtin", "Built-in templates cannot be deleted.")
    with _WRITE_LOCK:
        path = _path(source_directory, template_id)
        if not path.is_file():
            raise TemplateError("template_not_found", f"There is no template {template_id!r}.")
        if parse_template(path.read_bytes()).identity() != identity:
            raise TemplateError(
                "source_changed", "The template changed since it was opened. Reload the gallery."
            )
        path.unlink()


def unique_id(source_directory: Path, base: str) -> str:
    """`base`, or `base-2`, `base-3`... so it names no built-in or existing template."""
    taken = set(BUILTIN_ORDER) | {t.id for t in custom_templates(source_directory)[0]}
    directory = _directory(source_directory)
    stem = base[:36].strip("-") or "template"
    candidate, n = stem, 2
    while candidate in taken or (directory / f"{candidate}.json").exists():
        candidate, n = f"{stem}-{n}", n + 1
    return candidate
