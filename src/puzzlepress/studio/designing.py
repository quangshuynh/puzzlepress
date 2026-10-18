"""Studio adapter for interior design files and the built-in design catalogue.

Python owns every theme, layout and validation rule; Studio only presents them.
Design files are validated data (never executed) and change only the draft.
"""

from puzzlepress.interior.design import design_catalogue
from puzzlepress.interior_design_file import (
    MAX_DESIGN_BYTES,
    DesignFileError,
    export_design,
    import_design,
)

from .editing import DraftStore
from .service import StudioError


class DesignService:
    def __init__(self, drafts: DraftStore) -> None:
        self.drafts = drafts

    def catalogue(self) -> dict[str, object]:
        return design_catalogue()

    def export(self, key: str, source: object, name: object) -> tuple[str, bytes]:
        project = self.drafts.validate(key, source)
        if project.interior is None:
            raise StudioError(422, "no_interior_style", "This draft has no interior style.")
        try:
            data = export_design(project.interior, name)
        except DesignFileError as error:
            raise StudioError(422, "invalid_design", str(error)) from error
        slug = "".join(c if c.isalnum() else "-" for c in str(name).strip().lower()).strip("-")
        return f"{slug or 'design'}.puzzlepress-design.json", data

    def import_file(self, key: str, source: object, text: object) -> dict[str, object]:
        """The validated `interior` section a design file gives this draft."""
        if not isinstance(text, str) or len(text.encode("utf-8")) > MAX_DESIGN_BYTES:
            raise StudioError(
                413, "design_too_large", f"A design file is at most {MAX_DESIGN_BYTES // 1024} KB."
            )
        project = self.drafts.validate(key, source)
        try:
            name, style = import_design(
                text.encode("utf-8"), project.interior, project.composition is not None
            )
        except DesignFileError as error:
            return {
                "success": False,
                "issues": [
                    {"path": i.path, "code": i.code, "message": i.message} for i in error.issues
                ],
            }
        return {"success": True, "name": name, "interior": style.to_dict()}
