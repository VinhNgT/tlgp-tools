"""FastAPI application factory for the Annotator API.

Creates a FastAPI instance with workspace dependency injection and
global error-to-HTTP mapping.
"""

from __future__ import annotations

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from annotator.api.routes import router
from annotator.workspace import WorkspaceManager
from annotator.workspace.errors import (
    BoundaryViolationError,
    ComponentNotFoundError,
    InvalidArchiveError,
    InvalidImageError,
    InvalidStateError,
    ParentNotFoundError,
    ReadOnlyError,
    UndoRedoError,
    WorkspaceError,
)

# Centralized error → HTTP status mapping.
# Eliminates per-route try/except boilerplate.
_ERROR_STATUS_MAP: dict[type[WorkspaceError], int] = {
    ComponentNotFoundError: 404,
    ParentNotFoundError: 404,
    InvalidArchiveError: 400,
    InvalidImageError: 400,
    InvalidStateError: 409,
    UndoRedoError: 409,
    ReadOnlyError: 403,
    BoundaryViolationError: 400,
}


def create_app(
    workspace: WorkspaceManager,
) -> FastAPI:
    """Create and configure the FastAPI application.

    Args:
        workspace: The shared WorkspaceManager instance.
    """
    app = FastAPI(title="Annotator API")

    # Global exception handler — maps WorkspaceError subtypes to HTTP responses
    @app.exception_handler(WorkspaceError)
    async def workspace_error_handler(request: Request, exc: WorkspaceError):
        status = _ERROR_STATUS_MAP.get(type(exc), 500)
        return JSONResponse(
            status_code=status,
            content={"detail": exc.message, **exc.details},
        )

    # Store workspace in app state for dependency injection
    app.state.workspace = workspace

    # Wire routes
    app.include_router(router)

    return app
