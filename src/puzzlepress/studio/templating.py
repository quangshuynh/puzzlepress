"""Studio adapter for cover templates: the gallery, previews, application and the custom store.

Browsing and previewing never save: a preview applies a template to the unsaved
draft in memory and renders it with the same Python layout and renderer as any
cover. Applying is the browser putting the returned cover into its draft, where
it can be undone or reverted before an explicit save. Custom templates are
written only by explicit save, rename, duplicate, import and delete requests.
"""

import hashlib
import json
import re
from collections import OrderedDict
from dataclasses import replace
from pathlib import Path
from threading import Lock

from puzzlepress.cover.build import read_interior_facts, render_cover
from puzzlepress.cover.font_assets import load_cover_fonts
from puzzlepress.cover.geometry import cover_geometry
from puzzlepress.cover.issues import CoverError
from puzzlepress.cover.layout import PRESETS, CoverCopy, cover_display
from puzzlepress.cover_config import CoverStyle
from puzzlepress.cover_template import (
    MAX_DESCRIPTION,
    MAX_NAME,
    MAX_TEMPLATE_BYTES,
    CoverTemplate,
    TemplateError,
    apply_template,
    parse_template,
    template_bytes,
    template_from_cover,
)
from puzzlepress.cover_template_store import (
    builtin_templates,
    check_assets,
    custom_templates,
    delete_template,
    find_template,
    save_template,
    unique_id,
)

from .covering import (
    BUNDLED_FONTS,
    COVER_SCALES,
    LOCK_WAIT,
    CoverService,
    design_checks,
    display_checks,
    issue_checks,
    layout_checks,
    present_layout,
)
from .service import StudioError

FACE_LABELS = {face.value: f"{family} {style}" for family, style, face in BUNDLED_FONTS}
FAMILY_LABELS = {"sans": "Vera Sans", "serif": "Newsreader", "serif-display": "Newsreader Display"}
PREVIEW_CACHE = 64


def _slug(name: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", name.lower()).strip("-")[:36].strip("-") or "template"


def _text(raw: object, field: str, limit: int, empty: bool = False) -> str:
    if (
        not isinstance(raw, str)
        or (not raw.strip() and not empty)
        or len(raw.strip()) > limit
        or any(ord(c) < 32 for c in raw)
    ):
        raise StudioError(422, "invalid_request", f"The {field} is 1..{limit} characters.")
    return raw.strip()


def _error(error: TemplateError) -> StudioError:
    status = {
        "template_not_found": 404,
        "template_exists": 409,
        "source_changed": 409,
        "template_builtin": 403,
        "save_failed": 503,
    }.get(error.code, 422)
    message = str(error)
    if error.issues:
        message += " " + " ".join(f"{i.path}: {i.message}" for i in error.issues[:6])
    return StudioError(status, error.code, message)


def requirements(template: CoverTemplate) -> list[str]:
    """Every font the template's design asks for, by name."""
    style = template.design.get("type", {})
    preset = PRESETS[
        CoverStyle(str(style.get("style", "editorial")) if isinstance(style, dict) else "editorial")
    ]
    faces = {
        preset.title_face.value,
        preset.subtitle_face.value,
        preset.author_face.value,
        preset.body_face.value,
        preset.imprint_face.value,
    }
    imported = {font.id: font.path.rsplit("/", 1)[-1] for font in template.fonts}
    names = set()
    for face in faces | set(template.faces()):
        if face in imported:
            names.add(f"{imported[face]} (imported)")
        else:
            names.add(FACE_LABELS.get(face) or FAMILY_LABELS.get(face, face))
    return sorted(names)


def present(template: CoverTemplate) -> dict[str, object]:
    return {
        "id": template.id,
        "name": template.name,
        "description": template.description,
        "category": template.category.value,
        "photo": template.photo.value,
        "slots": len(template.slots()),
        "builtin": template.builtin,
        "palette": list(template.palette),
        "fonts": requirements(template),
        "imported_fonts": [font.path for font in template.fonts],
        "provenance": template.provenance,
        "identity": template.identity(),
    }


class TemplateService:
    def __init__(self, covers: CoverService) -> None:
        self.covers = covers
        self.store = covers.store
        self.drafts = covers.drafts
        self._lock = Lock()
        self._previews: OrderedDict[str, dict[str, object]] = OrderedDict()

    def _source(self, key: str) -> Path:
        return self.store.source(key).parent

    def gallery(self, key: str) -> dict[str, object]:
        source = self._source(key)
        try:
            custom, problems = custom_templates(source)
        except TemplateError as error:
            raise _error(error) from error
        return {
            "templates": [present(t) for t in (*builtin_templates(), *custom)],
            "problems": [problem.to_dict() for problem in problems],
        }

    def _find(self, source: Path, template_id: str) -> CoverTemplate:
        try:
            template = find_template(source, template_id)
            check_assets(template, source)
        except TemplateError as error:
            raise _error(error) from error
        return template

    # ------------------------------------------------------------ previews

    def preview(self, key: str, template_id: str, source_data: object) -> dict[str, object]:
        """The draft with `template_id` applied, rendered in memory. Nothing is saved."""
        project = self.drafts.validate(key, source_data)
        if project.cover is None:
            raise StudioError(422, "no_cover", "This draft has no cover section.")
        source = self._source(key)
        template = self._find(source, template_id)
        with self.covers.service.exclusive(wait=LOCK_WAIT):
            _, directory = self.covers._folders(key, project)
            try:
                interior = read_interior_facts(directory, project, require_current=False)
            except CoverError as error:
                return {
                    "success": False,
                    "template": present(template),
                    "stage": error.stage,
                    "diagnostics": [issue.to_dict() for issue in error.issues],
                }
            cache_key = hashlib.sha256(
                json.dumps(
                    [
                        template.identity(),
                        project.to_dict(),
                        interior.interior_identity,
                        interior.physical(),
                    ],
                    sort_keys=True,
                    default=str,
                ).encode()
            ).hexdigest()
            with self._lock:
                cached = self._previews.get(cache_key)
            if cached is not None:
                return cached
            try:
                geometry = cover_geometry(
                    interior.page_count, interior.trim_width, interior.trim_height, interior.paper
                )
                application = apply_template(
                    template,
                    project,
                    geometry.spine_width,
                    (interior.trim_width, interior.trim_height),
                )
            except CoverError as error:
                return {
                    "success": False,
                    "template": present(template),
                    "stage": error.stage,
                    "diagnostics": [issue.to_dict() for issue in error.issues],
                }
            except TemplateError as error:
                raise _error(error) from error
            applied = replace(project, cover=application.cover)
            try:
                photos = self.covers._photo_set(source, applied)
                fonts = load_cover_fonts(source, application.cover)
                build = render_cover(
                    applied, interior, photos, fonts=fonts, allow_layout_issues=True
                )
            except CoverError as error:
                return {
                    "success": False,
                    "template": present(template),
                    "stage": error.stage,
                    "diagnostics": [issue.to_dict() for issue in error.issues],
                }
        digest = self.covers._remember(build.pdf)
        result: dict[str, object] = {
            "success": True,
            "template": present(template),
            "cover": application.cover.to_dict(),
            "missing_slots": list(application.missing_slots),
            "replaced": list(application.replaced),
            "kept": list(application.kept),
            "current": CoverCopy.from_project(project).to_dict(),
            "display": cover_display(application.cover, CoverCopy.from_project(applied)),
            "checks": issue_checks(build.layout_issues)
            + display_checks(applied)
            + layout_checks(build.layout, interior.page_count)
            + design_checks(build.layout),
            "buildable": not build.layout_issues,
            "layout": present_layout(build.layout),
            "preview": {"pdf_sha256": digest, "scales": COVER_SCALES},
        }
        with self._lock:
            self._previews[cache_key] = result
            while len(self._previews) > PREVIEW_CACHE:
                self._previews.popitem(last=False)
        return result

    # ------------------------------------------------------------ custom templates

    def save(
        self, key: str, source_data: object, name: object, description: object
    ) -> dict[str, object]:
        """Save the draft's cover design as a new custom template (no book identity)."""
        project = self.drafts.validate(key, source_data)
        if project.cover is None:
            raise StudioError(422, "no_cover", "This draft has no cover section.")
        title = _text(name, "name", MAX_NAME)
        about = _text(description, "description", MAX_DESCRIPTION, empty=True)
        source = self._source(key)
        _, directory = self.covers._folders(key, project)
        try:
            facts = read_interior_facts(directory, project, require_current=False)
            spine = cover_geometry(
                facts.page_count, facts.trim_width, facts.trim_height, facts.paper
            ).spine_width
        except CoverError:
            spine = 0.0  # No interior yet: spine boxes keep their authored width.
        try:
            template = template_from_cover(
                project, unique_id(source, _slug(title)), title, about, spine
            )
            saved = save_template(source, template)
        except TemplateError as error:
            raise _error(error) from error
        return {"template": present(saved), **self.gallery(key)}

    def update(
        self, key: str, template_id: str, identity: str, name: object, description: object
    ) -> dict[str, object]:
        source = self._source(key)
        current = self._find(source, template_id)
        if current.builtin:
            raise StudioError(403, "template_builtin", "Built-in templates cannot be renamed.")
        renamed = replace(
            current,
            name=_text(name, "name", MAX_NAME),
            description=_text(description, "description", MAX_DESCRIPTION, empty=True),
        )
        try:
            saved = save_template(source, renamed, identity)
        except TemplateError as error:
            raise _error(error) from error
        return {"template": present(saved), **self.gallery(key)}

    def duplicate(self, key: str, template_id: str, name: object) -> dict[str, object]:
        source = self._source(key)
        original = self._find(source, template_id)
        title = _text(name, "name", MAX_NAME)
        try:
            copy = replace(original, id=unique_id(source, _slug(title)), name=title)
            saved = save_template(source, copy)
        except TemplateError as error:
            raise _error(error) from error
        return {"template": present(saved), **self.gallery(key)}

    def delete(self, key: str, template_id: str, identity: str) -> dict[str, object]:
        try:
            delete_template(self._source(key), template_id, identity)
        except TemplateError as error:
            raise _error(error) from error
        return self.gallery(key)

    def export(self, key: str, template_id: str) -> tuple[str, bytes]:
        template = self._find(self._source(key), template_id)
        return f"{template.id}.puzzlepress-template.json", template_bytes(template)

    def import_template(self, key: str, text: object) -> dict[str, object]:
        """Validate a template file's text and add it as a custom template. Never executed."""
        if not isinstance(text, str) or len(text.encode("utf-8")) > MAX_TEMPLATE_BYTES:
            raise StudioError(
                413, "template_too_large", f"A template is at most {MAX_TEMPLATE_BYTES // 1024} KB."
            )
        source = self._source(key)
        try:
            template = parse_template(text.encode("utf-8"))
            check_assets(template, source)
            template = replace(template, id=unique_id(source, template.id))
            saved = save_template(source, template)
        except TemplateError as error:
            raise _error(error) from error
        return {"template": present(saved), **self.gallery(key)}
