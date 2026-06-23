"""FastAPI routes and WebSocket broadcaster for the Annotator API.

Routes are async and delegate sync workspace calls via asyncio.to_thread().
The WebSocketBroadcaster bridges sync workspace mutations to async WS clients.
"""

from __future__ import annotations

import asyncio
import io
import json
import threading
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
    File,
    Request,
    UploadFile,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.responses import Response
from PIL import Image
from pydantic import BaseModel

# ── WebSocket Broadcaster ─────────────────────────────────────────────


class WebSocketBroadcaster:
    """Subscriber that bridges sync workspace mutations to async WS clients.

    Thread-safe: uses loop.call_soon_threadsafe() for cross-thread event posting.
    """

    def __init__(self, loop: asyncio.AbstractEventLoop):
        self._loop = loop
        self._clients: list[asyncio.Queue] = []
        self._clients_lock = threading.Lock()

    def broadcast_sync(self, patch: list[dict], new_state: WorkspaceState):
        """Called by WorkspaceManager on any mutation (from any thread)."""
        if self._loop.is_closed():
            return

        if patch and patch[0].get("op") == "replace" and patch[0].get("path") == "":
            msg = {"type": "full_sync", "state": patch[0]["value"]}
        else:
            msg = {"type": "patch", "revision": new_state.revision, "patch": patch}

        with self._clients_lock:
            clients = list(self._clients)
        for q in clients:
            self._loop.call_soon_threadsafe(q.put_nowait, msg)

    def connect(self) -> asyncio.Queue:
        """Register a new WS client and return its message queue."""
        q: asyncio.Queue = asyncio.Queue(maxsize=64)
        with self._clients_lock:
            self._clients.append(q)
        return q

    def disconnect(self, q: asyncio.Queue):
        """Unregister a WS client queue."""
        with self._clients_lock:
            if q in self._clients:
                self._clients.remove(q)


# ── Dependency ─────────────────────────────────────────────────────────


def get_workspace(request: Request) -> WorkspaceManager:
    """FastAPI dependency that retrieves the workspace from app state."""
    return request.app.state.workspace


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


# ── JSON-RPC Handler ──────────────────────────────────────────────────


def handle_json_rpc(method: str, params: dict, workspace: WorkspaceManager) -> dict:
    """Dispatch a JSON-RPC method call to the workspace."""
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


# ── Image Generation ──────────────────────────────────────────────────


def generate_image_bytes(
    comp_id: str | uuid.UUID,
    workspace: WorkspaceManager,
    show_children: bool = False,
) -> bytes:
    """Generate a PNG image for a component or the root screenshot."""
    if comp_id == "root":
        bounds_left, bounds_top = 0, 0
        bounds_right, bounds_bottom = workspace.state.image.width, workspace.state.image.height
        parent_comp = None
        children = TreeUtils.get_children(workspace.state, None) if show_children else []
        offset_x, offset_y = 0, 0
    else:
        comp_uuid = comp_id if isinstance(comp_id, uuid.UUID) else uuid.UUID(comp_id)
        if comp_uuid not in workspace.state.components:
            raise ComponentNotFoundError("Component not found", component_id=str(comp_uuid))
        comp = workspace.state.components[comp_uuid]
        bounds = comp.bounds
        bounds_left, bounds_top = bounds.left, bounds.top
        bounds_right, bounds_bottom = bounds.right, bounds.bottom
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


# ── Router Factory ────────────────────────────────────────────────────


def create_router(
    workspace: WorkspaceManager,
    server_loop: asyncio.AbstractEventLoop,
) -> tuple[APIRouter, WebSocketBroadcaster]:
    """Create the API router and broadcaster.

    Returns:
        (router, broadcaster) tuple. The caller must subscribe
        the broadcaster to the workspace.
    """
    router = APIRouter()
    broadcaster = WebSocketBroadcaster(server_loop)

    # ── WebSocket ──────────────────────────────────────────────────

    @router.websocket("/ws")
    async def websocket_endpoint(websocket: WebSocket):
        await websocket.accept()
        queue = broadcaster.connect()
        try:
            # Send initial full state
            await websocket.send_json({
                "type": "full_sync",
                "state": workspace.state.model_dump(mode="json"),
            })

            # Process incoming JSON-RPC + relay outgoing broadcasts
            import asyncio as _asyncio  # noqa: PLC0415

            async def relay_broadcasts():
                while True:
                    msg = await queue.get()
                    await websocket.send_json(msg)

            async def process_rpc():
                while True:
                    data_str = await websocket.receive_text()
                    try:
                        rpc_req = json.loads(data_str)
                        if not isinstance(rpc_req, dict) or rpc_req.get("jsonrpc") != "2.0":
                            continue
                        req_id = rpc_req.get("id")
                        method = rpc_req.get("method")
                        params = rpc_req.get("params", {})

                        result = await asyncio.to_thread(handle_json_rpc, method, params, workspace)
                        await websocket.send_json({"jsonrpc": "2.0", "result": result, "id": req_id})

                    except Exception as e:
                        error_msg = getattr(e, "message", str(e))
                        await websocket.send_json({
                            "jsonrpc": "2.0",
                            "error": {"code": -32603, "message": error_msg},
                            "id": rpc_req.get("id") if "rpc_req" in dir() and isinstance(rpc_req, dict) else None,
                        })

            # Run both tasks concurrently; cancel on disconnect
            relay_task = _asyncio.create_task(relay_broadcasts())
            try:
                await process_rpc()
            finally:
                relay_task.cancel()

        except WebSocketDisconnect:
            pass
        finally:
            broadcaster.disconnect(queue)

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
        await asyncio.to_thread(workspace.import_image, file_bytes, file.filename or "screenshot.png")
        return {"status": "image_imported", "sessionId": workspace.state.sessionId}

    @router.get("/workspace/export")
    async def export_workspace():
        zip_bytes = await asyncio.to_thread(workspace.export_zip)
        return Response(
            content=zip_bytes,
            media_type="application/zip",
            headers={"Content-Disposition": "attachment; filename=annotation_export.zip"},
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
            raise UndoRedoError("Cannot undo", session_id=str(workspace.state.sessionId))
        return {"status": "undone"}

    @router.post("/session/redo", tags=["Session"])
    async def session_redo():
        success = await asyncio.to_thread(workspace.redo)
        if not success:
            raise UndoRedoError("Cannot redo", session_id=str(workspace.state.sessionId))
        return {"status": "redone"}

    # ── Image Endpoints ────────────────────────────────────────────

    @router.get("/images/{comp_id}", tags=["Image"])
    async def get_image(comp_id: str, show_children: bool = False):
        if not workspace.raw_image_bytes:
            raise InvalidStateError("No image in RAM")
        img_bytes = await asyncio.to_thread(generate_image_bytes, comp_id, workspace, show_children)
        return Response(content=img_bytes, media_type="image/png")

    @router.post("/workspace/export-batch", tags=["Import/Export"])
    async def export_batch(req: BatchExportRequest):
        if not workspace.raw_image_bytes:
            raise InvalidStateError("No image in RAM", session_id=str(workspace.state.sessionId))

        def _build_batch_zip() -> bytes:
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
            return buf.getvalue()

        zip_content = await asyncio.to_thread(_build_batch_zip)
        return Response(
            content=zip_content,
            media_type="application/zip",
            headers={"Content-Disposition": "attachment; filename=batch_export.zip"},
        )

    return router, broadcaster
