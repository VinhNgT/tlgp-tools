import asyncio
import io
import json
import uuid
import zipfile

from annotator.models import Bounds, Style, Visibility, WorkspaceState
from annotator.models.tree import TreeUtils
from annotator.rendering import paint_annotations
from annotator.workspace import WorkspaceManager
from annotator.workspace.errors import (
    ComponentNotFoundError,
    InvalidStateError,
    UndoRedoError,
)
from fastapi import (
    APIRouter,
    Depends,
    File,
    UploadFile,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.responses import Response
from PIL import Image
from pydantic import BaseModel

from .app import get_workspace

router = APIRouter()

class WebSocketBroadcaster:
    def __init__(self):
        self.active_connections: list[WebSocket] = []
        self.loop = None

    def set_loop(self, loop: asyncio.AbstractEventLoop):
        self.loop = loop

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    def broadcast_sync(self, patch: list[dict], new_state: WorkspaceState):
        """Called by WorkspaceManager on any mutation."""
        if not self.loop or self.loop.is_closed():
            return

        if patch and patch[0].get("op") == "replace" and patch[0].get("path") == "":
            msg = {"type": "full_sync", "state": patch[0]["value"]}
        else:
            msg = {"type": "patch", "revision": new_state.revision, "patch": patch}

        asyncio.run_coroutine_threadsafe(self._broadcast(msg), self.loop)

    async def _broadcast(self, msg: dict):
        for connection in list(self.active_connections):
            try:
                await connection.send_json(msg)
            except Exception:
                self.disconnect(connection)

broadcaster = WebSocketBroadcaster()

@router.on_event("startup")
async def startup_event():
    broadcaster.set_loop(asyncio.get_running_loop())

@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket, workspace: WorkspaceManager = Depends(get_workspace)):
    await broadcaster.connect(websocket)
    try:
        await websocket.send_json({"type": "full_sync", "state": workspace.state.model_dump(mode="json")})

        while True:
            data_str = await websocket.receive_text()
            try:
                rpc_req = json.loads(data_str)
                if not isinstance(rpc_req, dict) or rpc_req.get("jsonrpc") != "2.0":
                    continue
                req_id = rpc_req.get("id")
                method = rpc_req.get("method")
                params = rpc_req.get("params", {})

                result = handle_json_rpc(method, params, workspace)
                await websocket.send_json({"jsonrpc": "2.0", "result": result, "id": req_id})

            except Exception as e:
                error_msg = getattr(e, "message", str(e))
                await websocket.send_json({
                    "jsonrpc": "2.0",
                    "error": {"code": -32603, "message": error_msg},
                    "id": rpc_req.get("id") if "rpc_req" in locals() and isinstance(rpc_req, dict) else None,
                })
    except WebSocketDisconnect:
        broadcaster.disconnect(websocket)

def handle_json_rpc(method: str, params: dict, workspace: WorkspaceManager) -> dict:
    if method == "add_component":
        comp_id = uuid.UUID(params.get("id")) if params.get("id") else uuid.uuid4()
        workspace.add_component(
            comp_id=comp_id,
            label=params["label"],
            bounds=params["bounds"],
            parent_id=uuid.UUID(params["parentId"]) if params.get("parentId") else None,
            style=Style(**params["style"]) if params.get("style") else None,
            visibility=Visibility(**params["visibility"]) if params.get("visibility") else None,
        )
        return {"id": str(comp_id), "status": "added"}
    elif method == "move_component":
        comp_id = uuid.UUID(str(params.get("comp_id") or params.get("id")))
        workspace.move_component(comp_id, params["x"], params["y"])
        return {"status": "moved"}
    elif method == "update_component":
        comp_id = uuid.UUID(str(params.get("comp_id") or params.get("id")))
        workspace.update_component(
            comp_id=comp_id,
            label=params.get("label"),
            bounds=Bounds(**params["bounds"]) if params.get("bounds") else None,
            parent_id=uuid.UUID(params["parentId"]) if params.get("parentId") else None,
            style=Style(**params["style"]) if params.get("style") else None,
            visibility=Visibility(**params["visibility"]) if params.get("visibility") else None,
        )
        return {"status": "updated"}
    elif method == "delete_component":
        comp_id = uuid.UUID(str(params.get("comp_id") or params.get("id")))
        workspace.delete_component(comp_id)
        return {"status": "deleted"}
    elif method == "undo":
        if not workspace.undo():
            raise UndoRedoError("Cannot undo", session_id=str(workspace.state.sessionId))
        return {"status": "undone"}
    elif method == "redo":
        if not workspace.redo():
            raise UndoRedoError("Cannot redo", session_id=str(workspace.state.sessionId))
        return {"status": "redone"}
    elif method == "update_cut_lines":
        workspace.update_cut_lines(params["lines"])
        return {"status": "updated_cuts"}
    elif method == "update_screen_info":
        workspace.update_screen_info(params["name"], params["description"])
        return {"status": "updated_screen_info"}
    else:
        raise ValueError(f"Method '{method}' not found")

# ── Import / Export ────────────────────────────────────────────────────

@router.post("/workspace/import", tags=["Import/Export"])
def import_workspace(file: UploadFile = File(...), workspace: WorkspaceManager = Depends(get_workspace)):
    file_bytes = file.file.read()
    workspace.import_zip(file_bytes)
    return {"status": "imported", "sessionId": workspace.state.sessionId}

@router.post("/workspace/import-image", tags=["Import/Export"])
def import_image(file: UploadFile = File(...), workspace: WorkspaceManager = Depends(get_workspace)):
    file_bytes = file.file.read()
    workspace.import_image(file_bytes, file.filename or "screenshot.png")
    return {"status": "image_imported", "sessionId": workspace.state.sessionId}

@router.get("/workspace/export")
def export_workspace(workspace: WorkspaceManager = Depends(get_workspace)):
    zip_bytes = workspace.export_zip()
    return Response(
        content=zip_bytes,
        media_type="application/zip",
        headers={"Content-Disposition": "attachment; filename=annotation_export.zip"},
    )

@router.get("/workspace/state", tags=["State"])
def get_state(workspace: WorkspaceManager = Depends(get_workspace)):
    return workspace.state.model_dump(mode="json")

class SetReadOnlyRequest(BaseModel):
    read_only: bool

@router.put("/workspace/readonly", tags=["State"])
def set_workspace_readonly(req: SetReadOnlyRequest, workspace: WorkspaceManager = Depends(get_workspace)):
    workspace.mutate(lambda s: setattr(s, "readOnly", req.read_only), force=True)
    return {"status": "success", "read_only": workspace.state.readOnly}

@router.post("/workspace/clear", tags=["State"])
def clear_workspace(workspace: WorkspaceManager = Depends(get_workspace)):
    workspace.clear_workspace(force=True)
    return {"status": "success", "sessionId": str(workspace.state.sessionId)}

# ── Semantic REST Endpoints ────────────────────────────────────────────

class AddComponentRequest(BaseModel):
    id: uuid.UUID | None = None
    label: str
    parentId: uuid.UUID | None = None
    bounds: dict
    style: dict | None = None
    visibility: dict | None = None

@router.post("/components", tags=["Components"])
def add_component(req: AddComponentRequest, workspace: WorkspaceManager = Depends(get_workspace)):
    comp_id = req.id or uuid.uuid4()
    workspace.add_component(
        comp_id=comp_id,
        label=req.label,
        bounds=req.bounds,
        parent_id=req.parentId,
        style=Style(**req.style) if req.style else None,
        visibility=Visibility(**req.visibility) if req.visibility else None,
    )
    return {"id": comp_id, "status": "added"}

class MoveComponentRequest(BaseModel):
    x: int
    y: int

@router.put("/components/{comp_id}/move", tags=["Components"])
def move_component(comp_id: uuid.UUID, req: MoveComponentRequest, workspace: WorkspaceManager = Depends(get_workspace)):
    workspace.move_component(comp_id, req.x, req.y)
    return {"status": "moved"}

class UpdateComponentRequest(BaseModel):
    label: str | None = None
    bounds: dict | None = None
    parentId: uuid.UUID | None = None
    style: dict | None = None
    visibility: dict | None = None

@router.put("/components/{comp_id}", tags=["Components"])
def update_component(comp_id: uuid.UUID, req: UpdateComponentRequest, workspace: WorkspaceManager = Depends(get_workspace)):
    workspace.update_component(
        comp_id=comp_id,
        label=req.label,
        bounds=Bounds(**req.bounds) if req.bounds else None,
        parent_id=req.parentId,
        style=Style(**req.style) if req.style else None,
        visibility=Visibility(**req.visibility) if req.visibility else None,
    )
    return {"status": "updated"}

@router.delete("/components/{comp_id}", tags=["Components"])
def delete_component(comp_id: uuid.UUID, workspace: WorkspaceManager = Depends(get_workspace)):
    workspace.delete_component(comp_id)
    return {"status": "deleted"}

@router.post("/session/undo", tags=["Session"])
def session_undo(workspace: WorkspaceManager = Depends(get_workspace)):
    if not workspace.undo():
        raise UndoRedoError("Cannot undo", session_id=str(workspace.state.sessionId))
    return {"status": "undone"}

@router.post("/session/redo", tags=["Session"])
def session_redo(workspace: WorkspaceManager = Depends(get_workspace)):
    if not workspace.redo():
        raise UndoRedoError("Cannot redo", session_id=str(workspace.state.sessionId))
    return {"status": "redone"}

# ── Image Endpoints ────────────────────────────────────────────────────

class BatchComponentItem(BaseModel):
    id: uuid.UUID
    show_children: bool = False

class BatchExportRequest(BaseModel):
    include_state: bool = True
    include_root: bool = False
    show_root_children: bool = False
    components: list[BatchComponentItem] = []

def generate_image_bytes(comp_id: str | uuid.UUID, workspace: WorkspaceManager, show_children: bool = False) -> bytes:
    if comp_id == "root":
        bounds_left, bounds_top, bounds_right, bounds_bottom = 0, 0, workspace.state.image.width, workspace.state.image.height
        parent_comp = None
        children = TreeUtils.get_children(workspace.state, None) if show_children else []
        offset_x, offset_y = 0, 0
    else:
        comp_uuid = comp_id if isinstance(comp_id, uuid.UUID) else uuid.UUID(comp_id)
        if comp_uuid not in workspace.state.components:
            raise ComponentNotFoundError("Component not found", component_id=str(comp_uuid))
        comp = workspace.state.components[comp_uuid]
        bounds = comp.bounds
        bounds_left, bounds_top, bounds_right, bounds_bottom = bounds.left, bounds.top, bounds.right, bounds.bottom
        parent_comp = comp
        children = TreeUtils.get_children(workspace.state, comp_uuid) if show_children else []
        offset_x, offset_y = bounds.left, bounds.top

    with Image.open(io.BytesIO(workspace.raw_image_bytes)) as img:
        cropped = img.crop((bounds_left, bounds_top, bounds_right, bounds_bottom))
        if show_children and children:
            cropped = paint_annotations(cropped, children, offset_x, offset_y, parent_comp, workspace.state.image.width)
        buf = io.BytesIO()
        cropped.save(buf, format="PNG")
        return buf.getvalue()

@router.post("/workspace/export-batch", tags=["Import/Export"])
def export_batch(req: BatchExportRequest, workspace: WorkspaceManager = Depends(get_workspace)):
    if not workspace.raw_image_bytes:
        raise InvalidStateError("No image in RAM", session_id=str(workspace.state.sessionId))

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        if req.include_state:
            zf.writestr("workspace.json", workspace.state.model_dump_json(indent=2))
        if req.include_root:
            if workspace.state.cutLines:
                with Image.open(io.BytesIO(workspace.raw_image_bytes)) as img:
                    img_w, img_h = img.width, img.height
                    boundaries = [0] + sorted(workspace.state.cutLines) + [img_h]
                    for part_idx in range(len(boundaries) - 1):
                        seg_y_start = boundaries[part_idx]
                        seg_y_end = boundaries[part_idx + 1]
                        if seg_y_end <= seg_y_start:
                            continue
                        cropped = img.crop((0, seg_y_start, img_w, seg_y_end))
                        children = []
                        if req.show_root_children:
                            root_children = TreeUtils.get_children(workspace.state, None)
                            for child in root_children:
                                center_y = (child.bounds.top + child.bounds.bottom) / 2
                                if seg_y_start <= center_y < seg_y_end:
                                    children.append(child)
                        if children:
                            cropped = paint_annotations(cropped, children, 0, seg_y_start, None, img_w)
                        buf_part = io.BytesIO()
                        cropped.save(buf_part, format="PNG")
                        zf.writestr(f"raw_part{part_idx + 1}.png", buf_part.getvalue())
            else:
                zf.writestr("raw.png", generate_image_bytes("root", workspace, req.show_root_children))
        for item in req.components:
            zf.writestr(f"images/{item.id}.png", generate_image_bytes(item.id, workspace, item.show_children))

    return Response(
        content=buf.getvalue(), media_type="application/zip",
        headers={"Content-Disposition": "attachment; filename=batch_export.zip"}
    )

@router.get("/images/{comp_id}", tags=["Image"])
def get_image(comp_id: str, show_children: bool = False, workspace: WorkspaceManager = Depends(get_workspace)):
    if not workspace.raw_image_bytes:
        raise InvalidStateError("No image in RAM")
    img_bytes = generate_image_bytes(comp_id, workspace, show_children)
    return Response(content=img_bytes, media_type="image/png")
