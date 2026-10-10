"""Single-process local HTTP adapter; domain rules remain in the Python core."""

import argparse
import logging
import re
from pathlib import Path

import uvicorn
from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse, Response
from pydantic import BaseModel, ConfigDict
from starlette.exceptions import HTTPException
from starlette.middleware.base import RequestResponseEndpoint
from starlette.middleware.trustedhost import TrustedHostMiddleware
from starlette.staticfiles import StaticFiles

from puzzlepress.cover.assets import MAX_ASSET_BYTES
from puzzlepress.errors import ProjectError

from .covering import CoverService
from .editing import DraftStore
from .planning import PlanningInvalid, PlanningService
from .printing import PrintService
from .publishing import PublishingService
from .service import ProjectStore, StudioError, StudioService, issue_dicts, project_detail

LOGGER = logging.getLogger(__name__)


class GenerationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    identity: str


class DraftRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source: dict[str, object]


class SaveRequest(DraftRequest):
    revision: str


class BuildRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    revision: str


class InteriorBuildRequest(BuildRequest):
    profile: str | None = None


class ExportRequest(BuildRequest):
    archive: bool = False


class PlanningSaveRequest(DraftRequest):
    revision: str | None  # None: planning.yaml does not exist yet.


class ApprovalRequest(BuildRequest):
    identity: str | None  # The planning identity reviewed; None withdraws the approval.


# The only non-JSON POST: a photograph upload. Image content types are not
# CORS-safelisted, so another site cannot send one without a refused preflight.
UPLOAD_PATH = re.compile(r"/api/projects/[^/]+/cover/assets")
UPLOAD_TYPES = ("image/jpeg", "image/png")


def error_response(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse({"error": {"code": code, "message": message, "issues": []}}, status)


def create_app(books: Path, frontend: Path) -> FastAPI:
    service = StudioService(ProjectStore(books.resolve()))
    drafts = DraftStore(service.store)
    printing = PrintService(service)
    covers = CoverService(service, drafts)
    publishing = PublishingService(service, drafts)
    planning = PlanningService(service)
    app = FastAPI(title="PuzzlePress Studio", docs_url=None, redoc_url=None, openapi_url=None)
    app.add_middleware(
        TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost", "testserver"]
    )

    @app.middleware("http")
    async def local_boundary(request: Request, call_next: RequestResponseEndpoint) -> Response:
        # A JSON POST and same-origin check prevent other sites driving local generation.
        origin = request.headers.get("origin")
        kind = request.headers.get("content-type", "").split(";")[0]
        upload = UPLOAD_PATH.fullmatch(request.url.path) is not None
        if request.method == "POST" and (
            (origin is not None and origin != str(request.base_url).rstrip("/"))
            or (kind not in UPLOAD_TYPES if upload else kind != "application/json")
        ):
            return error_response(403, "origin_rejected", "Use Studio on this local server.")
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        # Digest-addressed page previews may be cached; everything else is no-store.
        response.headers.setdefault("Cache-Control", "no-store")
        response.headers["Content-Security-Policy"] = (
            "default-src 'self'; img-src 'self'; style-src 'self'; font-src 'self'; "
            "script-src 'self'; connect-src 'self'; object-src 'none'; "
            "base-uri 'none'; frame-ancestors 'none'"
        )
        return response

    @app.exception_handler(StudioError)
    async def studio_error(request: Request, error: StudioError) -> JSONResponse:
        return error_response(error.status, error.code, str(error))

    @app.exception_handler(ProjectError)
    async def project_error(request: Request, error: ProjectError) -> JSONResponse:
        return JSONResponse(
            {
                "error": {
                    "code": "invalid_project",
                    "message": "Project validation failed.",
                    "issues": issue_dicts(error),
                }
            },
            422,
        )

    @app.exception_handler(PlanningInvalid)
    async def planning_error(request: Request, error: PlanningInvalid) -> JSONResponse:
        return JSONResponse(
            {
                "error": {
                    "code": "invalid_planning",
                    "message": "The plan does not satisfy the planning schema.",
                    "issues": issue_dicts(error),
                }
            },
            422,
        )

    @app.exception_handler(RequestValidationError)
    async def request_error(request: Request, error: RequestValidationError) -> JSONResponse:
        return error_response(422, "invalid_request", "Supply the required request fields as JSON.")

    @app.exception_handler(HTTPException)
    async def http_error(request: Request, error: HTTPException) -> JSONResponse:
        return error_response(
            error.status_code,
            "not_found" if error.status_code == 404 else "http_error",
            "Page or endpoint not found." if error.status_code == 404 else "Request not supported.",
        )

    @app.exception_handler(Exception)
    async def unexpected_error(request: Request, error: Exception) -> JSONResponse:
        LOGGER.error("Unexpected Studio failure", exc_info=error)
        return error_response(
            500, "server_error", "Studio could not complete the request. See the server log."
        )

    @app.get("/api/projects")
    def projects() -> dict[str, object]:
        return {"projects": service.store.discover()}

    @app.get("/api/projects/{key}")
    def project(key: str) -> dict[str, object]:
        return service.store.detail(key)

    @app.post("/api/projects/{key}/generation")
    def generation(key: str, body: GenerationRequest) -> dict[str, object]:
        return service.generate(key, body.identity)

    @app.post("/api/projects/{key}/draft/validate")
    def validate_draft(key: str, body: DraftRequest) -> dict[str, object]:
        return project_detail(key, drafts.validate(key, body.source))

    @app.post("/api/projects/{key}/draft/preview")
    def preview_draft(key: str, body: DraftRequest) -> dict[str, object]:
        return service.generate_project(drafts.validate(key, body.source))

    @app.post("/api/projects/{key}/draft/plan")
    def plan_draft(key: str, body: DraftRequest) -> dict[str, object]:
        return service.plan_project(drafts.validate(key, body.source))

    @app.post("/api/projects/{key}/draft/save")
    def save_draft(key: str, body: SaveRequest) -> dict[str, object]:
        return drafts.save(key, body.source, body.revision)

    @app.get("/api/projects/{key}/interior")
    def interior(key: str) -> dict[str, object]:
        return printing.status(key)

    @app.post("/api/projects/{key}/interior/build")
    def build_interior(key: str, body: InteriorBuildRequest) -> dict[str, object]:
        return printing.build(key, body.revision, body.profile)

    @app.get("/api/projects/{key}/interior/pages/{page}")
    def interior_page(key: str, page: int, size: str, pdf: str) -> Response:
        image = printing.page_image(key, page, size, pdf)
        return Response(
            image,
            media_type="image/png",
            headers={"Cache-Control": "private, max-age=31536000, immutable"},
        )

    @app.get("/api/projects/{key}/cover")
    def cover(key: str) -> dict[str, object]:
        return covers.status(key)

    @app.post("/api/projects/{key}/draft/cover")
    def draft_cover(key: str, body: DraftRequest) -> dict[str, object]:
        return covers.draft(key, body.source)

    @app.post("/api/projects/{key}/cover/build")
    def build_cover(key: str, body: BuildRequest) -> dict[str, object]:
        return covers.build(key, body.revision)

    @app.get("/api/projects/{key}/cover/assets")
    def cover_assets(key: str) -> dict[str, object]:
        return covers.assets(key)

    @app.post("/api/projects/{key}/cover/assets")
    async def import_cover_photo(key: str, request: Request, name: str = "photo") -> JSONResponse:
        limit = MAX_ASSET_BYTES
        declared = request.headers.get("content-length")
        if declared is not None and (not declared.isdigit() or int(declared) > limit):
            raise StudioError(413, "image_unsupported", "The photograph file is too large.")
        chunks: list[bytes] = []
        size = 0
        async for chunk in request.stream():
            size += len(chunk)
            if size > limit:
                raise StudioError(413, "image_unsupported", "The photograph file is too large.")
            chunks.append(chunk)
        return JSONResponse(covers.import_photo(key, b"".join(chunks), name[:200]))

    @app.get("/api/projects/{key}/cover/preview")
    def cover_preview(key: str, size: str, pdf: str) -> Response:
        image = covers.image(key, pdf, size)
        return Response(
            image,
            media_type="image/png",
            headers={"Cache-Control": "private, max-age=31536000, immutable"},
        )

    @app.get("/api/projects/{key}/publishing")
    def publishing_status(key: str) -> dict[str, object]:
        return publishing.status(key)

    @app.post("/api/projects/{key}/draft/publishing")
    def draft_publishing(key: str, body: DraftRequest) -> dict[str, object]:
        return publishing.draft(key, body.source)

    @app.post("/api/projects/{key}/publishing/export")
    def export_publishing(key: str, body: ExportRequest) -> dict[str, object]:
        return publishing.export(key, body.revision, body.archive)

    @app.get("/api/projects/{key}/planning")
    def planning_status(key: str) -> dict[str, object]:
        return planning.status(key)

    @app.post("/api/projects/{key}/draft/planning")
    def draft_planning(key: str, body: DraftRequest) -> dict[str, object]:
        return planning.draft(key, body.source)

    @app.post("/api/projects/{key}/planning/save")
    def save_planning(key: str, body: PlanningSaveRequest) -> dict[str, object]:
        return planning.save(key, body.source, body.revision)

    @app.post("/api/projects/{key}/planning/approval")
    def planning_approval(key: str, body: ApprovalRequest) -> dict[str, object]:
        return planning.approval(key, body.revision, body.identity)

    if (frontend / "assets").is_dir():
        app.mount("/assets", StaticFiles(directory=frontend / "assets"), name="assets")

    @app.get("/logo.png")
    def logo() -> FileResponse:
        path = frontend / "logo.png"
        if not path.is_file():
            raise HTTPException(404)
        return FileResponse(path)

    @app.get("/")
    @app.get("/books")
    @app.get("/books/{key}")
    @app.get("/books/{key}/puzzles")
    @app.get("/books/{key}/quality")
    @app.get("/books/{key}/edit")
    @app.get("/books/{key}/book")
    @app.get("/books/{key}/print")
    @app.get("/books/{key}/cover")
    @app.get("/books/{key}/publishing")
    @app.get("/books/{key}/planning")
    @app.get("/books/{key}/puzzles/{puzzle_id}")
    def shell() -> FileResponse:
        index = frontend / "index.html"
        if not index.is_file():
            raise StudioError(
                503, "frontend_missing", "Build Studio first: cd studio, npm ci, npm run build."
            )
        return FileResponse(index)

    return app


def default_frontend() -> Path:
    """This engine checkout's built Studio, so Studio can serve a library kept elsewhere.

    An editable install resolves to the checkout's studio/dist from any working
    directory (for example a separate book repository); otherwise ./studio/dist.
    """
    checkout = Path(__file__).resolve().parents[3] / "studio" / "dist"
    return checkout if (checkout / "index.html").is_file() else Path("studio/dist")


def main(argv: list[str] | None = None) -> None:
    parser = argparse.ArgumentParser(description="Run the local PuzzlePress authoring Studio.")
    parser.add_argument(
        "--books",
        type=Path,
        default=Path("books"),
        help="Library folder whose subfolders each hold a book.yaml (any location)",
    )
    parser.add_argument("--frontend", type=Path, default=None, help="Built Studio (studio/dist)")
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args(argv)
    if not args.books.is_dir():
        parser.error(f"--books {args.books} is not a directory of book projects.")
    frontend = args.frontend if args.frontend is not None else default_frontend()
    print(f"PuzzlePress Studio library: {args.books.resolve()}")
    uvicorn.run(create_app(args.books, frontend), host="127.0.0.1", port=args.port)


if __name__ == "__main__":
    main()
