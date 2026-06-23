"""FastAPI application factory for the Annotator API.

Creates a FastAPI instance with workspace dependency injection,
global error-to-HTTP mapping, and WebSocket broadcaster wiring.
"""

from __future__ import annotations

import asyncio

from annotator.workspace import WorkspaceManager
from annotator.workspace.errors import (
    ComponentNotFoundError,
    InvalidArchiveError,
    InvalidImageError,
    InvalidStateError,
    ParentNotFoundError,
    ReadOnlyError,
    UndoRedoError,
    WorkspaceError,
)
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

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
}


def create_app(
    workspace: WorkspaceManager,
    server_loop: asyncio.AbstractEventLoop,
) -> FastAPI:
    """Create and configure the FastAPI application.

    Args:
        workspace: The shared WorkspaceManager instance.
        server_loop: The asyncio event loop running the server thread.
            Passed to WebSocketBroadcaster for cross-thread event posting.
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
    app.state.server_loop = server_loop

    # Wire routes and broadcaster
    from .routes import create_router  # noqa: PLC0415

    router, broadcaster = create_router(workspace, server_loop)
    app.include_router(router)

    # Subscribe the broadcaster to workspace mutations
    workspace.subscribe(broadcaster.broadcast_sync)

    return app


def get_workspace(request: Request) -> WorkspaceManager:
    """FastAPI dependency that retrieves the workspace from app state."""
    return request.app.state.workspace
