import uuid
import os
import shutil
from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect, UploadFile, File
from fastapi.responses import FileResponse, JSONResponse
from pydantic import BaseModel
from typing import Optional

from models import WorkspaceState, Component, Bounds, Style, Visibility
from file_io import WorkspaceIO
from .state import WorkspaceManager, get_workspace
from .tree_math import recalculate_tree

router = APIRouter()

# Temporary storage for zip files and images
STORAGE_DIR = os.path.join(os.getcwd(), "data")
os.makedirs(STORAGE_DIR, exist_ok=True)

# ── Import / Export ────────────────────────────────────────────────────

@router.post("/import")
async def import_workspace(file: UploadFile = File(...), workspace: WorkspaceManager = Depends(get_workspace)):
    """Accepts a .zip file, unzips it, and loads the WorkspaceState into memory."""
    if not file.filename.endswith('.zip'):
        raise HTTPException(status_code=400, detail="Must be a .zip file")

    zip_path = os.path.join(STORAGE_DIR, "uploaded.zip")
    with open(zip_path, "wb") as f:
        shutil.copyfileobj(file.file, f)

    extract_dir = os.path.join(STORAGE_DIR, "workspace")
    if os.path.exists(extract_dir):
        shutil.rmtree(extract_dir)

    try:
        new_state, image_path = WorkspaceIO.unpack_workspace(zip_path, extract_dir)
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
    """Accepts a raw image file, clears the workspace, and sets it as the root image."""
    extract_dir = os.path.join(STORAGE_DIR, "workspace")
    os.makedirs(extract_dir, exist_ok=True)
    
    # Save image
    image_filename = file.filename or "screenshot.png"
    image_path = os.path.join(extract_dir, image_filename)
    with open(image_path, "wb") as f:
        shutil.copyfileobj(file.file, f)
        
    def mutate(state: WorkspaceState):
        state.sessionId = uuid.uuid4()
        from models import ImageRef
        state.image = ImageRef(filename=image_filename, originalPath=image_path)
        # Clear components
        state.cutLines = []
        state.rootComponents = []
        state.components = {}
        
    await workspace.mutate(mutate)
    return {"status": "image_imported", "sessionId": workspace.state.sessionId}

@router.get("/export")
async def export_workspace(workspace: WorkspaceManager = Depends(get_workspace)):
    """Packs the current WorkspaceState and image into a .zip file and returns it."""
    if not workspace.state.image or not workspace.state.image.filename:
        raise HTTPException(status_code=400, detail="No image in workspace")

    image_path = os.path.join(STORAGE_DIR, "workspace", workspace.state.image.filename)
    if not os.path.exists(image_path):
        raise HTTPException(status_code=404, detail="Image file not found on disk")

    output_zip = os.path.join(STORAGE_DIR, "export.zip")
    try:
        WorkspaceIO.pack_workspace(workspace.state, image_path, output_zip)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

    return FileResponse(output_zip, media_type="application/zip", filename="annotation_export.zip")

@router.get("/state")
async def get_state(workspace: WorkspaceManager = Depends(get_workspace)):
    """Returns the current WorkspaceState as JSON for the MCP agent to read directly."""
    return workspace.state.model_dump(mode="json")


# ── Image Endpoints ────────────────────────────────────────────────────

@router.get("/image/raw")
async def get_raw_image(workspace: WorkspaceManager = Depends(get_workspace)):
    """Returns the raw unannotated image."""
    if not workspace.state.image or not workspace.state.image.filename:
        raise HTTPException(status_code=404, detail="No image")
        
    image_path = os.path.join(STORAGE_DIR, "workspace", workspace.state.image.filename)
    if not os.path.exists(image_path):
        raise HTTPException(status_code=404, detail="Image file missing")
        
    return FileResponse(image_path)

@router.get("/image/crop/{comp_id}")
async def get_image_crop(comp_id: uuid.UUID, workspace: WorkspaceManager = Depends(get_workspace)):
    """Returns a cropped unannotated image for a specific component."""
    if comp_id not in workspace.state.components:
        raise HTTPException(status_code=404, detail="Component not found")
        
    if not workspace.state.image or not workspace.state.image.filename:
        raise HTTPException(status_code=404, detail="No image")

    image_path = os.path.join(STORAGE_DIR, "workspace", workspace.state.image.filename)
    if not os.path.exists(image_path):
        raise HTTPException(status_code=404, detail="Image file missing")
        
    comp = workspace.state.components[comp_id]
    
    # We use PIL to crop on the fly
    from PIL import Image
    try:
        with Image.open(image_path) as img:
            bounds = comp.absoluteBounds
            cropped = img.crop((bounds.left, bounds.top, bounds.right, bounds.bottom))
            
            crop_path = os.path.join(STORAGE_DIR, f"crop_{comp_id}.png")
            cropped.save(crop_path, "PNG")
            
        return FileResponse(crop_path)
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
