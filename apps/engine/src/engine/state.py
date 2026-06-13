import uuid
import jsonpatch
import asyncio
from typing import List, Callable
from fastapi import WebSocket
from models import WorkspaceState

class WorkspaceManager:
    """
    In-memory state manager for the annotation engine.
    Holds the single source of truth WorkspaceState, computes JSON Patches
    upon mutation, and broadcasts them to all connected WebSocket clients.
    """
    def __init__(self):
        self._state = WorkspaceState(sessionId=uuid.uuid4())
        self._clients: List[WebSocket] = []
        self._lock = asyncio.Lock()
        self.raw_image_bytes: bytes = b""

    @property
    def state(self) -> WorkspaceState:
        return self._state

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self._clients.append(websocket)
        # Send the full state immediately upon connection
        await websocket.send_json({
            "type": "full_sync",
            "state": self._state.model_dump(mode="json")
        })

    def disconnect(self, websocket: WebSocket):
        if websocket in self._clients:
            self._clients.remove(websocket)

    async def broadcast_patch(self, patch: list):
        if not patch:
            return
        msg = {
            "type": "patch",
            "revision": self._state.revision,
            "patch": patch
        }
        for client in self._clients:
            try:
                await client.send_json(msg)
            except Exception:
                pass

    async def mutate(self, mutation_fn: Callable[[WorkspaceState], None]):
        """
        Executes a mutation function on the state, automatically computes the
        minimal JSON patch, increments the OCC revision, and broadcasts to clients.
        Uses an asyncio.Lock to ensure thread-safety against concurrent mutations.
        """
        async with self._lock:
            old_dict = self._state.model_dump(mode="json")
            
            # Execute the mutation in-place
            mutation_fn(self._state)
            
            # Increment OCC revision integer
            self._state.revision += 1
            
            new_dict = self._state.model_dump(mode="json")
            
            # Compute exact JSON patch
            patch = jsonpatch.make_patch(old_dict, new_dict).patch
            
            # Broadcast the deltas
            await self.broadcast_patch(patch)

# The global singleton instance injected via FastAPI Depends
workspace_manager = WorkspaceManager()

def get_workspace() -> WorkspaceManager:
    return workspace_manager
