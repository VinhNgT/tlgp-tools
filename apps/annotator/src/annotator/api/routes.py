"""FastAPI routes for the Annotator API.

Routes are async and delegate sync workspace calls via asyncio.to_thread().

Note: The API surface is intentionally read-only by design. It is built to serve state
and exports to the MCP client (or other local consumers). All mutations (creating
components, moving boxes) must be performed interactively through the GUI.
"""

from __future__ import annotations

import asyncio
import io
import urllib.parse
from typing import Literal

from fastapi import (
    APIRouter,
    Depends,
    Request,
)
from fastapi.responses import StreamingResponse

from annotator.models import WorkspaceState
from annotator.workspace import WorkspaceManager
from annotator.workspace.errors import (
    InvalidStateError,
)

# ── Router Definition ──────────────────────────────────────────────────


router = APIRouter()


def get_workspace(request: Request) -> WorkspaceManager:
    """Retrieve the workspace manager from the FastAPI application state."""
    return request.app.state.workspace


def _content_disposition(filename: str) -> dict[str, str]:
    """Build a Content-Disposition header with RFC 5987 encoding for non-ASCII filenames."""
    encoded = urllib.parse.quote(filename)
    return {"Content-Disposition": f"attachment; filename*=utf-8''{encoded}"}


# ── Status Routes ──────────────────────────────────────────────────────


@router.get("/health", tags=["Status"])
async def health_check() -> dict:
    """Lightweight connection check endpoint."""
    return {"status": "ok"}


# ── State Routes ───────────────────────────────────────────────────────


@router.get("/workspace/state", response_model=WorkspaceState, tags=["State"])
async def get_state(workspace: WorkspaceManager = Depends(get_workspace)):
    # workspace.state returns an immutable snapshot — safe without to_thread
    return workspace.state



@router.get("/workspace/export", tags=["Export"])
async def export_workspace(workspace: WorkspaceManager = Depends(get_workspace)):
    zip_bytes = await asyncio.to_thread(workspace.export_zip)
    return StreamingResponse(
        io.BytesIO(zip_bytes),
        media_type="application/zip",
        headers=_content_disposition("annotation_export.zip"),
    )


@router.get("/workspace/export-images", tags=["Export"])
async def export_images(
    mode: Literal["annotated", "raw", "both"] = "annotated",
    workspace: WorkspaceManager = Depends(get_workspace),
):
    if not workspace.raw_image_bytes:
        raise InvalidStateError("No image in workspace")
    zip_bytes = await asyncio.to_thread(workspace.export_images, mode)
    export_name = workspace.get_default_export_name(mode)
    return StreamingResponse(
        io.BytesIO(zip_bytes),
        media_type="application/zip",
        headers=_content_disposition(f"{export_name}.zip"),
    )
