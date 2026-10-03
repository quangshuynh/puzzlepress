"""Single-process local HTTP boundary; no project mutations or domain rules."""

import argparse
import logging
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

from puzzlepress.errors import ProjectError

from .service import ProjectStore, StudioError, StudioService, issue_dicts

LOGGER = logging.getLogger(__name__)


class GenerationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    identity: str


def error_response(status: int, code: str, message: str) -> JSONResponse:
    return JSONResponse({"error": {"code": code, "message": message, "issues": []}}, status)


def create_app(books: Path, frontend: Path) -> FastAPI:
    service = StudioService(ProjectStore(books.resolve()))
    app = FastAPI(title="PuzzlePress Studio", docs_url=None, redoc_url=None, openapi_url=None)
    app.add_middleware(
        TrustedHostMiddleware, allowed_hosts=["127.0.0.1", "localhost", "testserver"]
    )

    @app.middleware("http")
    async def local_boundary(request: Request, call_next: RequestResponseEndpoint) -> Response:
        # A JSON POST and same-origin check prevent other sites driving local generation.
        origin = request.headers.get("origin")
        if request.method == "POST" and (
            (origin is not None and origin != str(request.base_url).rstrip("/"))
            or request.headers.get("content-type", "").split(";")[0] != "application/json"
        ):
            return error_response(403, "origin_rejected", "Use Studio on this local server.")
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Cache-Control"] = "no-store"
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

    @app.exception_handler(RequestValidationError)
    async def request_error(request: Request, error: RequestValidationError) -> JSONResponse:
        return error_response(
            422, "invalid_request", "Supply the current project identity as JSON."
        )

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
    @app.get("/books/{key}/puzzles/{puzzle_id}")
    def shell() -> FileResponse:
        index = frontend / "index.html"
        if not index.is_file():
            raise StudioError(
                503, "frontend_missing", "Build Studio first: cd studio, npm ci, npm run build."
            )
        return FileResponse(index)

    return app


def main() -> None:
    parser = argparse.ArgumentParser(description="Run the local, read-only PuzzlePress Studio.")
    parser.add_argument("--books", type=Path, default=Path("books"))
    parser.add_argument("--frontend", type=Path, default=Path("studio/dist"))
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()
    uvicorn.run(create_app(args.books, args.frontend), host="127.0.0.1", port=args.port)


if __name__ == "__main__":
    main()
