"""FastAPI routes for the Annotator API.

Routes are async and delegate sync workspace calls via asyncio.to_thread().
"""

from __future__ import annotations

import asyncio
import io
import uuid
import zipfile

from fastapi import (
    APIRouter,
    File,
    UploadFile,
)
from fastapi.responses import Response
from PIL import Image
from pydantic import BaseModel

from annotator.models import Bounds, Style, Visibility
from annotator.models.tree import TreeUtils
from annotator.rendering import paint_annotations
from annotator.workspace import WorkspaceManager
from annotator.workspace.errors import (
    ComponentNotFoundError,
    InvalidStateError,
    UndoRedoError,
)

# ── Request Models ─────────────────────────────────────────────────────


class AddComponentRequest(BaseModel):
    id: uuid.UUID | None = None
    label: str
    parentId: uuid.UUID | None = None
    bounds: dict
    style: dict | None = None
    visibility: dict | None = None


class MoveComponentRequest(BaseModel):
    x: int
    y: int


class UpdateComponentRequest(BaseModel):
    label: str | None = None
    bounds: dict | None = None
    parentId: uuid.UUID | None = None
    style: dict | None = None
    visibility: dict | None = None


class SetReadOnlyRequest(BaseModel):
    read_only: bool


class BatchComponentItem(BaseModel):
    id: uuid.UUID
    show_children: bool = False


class BatchExportRequest(BaseModel):
    include_state: bool = True
    include_root: bool = False
    show_root_children: bool = False
    components: list[BatchComponentItem] = []


# ── Image Generation ──────────────────────────────────────────────────


def generate_image_bytes(
    comp_id: str | uuid.UUID,
    workspace: WorkspaceManager,
    show_children: bool = False,
) -> bytes:
    """Generate a PNG image for a component or the root screenshot."""
    if not workspace.state.image:
        raise ValueError("Workspace image is not loaded")

    if comp_id == "root":
        bounds_left, bounds_top = 0, 0
        bounds_right, bounds_bottom = (
            workspace.state.image.width,
            workspace.state.image.height,
        )
        parent_comp = None
        children = (
            TreeUtils.get_children(workspace.state, None) if show_children else []
        )
        offset_x, offset_y = 0, 0
    else:
        comp_uuid = comp_id if isinstance(comp_id, uuid.UUID) else uuid.UUID(comp_id)
        if comp_uuid not in workspace.state.components:
            raise ComponentNotFoundError(
                "Component not found", component_id=str(comp_uuid)
            )
        comp = workspace.state.components[comp_uuid]
        bounds = comp.bounds
        bounds_left, bounds_top = bounds.left, bounds.top
        bounds_right, bounds_bottom = bounds.right, bounds.bottom
        parent_comp = comp
        children = (
            TreeUtils.get_children(workspace.state, comp_uuid) if show_children else []
        )
        offset_x, offset_y = bounds.left, bounds.top

    with Image.open(io.BytesIO(workspace.raw_image_bytes)) as img:
        cropped = img.crop((bounds_left, bounds_top, bounds_right, bounds_bottom))
        if show_children and children:
            cropped = paint_annotations(
                cropped,
                children,
                offset_x,
                offset_y,
                parent_comp,
                workspace.state.image.width,
            )
        buf = io.BytesIO()
        cropped.save(buf, format="PNG")
        return buf.getvalue()


# ── Router Factory ────────────────────────────────────────────────────


def create_router(
    workspace: WorkspaceManager,
) -> APIRouter:
    """Create the API router."""
    router = APIRouter()

    # ── State Routes ───────────────────────────────────────────────

    @router.get("/workspace/state", tags=["State"])
    async def get_state():
        # workspace.state returns an immutable snapshot — safe without to_thread
        return workspace.state.model_dump(mode="json")

    @router.put("/workspace/readonly", tags=["State"])
    async def set_workspace_readonly(req: SetReadOnlyRequest):
        await asyncio.to_thread(
            workspace.mutate, lambda s: setattr(s, "readOnly", req.read_only), True
        )
        return {"status": "success", "read_only": workspace.state.readOnly}

    @router.post("/workspace/clear", tags=["State"])
    async def clear_workspace():
        await asyncio.to_thread(workspace.clear_workspace, True)
        return {"status": "success", "sessionId": str(workspace.state.sessionId)}

    # ── Import / Export ────────────────────────────────────────────

    @router.post("/workspace/import", tags=["Import/Export"])
    async def import_workspace(file: UploadFile = File(...)):
        file_bytes = await file.read()
        await asyncio.to_thread(workspace.import_zip, file_bytes)
        return {"status": "imported", "sessionId": workspace.state.sessionId}

    @router.post("/workspace/import-image", tags=["Import/Export"])
    async def import_image(file: UploadFile = File(...)):
        file_bytes = await file.read()
        await asyncio.to_thread(
            workspace.import_image, file_bytes, file.filename or "screenshot.png"
        )
        return {"status": "image_imported", "sessionId": workspace.state.sessionId}

    @router.get("/workspace/export")
    async def export_workspace():
        zip_bytes = await asyncio.to_thread(workspace.export_zip)
        return Response(
            content=zip_bytes,
            media_type="application/zip",
            headers={
                "Content-Disposition": "attachment; filename=annotation_export.zip"
            },
        )

    # ── Component REST ─────────────────────────────────────────────

    @router.post("/components", tags=["Components"])
    async def add_component(req: AddComponentRequest):
        comp_id = req.id or uuid.uuid4()
        await asyncio.to_thread(
            workspace.add_component,
            comp_id=comp_id,
            label=req.label,
            bounds=req.bounds,
            parent_id=req.parentId,
            style=Style(**req.style) if req.style else None,
            visibility=Visibility(**req.visibility) if req.visibility else None,
        )
        return {"id": comp_id, "status": "added"}

    @router.put("/components/{comp_id}/move", tags=["Components"])
    async def move_component(comp_id: uuid.UUID, req: MoveComponentRequest):
        await asyncio.to_thread(workspace.move_component, comp_id, req.x, req.y)
        return {"status": "moved"}

    @router.put("/components/{comp_id}", tags=["Components"])
    async def update_component(comp_id: uuid.UUID, req: UpdateComponentRequest):
        await asyncio.to_thread(
            workspace.update_component,
            comp_id=comp_id,
            label=req.label,
            bounds=Bounds(**req.bounds) if req.bounds else None,
            parent_id=req.parentId,
            style=Style(**req.style) if req.style else None,
            visibility=Visibility(**req.visibility) if req.visibility else None,
        )
        return {"status": "updated"}

    @router.delete("/components/{comp_id}", tags=["Components"])
    async def delete_component(comp_id: uuid.UUID):
        await asyncio.to_thread(workspace.delete_component, comp_id)
        return {"status": "deleted"}

    @router.post("/session/undo", tags=["Session"])
    async def session_undo():
        success = await asyncio.to_thread(workspace.undo)
        if not success:
            raise UndoRedoError(
                "Cannot undo", session_id=str(workspace.state.sessionId)
            )
        return {"status": "undone"}

    @router.post("/session/redo", tags=["Session"])
    async def session_redo():
        success = await asyncio.to_thread(workspace.redo)
        if not success:
            raise UndoRedoError(
                "Cannot redo", session_id=str(workspace.state.sessionId)
            )
        return {"status": "redone"}

    # ── Image Endpoints ────────────────────────────────────────────

    @router.get("/images/{comp_id}", tags=["Image"])
    async def get_image(comp_id: str, show_children: bool = False):
        if not workspace.raw_image_bytes:
            raise InvalidStateError("No image in RAM")
        img_bytes = await asyncio.to_thread(
            generate_image_bytes, comp_id, workspace, show_children
        )
        return Response(content=img_bytes, media_type="image/png")

    @router.post("/workspace/export-batch", tags=["Import/Export"])
    async def export_batch(req: BatchExportRequest):
        if not workspace.raw_image_bytes:
            raise InvalidStateError(
                "No image in RAM", session_id=str(workspace.state.sessionId)
            )

        def _build_batch_zip() -> bytes:
            buf = io.BytesIO()
            with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
                if req.include_state:
                    zf.writestr(
                        "workspace.json", workspace.state.model_dump_json(indent=2)
                    )
                if req.include_root:
                    if workspace.state.cutLines:
                        with Image.open(io.BytesIO(workspace.raw_image_bytes)) as img:
                            img_w, img_h = img.width, img.height
                            boundaries = [0, *sorted(workspace.state.cutLines), img_h]
                            for part_idx in range(len(boundaries) - 1):
                                seg_y_start = boundaries[part_idx]
                                seg_y_end = boundaries[part_idx + 1]
                                if seg_y_end <= seg_y_start:
                                    continue
                                cropped = img.crop((0, seg_y_start, img_w, seg_y_end))
                                children = []
                                if req.show_root_children:
                                    root_children = TreeUtils.get_children(
                                        workspace.state, None
                                    )
                                    for child in root_children:
                                        center_y = (
                                            child.bounds.top + child.bounds.bottom
                                        ) / 2
                                        if seg_y_start <= center_y < seg_y_end:
                                            children.append(child)
                                if children:
                                    cropped = paint_annotations(
                                        cropped, children, 0, seg_y_start, None, img_w
                                    )
                                buf_part = io.BytesIO()
                                cropped.save(buf_part, format="PNG")
                                zf.writestr(
                                    f"raw_part{part_idx + 1}.png", buf_part.getvalue()
                                )
                    else:
                        zf.writestr(
                            "raw.png",
                            generate_image_bytes(
                                "root", workspace, req.show_root_children
                            ),
                        )
                for item in req.components:
                    zf.writestr(
                        f"images/{item.id}.png",
                        generate_image_bytes(item.id, workspace, item.show_children),
                    )
            return buf.getvalue()

        zip_content = await asyncio.to_thread(_build_batch_zip)
        return Response(
            content=zip_content,
            media_type="application/zip",
            headers={"Content-Disposition": "attachment; filename=batch_export.zip"},
        )

    return router
