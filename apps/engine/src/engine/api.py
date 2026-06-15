import io
import json
import uuid
import zipfile

import asyncio
from fastapi import (
    APIRouter,
    Depends,
    File,
    HTTPException,
    UploadFile,
    WebSocket,
    WebSocketDisconnect,
)
from fastapi.responses import Response
from models import Bounds, Component, ImageInfo, Style, Visibility, WorkspaceState
from PIL import Image
from pydantic import BaseModel
from tlgp_logger import get_logger

from .exceptions import (
    ComponentNotFoundError,
    InvalidArchiveError,
    InvalidImageError,
    InvalidStateError,
    ParentNotFoundError,
    UndoRedoError,
)
from .state import WorkspaceManager, WorkspaceDep

logger = get_logger(__name__)
router = APIRouter()

class ClientConnection:
    """Wraps a WebSocket to decouple network I/O from state mutation locks via an asyncio.Queue."""
    def __init__(self, websocket: WebSocket, queue: asyncio.Queue[dict]):
        self.websocket = websocket
        self.queue = queue
        self.task = asyncio.create_task(self._worker())
        
    async def _worker(self):
        while True:
            try:
                msg = await self.queue.get()
                await self.websocket.send_json(msg)
                self.queue.task_done()
            except Exception:
                break
                
    def send_msg(self, msg: dict):
        try:
            self.queue.put_nowait(msg)
        except asyncio.QueueFull:
            pass # Drop message if client is too slow to avoid OOM
            
    def cancel(self):
        self.task.cancel()


# ── Import / Export ────────────────────────────────────────────────────


@router.post("/import", tags=["Import/Export"])
async def import_workspace(
    workspace: WorkspaceDep, file: UploadFile = File(...)
):
    """Accepts a .zip file, unzips it entirely in RAM, and loads the WorkspaceState into memory."""
    logger.info("Importing workspace zip file", filename=file.filename)
    if not file.filename.endswith(".zip"):
        raise InvalidArchiveError("Must be a .zip file", filename=file.filename)

    file_bytes = await file.read()

    try:
        with zipfile.ZipFile(io.BytesIO(file_bytes), "r") as zf:
            if "workspace.json" not in zf.namelist():
                raise InvalidArchiveError(
                    "Invalid archive: Missing workspace.json", filename=file.filename
                )

            try:
                state_data = json.loads(zf.read("workspace.json").decode("utf-8"))
                new_state = WorkspaceState.model_validate(state_data)
            except Exception as e:
                raise InvalidArchiveError(
                    f"Failed to parse workspace JSON: {e}",
                    filename=file.filename,
                ) from e

            image_filename = new_state.image.filename if new_state.image else None
            if image_filename and image_filename in zf.namelist():
                workspace.raw_image_bytes = zf.read(image_filename)
            else:
                workspace.raw_image_bytes = b""

    except zipfile.BadZipFile as e:
        raise InvalidArchiveError(f"Bad zip file: {e}", filename=file.filename) from e

    # Replace the global state entirely
    def mutate(state: WorkspaceState):
        from .tree_math import recalculate_tree
        state.sessionId = uuid.uuid4()  # New session ID forces clients to hard-refresh
        state.screen = new_state.screen
        state.image = new_state.image
        state.cutLines = new_state.cutLines
        state.rootComponents = new_state.rootComponents
        state.components = new_state.components
        recalculate_tree(state)

    await workspace.mutate(mutate)
    logger.info(
        "Successfully imported workspace", sessionId=str(workspace.state.sessionId)
    )
    return {"status": "imported", "sessionId": workspace.state.sessionId}


@router.post("/import/image", tags=["Import/Export"])
async def import_image(
    workspace: WorkspaceDep, file: UploadFile = File(...)
):
    """Accepts a raw image file, clears the workspace, and sets it as the root image in RAM."""
    logger.info("Importing raw image file", filename=file.filename)
    # Read bytes to RAM
    file_bytes = await file.read()
    workspace.raw_image_bytes = file_bytes

    try:
        with Image.open(io.BytesIO(file_bytes)) as img:
            width, height = img.width, img.height
    except Exception as e:
        raise InvalidImageError(
            f"Invalid image format: {e}",
            filename=file.filename or "screenshot.png",
        ) from e

    image_filename = file.filename or "screenshot.png"

    def mutate(state: WorkspaceState):
        state.sessionId = uuid.uuid4()
        state.image = ImageInfo(filename=image_filename, width=width, height=height)
        # Clear components
        state.cutLines = []
        state.rootComponents = []
        state.components = {}

    await workspace.mutate(mutate)
    logger.info(
        "Successfully imported raw image", sessionId=str(workspace.state.sessionId)
    )
    return {"status": "image_imported", "sessionId": workspace.state.sessionId}


@router.get("/export")
async def export_workspace(workspace: WorkspaceDep):
    """Packs the current WorkspaceState and image into a .zip file and returns it from RAM."""
    logger.info("Exporting workspace archive", sessionId=str(workspace.state.sessionId))
    if not workspace.state.image or not workspace.state.image.filename:
        raise InvalidStateError(
            "No image in workspace", session_id=str(workspace.state.sessionId)
        )

    if not workspace.raw_image_bytes:
        raise InvalidStateError(
            "No image bytes in RAM", session_id=str(workspace.state.sessionId)
        )

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        state_json = workspace.state.model_dump_json(indent=2)
        zf.writestr("workspace.json", state_json)
        zf.writestr(workspace.state.image.filename, workspace.raw_image_bytes)

    return Response(
        content=buf.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": "attachment; filename=annotation_export.zip"},
    )


@router.get("/state", tags=["State"])
async def get_state(workspace: WorkspaceDep):
    """Returns the current WorkspaceState as JSON for the MCP agent to read directly."""
    return workspace.state.model_dump(mode="json")


# ── Image Endpoints ────────────────────────────────────────────────────


@router.get("/image/raw", tags=["Image"])
async def get_raw_image(workspace: WorkspaceDep):
    """Returns the raw unannotated image straight from RAM."""
    if not workspace.raw_image_bytes:
        raise ComponentNotFoundError(
            "No image in workspace", session_id=str(workspace.state.sessionId)
        )

    return Response(content=workspace.raw_image_bytes, media_type="image/png")


@router.get("/image/crop/{comp_id}", tags=["Image"])
async def get_image_crop(
    comp_id: uuid.UUID, workspace: WorkspaceDep
):
    """Returns a cropped unannotated image for a specific component straight from RAM."""
    if comp_id not in workspace.state.components:
        raise ComponentNotFoundError("Component not found", component_id=str(comp_id))

    if not workspace.raw_image_bytes:
        raise InvalidStateError("No image in RAM", component_id=str(comp_id))

    comp = workspace.state.components[comp_id]

    # We use PIL to crop on the fly from RAM
    with Image.open(io.BytesIO(workspace.raw_image_bytes)) as img:
        bounds = comp.bounds
        cropped = img.crop((bounds.left, bounds.top, bounds.right, bounds.bottom))

        buf = io.BytesIO()
        cropped.save(buf, format="PNG")

    return Response(content=buf.getvalue(), media_type="image/png")


# ── WebSockets ─────────────────────────────────────────────────────────


async def handle_json_rpc(
    method: str, params: dict, workspace: WorkspaceManager
) -> dict:
    if method == "add_component":
        req = AddComponentRequest.model_validate(params)
        comp_id = req.id or uuid.uuid4()
        await workspace.add_component(
            comp_id=comp_id,
            label=req.label,
            bounds=req.bounds,
            parent_id=req.parentId,
            style=req.style,
            visibility=req.visibility,
        )
        return {"id": str(comp_id), "status": "added"}

    elif method == "move_component":
        comp_id_str = params.get("comp_id") or params.get("id")
        if not comp_id_str:
            raise ValueError("Missing 'comp_id' parameter")
        comp_id = uuid.UUID(comp_id_str) if isinstance(comp_id_str, str) else comp_id_str
        req = MoveComponentRequest.model_validate(params)
        await workspace.move_component(comp_id=comp_id, x=req.x, y=req.y)
        return {"status": "moved"}

    elif method == "update_component":
        comp_id_str = params.get("comp_id") or params.get("id")
        if not comp_id_str:
            raise ValueError("Missing 'comp_id' parameter")
        comp_id = uuid.UUID(comp_id_str) if isinstance(comp_id_str, str) else comp_id_str
        req = UpdateComponentRequest.model_validate(params)
        await workspace.update_component(
            comp_id=comp_id,
            label=req.label,
            bounds=req.bounds,
            parent_id=req.parentId,
            style=req.style,
            visibility=req.visibility,
        )
        return {"status": "updated"}

    elif method == "delete_component":
        comp_id_str = params.get("comp_id") or params.get("id")
        if not comp_id_str:
            raise ValueError("Missing 'comp_id' parameter")
        comp_id = uuid.UUID(comp_id_str) if isinstance(comp_id_str, str) else comp_id_str
        await workspace.delete_component(comp_id=comp_id)
        return {"status": "deleted"}

    elif method == "undo":
        success = await workspace.undo()
        if not success:
            raise UndoRedoError("Cannot undo", session_id=str(workspace.state.sessionId))
        return {"status": "undone"}

    elif method == "redo":
        success = await workspace.redo()
        if not success:
            raise UndoRedoError("Cannot redo", session_id=str(workspace.state.sessionId))
        return {"status": "redone"}

    elif method == "update_cut_lines":
        lines = params.get("lines")
        if lines is None:
            raise ValueError("Missing 'lines' parameter")
        await workspace.update_cut_lines(lines=lines)
        return {"status": "updated_cuts"}

    elif method == "update_screen_info":
        name = params.get("name")
        description = params.get("description")
        if name is None or description is None:
            raise ValueError("Missing 'name' or 'description' parameter")
        await workspace.update_screen_info(name=name, description=description)
        return {"status": "updated_screen_info"}

    else:
        raise ValueError(f"Method '{method}' not found")
@router.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket, workspace: WorkspaceDep
):
    """
    Clients connect to receive the full WorkspaceState JSON immediately,
    followed by JSON Patch deltas broadcasted on every mutation.
    Allows executing mutations via JSON-RPC 2.0 messages over the connection.
    """
    logger.info("WebSocket client connected")
    await websocket.accept()
    queue = workspace.connect()
    conn = ClientConnection(websocket, queue)
    try:
        while True:
            data_str = await websocket.receive_text()
            try:
                rpc_req = json.loads(data_str)
            except json.JSONDecodeError as e:
                logger.error("Failed to parse WebSocket text as JSON", error=str(e))
                conn.send_msg(
                    {
                        "jsonrpc": "2.0",
                        "error": {"code": -32700, "message": "Parse error"},
                        "id": None,
                    }
                )
                continue

            if not isinstance(rpc_req, dict) or rpc_req.get("jsonrpc") != "2.0":
                continue

            req_id = rpc_req.get("id")
            method = rpc_req.get("method")
            params = rpc_req.get("params", {})

            try:
                result = await handle_json_rpc(method, params, workspace)
                conn.send_msg(
                    {"jsonrpc": "2.0", "result": result, "id": req_id}
                )
            except Exception as e:
                logger.exception(
                    "Error handling JSON-RPC request", method=method, req_id=req_id
                )
                error_msg = getattr(e, "message", str(e))
                error_details = getattr(e, "details", None)
                conn.send_msg(
                    {
                        "jsonrpc": "2.0",
                        "error": {
                            "code": -32603,
                            "message": error_msg,
                            "data": error_details,
                        },
                        "id": req_id,
                    }
                )
                conn.send_msg(
                    {
                        "type": "full_sync",
                        "state": workspace.state.model_dump(mode="json"),
                    }
                )
    except WebSocketDisconnect:
        logger.info("WebSocket client disconnected")
        conn.cancel()
        workspace.disconnect(queue)


# ── Semantic REST Endpoints ────────────────────────────────────────────


class AddComponentRequest(BaseModel):
    id: uuid.UUID | None = None
    label: str
    parentId: uuid.UUID | None = None
    bounds: Bounds
    style: Style | None = None
    visibility: Visibility | None = None


@router.post("/components", tags=["Components"])
async def add_component(
    req: AddComponentRequest, workspace: WorkspaceDep
):
    comp_id = req.id or uuid.uuid4()
    logger.info("Adding component", comp_id=str(comp_id), label=req.label, parentId=str(req.parentId) if req.parentId else None)
    await workspace.add_component(
        comp_id=comp_id,
        label=req.label,
        bounds=req.bounds,
        parent_id=req.parentId,
        style=req.style,
        visibility=req.visibility,
    )
    return {"id": comp_id, "status": "added"}


class MoveComponentRequest(BaseModel):
    x: int
    y: int


@router.put("/components/{comp_id}/move", tags=["Components"])
async def move_component(
    comp_id: uuid.UUID,
    req: MoveComponentRequest,
    workspace: WorkspaceDep,
):
    logger.info("Moving component", comp_id=str(comp_id), x=req.x, y=req.y)
    await workspace.move_component(comp_id=comp_id, x=req.x, y=req.y)
    return {"status": "moved"}


class UpdateComponentRequest(BaseModel):
    label: str | None = None
    bounds: Bounds | None = None
    parentId: uuid.UUID | None = None  # For nesting
    style: Style | None = None
    visibility: Visibility | None = None


@router.put("/components/{comp_id}", tags=["Components"])
async def update_component(
    comp_id: uuid.UUID,
    req: UpdateComponentRequest,
    workspace: WorkspaceDep,
):
    logger.info("Updating component", comp_id=str(comp_id), label=req.label, parentId=str(req.parentId) if req.parentId else None)
    await workspace.update_component(
        comp_id=comp_id,
        label=req.label,
        bounds=req.bounds,
        parent_id=req.parentId,
        style=req.style,
        visibility=req.visibility,
    )
    return {"status": "updated"}


@router.delete("/components/{comp_id}", tags=["Components"])
async def delete_component(
    comp_id: uuid.UUID, workspace: WorkspaceDep
):
    logger.info("Deleting component", comp_id=str(comp_id))
    await workspace.delete_component(comp_id=comp_id)
    return {"status": "deleted"}


@router.post("/session/undo", tags=["Session"])
async def session_undo(workspace: WorkspaceDep):
    logger.info("Performing undo")
    success = await workspace.undo()
    if not success:
        raise UndoRedoError("Cannot undo", session_id=str(workspace.state.sessionId))
    return {"status": "undone"}


@router.post("/session/redo", tags=["Session"])
async def session_redo(workspace: WorkspaceDep):
    logger.info("Performing redo")
    success = await workspace.redo()
    if not success:
        raise UndoRedoError("Cannot redo", session_id=str(workspace.state.sessionId))
    return {"status": "redone"}
