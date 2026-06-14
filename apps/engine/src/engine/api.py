import io
import json
import uuid
import zipfile

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
from .state import WorkspaceManager, get_workspace
from .tree_math import recalculate_tree

logger = get_logger(__name__)
router = APIRouter()


def shift_descendants(state: WorkspaceState, comp_id: uuid.UUID, dx: int, dy: int):
    comp = state.components.get(comp_id)
    if not comp:
        return
    for child_id in comp.childrenIds:
        child = state.components.get(child_id)
        if child:
            child.bounds.x += dx
            child.bounds.y += dy
            shift_descendants(state, child_id, dx, dy)


# ── Import / Export ────────────────────────────────────────────────────


@router.post("/import")
async def import_workspace(
    file: UploadFile = File(...), workspace: WorkspaceManager = Depends(get_workspace)
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


@router.post("/import/image")
async def import_image(
    file: UploadFile = File(...), workspace: WorkspaceManager = Depends(get_workspace)
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
async def export_workspace(workspace: WorkspaceManager = Depends(get_workspace)):
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


@router.get("/state")
async def get_state(workspace: WorkspaceManager = Depends(get_workspace)):
    """Returns the current WorkspaceState as JSON for the MCP agent to read directly."""
    return workspace.state.model_dump(mode="json")


# ── Image Endpoints ────────────────────────────────────────────────────


@router.get("/image/raw")
async def get_raw_image(workspace: WorkspaceManager = Depends(get_workspace)):
    """Returns the raw unannotated image straight from RAM."""
    if not workspace.raw_image_bytes:
        raise ComponentNotFoundError(
            "No image in workspace", session_id=str(workspace.state.sessionId)
        )

    return Response(content=workspace.raw_image_bytes, media_type="image/png")


@router.get("/image/crop/{comp_id}")
async def get_image_crop(
    comp_id: uuid.UUID, workspace: WorkspaceManager = Depends(get_workspace)
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
        if not workspace.state.image:
            raise InvalidStateError("No screenshot/image loaded in workspace")
        comp_id = req.id or uuid.uuid4()

        def mutate(state: WorkspaceState):
            if req.parentId and req.parentId not in state.components:
                raise ParentNotFoundError(
                    f"Parent {req.parentId} not found",
                    parent_id=str(req.parentId),
                    component_id=str(comp_id),
                )
            new_comp = Component(
                id=comp_id,
                number="",  # Auto-assigned by tree_math
                label=req.label,
                parentId=req.parentId,
                bounds=req.bounds,
                style=req.style or Style(),
                visibility=req.visibility or Visibility(),
            )
            state.components[comp_id] = new_comp
            if req.parentId:
                state.components[req.parentId].childrenIds.append(comp_id)
            else:
                state.rootComponents.append(comp_id)
            recalculate_tree(state, changed_id=comp_id)

        await workspace.mutate(mutate)
        return {"id": str(comp_id), "status": "added"}

    elif method == "move_component":
        comp_id_str = params.get("comp_id") or params.get("id")
        if not comp_id_str:
            raise ValueError("Missing 'comp_id' parameter")
        comp_id = (
            uuid.UUID(comp_id_str) if isinstance(comp_id_str, str) else comp_id_str
        )
        req = MoveComponentRequest.model_validate(params)
        if not workspace.state.image:
            raise InvalidStateError("No screenshot/image loaded in workspace")

        def mutate(state: WorkspaceState):
            if comp_id not in state.components:
                raise ComponentNotFoundError(
                    "Component not found", component_id=str(comp_id)
                )
            comp = state.components[comp_id]
            dx = req.x - comp.bounds.x
            dy = req.y - comp.bounds.y
            comp.bounds.x = req.x
            comp.bounds.y = req.y
            if dx != 0 or dy != 0:
                shift_descendants(state, comp_id, dx, dy)
            recalculate_tree(state, changed_id=comp_id)

        await workspace.mutate(mutate)
        return {"status": "moved"}

    elif method == "update_component":
        comp_id_str = params.get("comp_id") or params.get("id")
        if not comp_id_str:
            raise ValueError("Missing 'comp_id' parameter")
        comp_id = (
            uuid.UUID(comp_id_str) if isinstance(comp_id_str, str) else comp_id_str
        )
        req = UpdateComponentRequest.model_validate(params)
        if not workspace.state.image:
            raise InvalidStateError("No screenshot/image loaded in workspace")

        def mutate(state: WorkspaceState):
            if comp_id not in state.components:
                raise ComponentNotFoundError(
                    "Component not found", component_id=str(comp_id)
                )
            comp = state.components[comp_id]
            if req.label is not None:
                comp.label = req.label
            if req.bounds is not None:
                comp.bounds = req.bounds
            if req.style is not None:
                comp.style = req.style
            if req.visibility is not None:
                comp.visibility = req.visibility
            if req.parentId is not None and req.parentId != comp.parentId:
                # Remove from old parent/roots
                if comp.parentId:
                    old_parent = state.components.get(comp.parentId)
                    if old_parent and comp_id in old_parent.childrenIds:
                        old_parent.childrenIds.remove(comp_id)
                else:
                    if comp_id in state.rootComponents:
                        state.rootComponents.remove(comp_id)
                # Add to new parent
                comp.parentId = req.parentId
                new_parent = state.components.get(req.parentId)
                if new_parent:
                    new_parent.childrenIds.append(comp_id)
                else:
                    raise ParentNotFoundError(
                        "New parent not found",
                        component_id=str(comp_id),
                        parent_id=str(req.parentId),
                    )
            recalculate_tree(state, changed_id=comp_id)

        await workspace.mutate(mutate)
        return {"status": "updated"}

    elif method == "delete_component":
        comp_id_str = params.get("comp_id") or params.get("id")
        if not comp_id_str:
            raise ValueError("Missing 'comp_id' parameter")
        comp_id = (
            uuid.UUID(comp_id_str) if isinstance(comp_id_str, str) else comp_id_str
        )
        if not workspace.state.image:
            raise InvalidStateError("No screenshot/image loaded in workspace")

        def mutate(state: WorkspaceState):
            if comp_id not in state.components:
                raise ComponentNotFoundError(
                    "Component not found", component_id=str(comp_id)
                )
            comp = state.components[comp_id]
            parent_id = comp.parentId
            if comp.parentId:
                parent = state.components.get(comp.parentId)
                if parent and comp_id in parent.childrenIds:
                    parent.childrenIds.remove(comp_id)
            else:
                if comp_id in state.rootComponents:
                    state.rootComponents.remove(comp_id)

            def delete_recursive(cid: uuid.UUID):
                c = state.components.get(cid)
                if c:
                    for child_id in list(c.childrenIds):
                        delete_recursive(child_id)
                    del state.components[cid]

            delete_recursive(comp_id)
            recalculate_tree(state, changed_id=parent_id if parent_id else "roots")

        await workspace.mutate(mutate)
        return {"status": "deleted"}

    elif method == "undo":
        if not workspace.state.image:
            raise InvalidStateError("No screenshot/image loaded in workspace")
        success = await workspace.undo()
        if not success:
            raise UndoRedoError(
                "Cannot undo", session_id=str(workspace.state.sessionId)
            )
        return {"status": "undone"}

    elif method == "redo":
        if not workspace.state.image:
            raise InvalidStateError("No screenshot/image loaded in workspace")
        success = await workspace.redo()
        if not success:
            raise UndoRedoError(
                "Cannot redo", session_id=str(workspace.state.sessionId)
            )
        return {"status": "redone"}

    elif method == "update_cut_lines":
        lines = params.get("lines")
        if lines is None:
            raise ValueError("Missing 'lines' parameter")
        if not workspace.state.image:
            raise InvalidStateError("No screenshot/image loaded in workspace")

        def mutate(state: WorkspaceState):
            for cut in lines:
                for comp in state.components.values():
                    if comp.bounds.top <= cut <= comp.bounds.bottom:
                        raise InvalidStateError(
                            f"Cut line at Y={cut} intersects component '{comp.label}' bounds",
                            component_id=str(comp.id),
                            cut_y=cut,
                        )
            state.cutLines = sorted(lines)
            recalculate_tree(state)

        await workspace.mutate(mutate)
        return {"status": "updated_cuts"}

    elif method == "update_screen_info":
        name = params.get("name")
        description = params.get("description")
        if name is None or description is None:
            raise ValueError("Missing 'name' or 'description' parameter")
        if not workspace.state.image:
            raise InvalidStateError("No screenshot/image loaded in workspace")

        def mutate(state: WorkspaceState):
            state.screen.name = name
            state.screen.description = description

        await workspace.mutate(mutate)
        return {"status": "updated_screen_info"}

    else:
        raise ValueError(f"Method '{method}' not found")


@router.websocket("/ws")
async def websocket_endpoint(
    websocket: WebSocket, workspace: WorkspaceManager = Depends(get_workspace)
):
    """
    Clients connect to receive the full WorkspaceState JSON immediately,
    followed by JSON Patch deltas broadcasted on every mutation.
    Allows executing mutations via JSON-RPC 2.0 messages over the connection.
    """
    logger.info("WebSocket client connected")
    await workspace.connect(websocket)
    try:
        while True:
            data_str = await websocket.receive_text()
            try:
                rpc_req = json.loads(data_str)
            except json.JSONDecodeError as e:
                logger.error("Failed to parse WebSocket text as JSON", error=str(e))
                await websocket.send_json(
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
                await websocket.send_json(
                    {"jsonrpc": "2.0", "result": result, "id": req_id}
                )
            except Exception as e:
                logger.exception(
                    "Error handling JSON-RPC request", method=method, req_id=req_id
                )
                error_msg = getattr(e, "message", str(e))
                error_details = getattr(e, "details", None)
                await websocket.send_json(
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
                await websocket.send_json(
                    {
                        "type": "full_sync",
                        "state": workspace.state.model_dump(mode="json"),
                    }
                )
    except WebSocketDisconnect:
        logger.info("WebSocket client disconnected")
        workspace.disconnect(websocket)


# ── Semantic REST Endpoints ────────────────────────────────────────────


class AddComponentRequest(BaseModel):
    id: uuid.UUID | None = None
    label: str
    parentId: uuid.UUID | None = None
    bounds: Bounds
    style: Style | None = None
    visibility: Visibility | None = None


@router.post("/components")
async def add_component(
    req: AddComponentRequest, workspace: WorkspaceManager = Depends(get_workspace)
):
    if not workspace.state.image:
        raise HTTPException(
            status_code=422, detail="No screenshot/image loaded in workspace"
        )
    comp_id = req.id or uuid.uuid4()
    logger.info(
        "Adding component",
        comp_id=str(comp_id),
        label=req.label,
        parentId=str(req.parentId) if req.parentId else None,
    )

    def mutate(state: WorkspaceState):
        if req.parentId and req.parentId not in state.components:
            raise ParentNotFoundError(
                f"Parent {req.parentId} not found",
                parent_id=str(req.parentId),
                component_id=str(comp_id),
            )

        new_comp = Component(
            id=comp_id,
            number="",  # Auto-assigned by tree_math
            label=req.label,
            parentId=req.parentId,
            bounds=req.bounds,
            style=req.style or Style(),
            visibility=req.visibility or Visibility(),
        )

        state.components[comp_id] = new_comp

        if req.parentId:
            state.components[req.parentId].childrenIds.append(comp_id)
        else:
            state.rootComponents.append(comp_id)

        recalculate_tree(state, changed_id=comp_id)

    await workspace.mutate(mutate)
    return {"id": comp_id, "status": "added"}


class MoveComponentRequest(BaseModel):
    x: int
    y: int


@router.put("/components/{comp_id}/move")
async def move_component(
    comp_id: uuid.UUID,
    req: MoveComponentRequest,
    workspace: WorkspaceManager = Depends(get_workspace),
):
    if not workspace.state.image:
        raise HTTPException(
            status_code=422, detail="No screenshot/image loaded in workspace"
        )
    logger.info("Moving component", comp_id=str(comp_id), x=req.x, y=req.y)

    def mutate(state: WorkspaceState):
        if comp_id not in state.components:
            raise ComponentNotFoundError(
                "Component not found", component_id=str(comp_id)
            )

        comp = state.components[comp_id]
        dx = req.x - comp.bounds.x
        dy = req.y - comp.bounds.y
        comp.bounds.x = req.x
        comp.bounds.y = req.y
        if dx != 0 or dy != 0:
            shift_descendants(state, comp_id, dx, dy)

        recalculate_tree(state, changed_id=comp_id)

    await workspace.mutate(mutate)
    return {"status": "moved"}


class UpdateComponentRequest(BaseModel):
    label: str | None = None
    bounds: Bounds | None = None
    parentId: uuid.UUID | None = None  # For nesting
    style: Style | None = None
    visibility: Visibility | None = None


@router.put("/components/{comp_id}")
async def update_component(
    comp_id: uuid.UUID,
    req: UpdateComponentRequest,
    workspace: WorkspaceManager = Depends(get_workspace),
):
    if not workspace.state.image:
        raise HTTPException(
            status_code=422, detail="No screenshot/image loaded in workspace"
        )
    logger.info(
        "Updating component",
        comp_id=str(comp_id),
        label=req.label,
        parentId=str(req.parentId) if req.parentId else None,
    )

    def mutate(state: WorkspaceState):
        if comp_id not in state.components:
            raise ComponentNotFoundError(
                "Component not found", component_id=str(comp_id)
            )

        comp = state.components[comp_id]

        if req.label is not None:
            comp.label = req.label

        if req.bounds is not None:
            comp.bounds = req.bounds

        if req.style is not None:
            comp.style = req.style
        if req.visibility is not None:
            comp.visibility = req.visibility
        if req.parentId is not None and req.parentId != comp.parentId:
            # Remove from old parent/roots
            if comp.parentId:
                old_parent = state.components.get(comp.parentId)
                if old_parent and comp_id in old_parent.childrenIds:
                    old_parent.childrenIds.remove(comp_id)
            else:
                if comp_id in state.rootComponents:
                    state.rootComponents.remove(comp_id)

            # Add to new parent
            comp.parentId = req.parentId
            new_parent = state.components.get(req.parentId)
            if new_parent:
                new_parent.childrenIds.append(comp_id)
            else:
                raise ParentNotFoundError(
                    "New parent not found",
                    component_id=str(comp_id),
                    parent_id=str(req.parentId),
                )

        recalculate_tree(state, changed_id=comp_id)

    await workspace.mutate(mutate)
    return {"status": "updated"}


@router.delete("/components/{comp_id}")
async def delete_component(
    comp_id: uuid.UUID, workspace: WorkspaceManager = Depends(get_workspace)
):
    if not workspace.state.image:
        raise HTTPException(
            status_code=422, detail="No screenshot/image loaded in workspace"
        )
    logger.info("Deleting component", comp_id=str(comp_id))

    def mutate(state: WorkspaceState):
        if comp_id not in state.components:
            raise ComponentNotFoundError(
                "Component not found", component_id=str(comp_id)
            )

        comp = state.components[comp_id]
        parent_id = comp.parentId

        # Remove from parent or roots
        if comp.parentId:
            parent = state.components.get(comp.parentId)
            if parent and comp_id in parent.childrenIds:
                parent.childrenIds.remove(comp_id)
        else:
            if comp_id in state.rootComponents:
                state.rootComponents.remove(comp_id)

        # Cascading delete
        def delete_recursive(cid: uuid.UUID):
            c = state.components.get(cid)
            if c:
                for child_id in list(c.childrenIds):
                    delete_recursive(child_id)
                del state.components[cid]

        delete_recursive(comp_id)
        recalculate_tree(state, changed_id=parent_id if parent_id else "roots")

    await workspace.mutate(mutate)
    return {"status": "deleted"}


@router.post("/session/undo")
async def session_undo(workspace: WorkspaceManager = Depends(get_workspace)):
    if not workspace.state.image:
        raise HTTPException(
            status_code=422, detail="No screenshot/image loaded in workspace"
        )
    logger.info("Performing undo")
    success = await workspace.undo()
    if not success:
        raise UndoRedoError("Cannot undo", session_id=str(workspace.state.sessionId))
    return {"status": "undone"}


@router.post("/session/redo")
async def session_redo(workspace: WorkspaceManager = Depends(get_workspace)):
    if not workspace.state.image:
        raise HTTPException(
            status_code=422, detail="No screenshot/image loaded in workspace"
        )
    logger.info("Performing redo")
    success = await workspace.redo()
    if not success:
        raise UndoRedoError("Cannot redo", session_id=str(workspace.state.sessionId))
    return {"status": "redone"}
