import uuid
import os
import shutil
from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect, UploadFile, File
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
from typing import Optional

from models import WorkspaceState, Component, Bounds, Style, Visibility
from .state import WorkspaceManager, get_workspace
from .tree_math import recalculate_tree

router = APIRouter()



# ── Import / Export ────────────────────────────────────────────────────

@router.post("/import")
async def import_workspace(file: UploadFile = File(...), workspace: WorkspaceManager = Depends(get_workspace)):
    """Accepts a .zip file, unzips it entirely in RAM, and loads the WorkspaceState into memory."""
    if not file.filename.endswith('.zip'):
        raise HTTPException(status_code=400, detail="Must be a .zip file")

    import zipfile
    import io
    import json
    
    file_bytes = await file.read()
    
    try:
        with zipfile.ZipFile(io.BytesIO(file_bytes), 'r') as zf:
            if "workspace.json" not in zf.namelist():
                raise ValueError("Invalid archive: Missing workspace.json")
                
            state_data = json.loads(zf.read("workspace.json").decode('utf-8'))
            new_state = WorkspaceState.model_validate(state_data)
            
            image_filename = new_state.image.filename if new_state.image else None
            if image_filename and image_filename in zf.namelist():
                workspace.raw_image_bytes = zf.read(image_filename)
            else:
                workspace.raw_image_bytes = b""
                
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

    # Replace the global state entirely
    def mutate(state: WorkspaceState):
        state.sessionId = uuid.uuid4() # New session ID forces clients to hard-refresh
        state.screen = new_state.screen
        state.image = new_state.image
        state.cutLines = new_state.cutLines
        state.rootComponents = new_state.rootComponents
        state.components = new_state.components
        recalculate_tree(state)
        
    await workspace.mutate(mutate)
    return {"status": "imported", "sessionId": workspace.state.sessionId}

@router.post("/import/image")
async def import_image(file: UploadFile = File(...), workspace: WorkspaceManager = Depends(get_workspace)):
    """Accepts a raw image file, clears the workspace, and sets it as the root image in RAM."""
    # Read bytes to RAM
    file_bytes = await file.read()
    workspace.raw_image_bytes = file_bytes
    
    image_filename = file.filename or "screenshot.png"
        
    def mutate(state: WorkspaceState):
        state.sessionId = uuid.uuid4()
        from models import ImageRef
        state.image = ImageRef(filename=image_filename, originalPath="")
        # Clear components
        state.cutLines = []
        state.rootComponents = []
        state.components = {}
        
    await workspace.mutate(mutate)
    return {"status": "image_imported", "sessionId": workspace.state.sessionId}

@router.get("/export")
async def export_workspace(workspace: WorkspaceManager = Depends(get_workspace)):
    """Packs the current WorkspaceState and image into a .zip file and returns it from RAM."""
    if not workspace.state.image or not workspace.state.image.filename:
        raise HTTPException(status_code=400, detail="No image in workspace")

    if not workspace.raw_image_bytes:
        raise HTTPException(status_code=400, detail="No image bytes in RAM")

    import zipfile
    import io
    from fastapi.responses import Response
    
    buf = io.BytesIO()
    try:
        with zipfile.ZipFile(buf, 'w', zipfile.ZIP_DEFLATED) as zf:
            state_json = workspace.state.model_dump_json(indent=2)
            zf.writestr("workspace.json", state_json)
            zf.writestr(workspace.state.image.filename, workspace.raw_image_bytes)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return Response(
        content=buf.getvalue(),
        media_type="application/zip",
        headers={"Content-Disposition": "attachment; filename=annotation_export.zip"}
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
        raise HTTPException(status_code=404, detail="No image")
        
    from fastapi.responses import Response
    return Response(content=workspace.raw_image_bytes, media_type="image/png")

@router.get("/image/crop/{comp_id}")
async def get_image_crop(comp_id: uuid.UUID, workspace: WorkspaceManager = Depends(get_workspace)):
    """Returns a cropped unannotated image for a specific component straight from RAM."""
    if comp_id not in workspace.state.components:
        raise HTTPException(status_code=404, detail="Component not found")
        
    if not workspace.raw_image_bytes:
        raise HTTPException(status_code=404, detail="No image in RAM")

    comp = workspace.state.components[comp_id]
    
    # We use PIL to crop on the fly from RAM
    from PIL import Image
    import io
    from fastapi.responses import Response
    try:
        with Image.open(io.BytesIO(workspace.raw_image_bytes)) as img:
            bounds = comp.absoluteBounds
            cropped = img.crop((bounds.left, bounds.top, bounds.right, bounds.bottom))
            
            buf = io.BytesIO()
            cropped.save(buf, format="PNG")
            
        return Response(content=buf.getvalue(), media_type="image/png")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ── WebSockets ─────────────────────────────────────────────────────────

@router.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket, workspace: WorkspaceManager = Depends(get_workspace)):
    """
    Clients connect to receive the full WorkspaceState JSON immediately,
    followed by JSON Patch deltas broadcasted on every mutation.
    Clients do NOT send data here; they use the Semantic REST endpoints below.
    """
    await workspace.connect(websocket)
    try:
        while True:
            _ = await websocket.receive_text()
    except WebSocketDisconnect:
        workspace.disconnect(websocket)


# ── Semantic REST Endpoints ────────────────────────────────────────────

class AddComponentRequest(BaseModel):
    id: Optional[uuid.UUID] = None
    label: str
    parentId: Optional[uuid.UUID] = None
    bounds: Bounds
    style: Optional[Style] = None
    visibility: Optional[Visibility] = None

@router.post("/components")
async def add_component(req: AddComponentRequest, workspace: WorkspaceManager = Depends(get_workspace)):
    comp_id = req.id or uuid.uuid4()
    
    def mutate(state: WorkspaceState):
        if req.parentId and req.parentId not in state.components:
            raise ValueError(f"Parent {req.parentId} not found")
            
        new_comp = Component(
            id=comp_id,
            number="", # Auto-assigned by tree_math
            label=req.label,
            parentId=req.parentId,
            bounds=req.bounds,
            absoluteBounds=req.bounds, # Will be overwritten by tree_math
            style=req.style or Style(),
            visibility=req.visibility or Visibility()
        )
        
        state.components[comp_id] = new_comp
        
        if req.parentId:
            state.components[req.parentId].childrenIds.append(comp_id)
        else:
            state.rootComponents.append(comp_id)
            
        recalculate_tree(state)
        
    try:
        await workspace.mutate(mutate)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
        
    return {"id": comp_id, "status": "added"}


class MoveComponentRequest(BaseModel):
    x: int
    y: int

@router.put("/components/{comp_id}/move")
async def move_component(comp_id: uuid.UUID, req: MoveComponentRequest, workspace: WorkspaceManager = Depends(get_workspace)):
    def mutate(state: WorkspaceState):
        if comp_id not in state.components:
            raise ValueError("Component not found")
        
        comp = state.components[comp_id]
        comp.bounds.x = req.x
        comp.bounds.y = req.y
        
        recalculate_tree(state)

    try:
        await workspace.mutate(mutate)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
        
    return {"status": "moved"}


class UpdateComponentRequest(BaseModel):
    label: Optional[str] = None
    bounds: Optional[Bounds] = None
    parentId: Optional[uuid.UUID] = None # For nesting

@router.put("/components/{comp_id}")
async def update_component(comp_id: uuid.UUID, req: UpdateComponentRequest, workspace: WorkspaceManager = Depends(get_workspace)):
    def mutate(state: WorkspaceState):
        if comp_id not in state.components:
            raise ValueError("Component not found")
            
        comp = state.components[comp_id]
        
        if req.label is not None:
            comp.label = req.label
            
        if req.bounds is not None:
            comp.bounds = req.bounds
            
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
                raise ValueError("New parent not found")

        recalculate_tree(state)

    try:
        await workspace.mutate(mutate)
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
        
    return {"status": "updated"}

@router.delete("/components/{comp_id}")
async def delete_component(comp_id: uuid.UUID, workspace: WorkspaceManager = Depends(get_workspace)):
    def mutate(state: WorkspaceState):
        if comp_id not in state.components:
            raise ValueError("Component not found")
            
        comp = state.components[comp_id]
        
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
        recalculate_tree(state)

    try:
        await workspace.mutate(mutate)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
        
    return {"status": "deleted"}
