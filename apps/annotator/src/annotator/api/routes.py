"""FastAPI routes for the Annotator API.

Routes are async and delegate sync workspace calls via asyncio.to_thread().
"""

from __future__ import annotations

import asyncio
import io
from typing import Literal

from fastapi import (
    APIRouter,
    Depends,
    Request,
)
from fastapi.responses import StreamingResponse

from annotator.models.core import WorkspaceState
from annotator.workspace import WorkspaceManager
from annotator.workspace.errors import (
    InvalidStateError,
)

# ── Router Definition ──────────────────────────────────────────────────


router = APIRouter()


def get_workspace(request: Request) -> WorkspaceManager:
    """Retrieve the workspace manager from the FastAPI application state."""
    return request.app.state.workspace


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
        headers={"Content-Disposition": "attachment; filename=annotation_export.zip"},
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
        headers={"Content-Disposition": f"attachment; filename={export_name}.zip"},
    )
