import asyncio
import uuid
from collections.abc import Callable
from typing import Annotated

import jsonpatch
from fastapi import Depends
from models import Bounds, Component, Style, Visibility, WorkspaceState

from .exceptions import ComponentNotFoundError, InvalidStateError, ParentNotFoundError
from .tree_math import recalculate_tree


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


class WorkspaceManager:
    """
    In-memory state manager for the annotation engine.
    Holds the single source of truth WorkspaceState, computes JSON Patches
    upon mutation, and broadcasts them to all connected listeners via queues.
    """

    def __init__(self):
        self._state = WorkspaceState(sessionId=uuid.uuid4())
        self._listeners: list[asyncio.Queue[dict]] = []
        self._lock = asyncio.Lock()
        self.raw_image_bytes: bytes = b""
        self._history: list[dict] = []
        self._pointer: int = -1
        self._save_history_snapshot()

    @property
    def state(self) -> WorkspaceState:
        return self._state

    def _save_history_snapshot(self):
        # Prune redo history
        if self._pointer < len(self._history) - 1:
            self._history = self._history[: self._pointer + 1]
        self._history.append(self._state.model_dump(mode="json"))
        self._pointer += 1

    def connect(self) -> asyncio.Queue[dict]:
        """Registers a new listener and returns an asyncio.Queue for broadcasting updates."""
        queue: asyncio.Queue[dict] = asyncio.Queue(maxsize=10000)
        self._listeners.append(queue)
        # Send the full state immediately upon connection
        try:
            queue.put_nowait(
                {"type": "full_sync", "state": self._state.model_dump(mode="json")}
            )
        except asyncio.QueueFull:
            pass
        return queue

    def disconnect(self, queue: asyncio.Queue[dict]):
        if queue in self._listeners:
            self._listeners.remove(queue)

    def broadcast_patch(self, patch: list):
        if not patch:
            return
        msg = {"type": "patch", "revision": self._state.revision, "patch": patch}
        for listener_queue in self._listeners:
            try:
                listener_queue.put_nowait(msg)
            except asyncio.QueueFull:
                pass

    async def mutate(self, mutation_fn: Callable[[WorkspaceState], None]):
        """
        Executes a mutation function on the state, automatically computes the
        minimal JSON patch, increments the OCC revision, and broadcasts to clients.
        Uses an asyncio.Lock to ensure thread-safety against concurrent mutations.
        """
        async with self._lock:
            old_dict = self._state.model_dump(mode="json")
            old_session_id = self._state.sessionId

            # Execute the mutation in-place
            mutation_fn(self._state)

            if self._state.sessionId != old_session_id:
                # Clear history for a new session
                self._history = []
                self._pointer = -1
                self._state.revision = 0
                self._save_history_snapshot()

                # Broadcast full sync since sessionId changed
                msg = {
                    "type": "full_sync",
                    "state": self._state.model_dump(mode="json"),
                }
                for listener_queue in list(self._listeners):
                    try:
                        listener_queue.put_nowait(msg)
                    except asyncio.QueueFull:
                        pass
                return

            # Increment OCC revision integer
            self._state.revision += 1

            new_dict = self._state.model_dump(mode="json")

            # Save to history
            self._save_history_snapshot()

            # Compute exact JSON patch
            patch = jsonpatch.make_patch(old_dict, new_dict).patch

            # Broadcast the deltas
            self.broadcast_patch(patch)

    async def undo(self) -> bool:
        async with self._lock:
            if self._pointer > 0:
                old_dict = self._state.model_dump(mode="json")
                self._pointer -= 1
                state_data = self._history[self._pointer]
                self._state = WorkspaceState.model_validate(state_data)
                self._state.revision += 1
                new_dict = self._state.model_dump(mode="json")
                patch = jsonpatch.make_patch(old_dict, new_dict).patch
                self.broadcast_patch(patch)
                return True
            return False

    async def redo(self) -> bool:
        async with self._lock:
            if self._pointer < len(self._history) - 1:
                old_dict = self._state.model_dump(mode="json")
                self._pointer += 1
                state_data = self._history[self._pointer]
                self._state = WorkspaceState.model_validate(state_data)
                self._state.revision += 1
                new_dict = self._state.model_dump(mode="json")
                patch = jsonpatch.make_patch(old_dict, new_dict).patch
                self.broadcast_patch(patch)
                return True
            return False

    # ── Domain Service Methods ─────────────────────────────────────────────

    async def add_component(
        self,
        comp_id: uuid.UUID,
        label: str,
        bounds: Bounds,
        parent_id: uuid.UUID | None = None,
        style: Style | None = None,
        visibility: Visibility | None = None,
    ):
        if not self.state.image:
            raise InvalidStateError("No screenshot/image loaded in workspace")

        def mutate_fn(state: WorkspaceState):
            if parent_id and parent_id not in state.components:
                raise ParentNotFoundError(
                    f"Parent {parent_id} not found",
                    parent_id=str(parent_id),
                    component_id=str(comp_id),
                )
            new_comp = Component(
                id=comp_id,
                number="",  # Auto-assigned by tree_math
                label=label,
                parentId=parent_id,
                bounds=bounds,
                style=style or Style(),
                visibility=visibility or Visibility(),
            )
            state.components[comp_id] = new_comp
            if parent_id:
                state.components[parent_id].childrenIds.append(comp_id)
            else:
                state.rootComponents.append(comp_id)
            recalculate_tree(state, changed_id=comp_id)

        await self.mutate(mutate_fn)

    async def move_component(self, comp_id: uuid.UUID, x: int, y: int):
        if not self.state.image:
            raise InvalidStateError("No screenshot/image loaded in workspace")

        def mutate_fn(state: WorkspaceState):
            if comp_id not in state.components:
                raise ComponentNotFoundError("Component not found", component_id=str(comp_id))
            comp = state.components[comp_id]
            dx = x - comp.bounds.x
            dy = y - comp.bounds.y
            comp.bounds.x = x
            comp.bounds.y = y
            if dx != 0 or dy != 0:
                shift_descendants(state, comp_id, dx, dy)
            recalculate_tree(state, changed_id=comp_id)

        await self.mutate(mutate_fn)

    async def update_component(
        self,
        comp_id: uuid.UUID,
        label: str | None = None,
        bounds: Bounds | None = None,
        parent_id: uuid.UUID | None = None,
        style: Style | None = None,
        visibility: Visibility | None = None,
    ):
        if not self.state.image:
            raise InvalidStateError("No screenshot/image loaded in workspace")

        def mutate_fn(state: WorkspaceState):
            if comp_id not in state.components:
                raise ComponentNotFoundError("Component not found", component_id=str(comp_id))
            
            comp = state.components[comp_id]
            
            if label is not None:
                comp.label = label
            if bounds is not None:
                comp.bounds = bounds
            if style is not None:
                comp.style = style
            if visibility is not None:
                comp.visibility = visibility
            
            if parent_id is not None and parent_id != comp.parentId:
                # Remove from old parent/roots
                if comp.parentId:
                    old_parent = state.components.get(comp.parentId)
                    if old_parent and comp_id in old_parent.childrenIds:
                        old_parent.childrenIds.remove(comp_id)
                else:
                    if comp_id in state.rootComponents:
                        state.rootComponents.remove(comp_id)
                
                # Add to new parent
                comp.parentId = parent_id
                new_parent = state.components.get(parent_id)
                if new_parent:
                    new_parent.childrenIds.append(comp_id)
                else:
                    raise ParentNotFoundError(
                        "New parent not found",
                        component_id=str(comp_id),
                        parent_id=str(parent_id),
                    )
            recalculate_tree(state, changed_id=comp_id)

        await self.mutate(mutate_fn)

    async def delete_component(self, comp_id: uuid.UUID):
        if not self.state.image:
            raise InvalidStateError("No screenshot/image loaded in workspace")

        def mutate_fn(state: WorkspaceState):
            if comp_id not in state.components:
                raise ComponentNotFoundError("Component not found", component_id=str(comp_id))
            
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

        await self.mutate(mutate_fn)

    async def update_cut_lines(self, lines: list[int]):
        if not self.state.image:
            raise InvalidStateError("No screenshot/image loaded in workspace")

        def mutate_fn(state: WorkspaceState):
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

        await self.mutate(mutate_fn)

    async def update_screen_info(self, name: str, description: str):
        if not self.state.image:
            raise InvalidStateError("No screenshot/image loaded in workspace")

        def mutate_fn(state: WorkspaceState):
            state.screen.name = name
            state.screen.description = description

        await self.mutate(mutate_fn)


# The global singleton instance injected via FastAPI Depends
workspace_manager = WorkspaceManager()

def get_workspace() -> WorkspaceManager:
    return workspace_manager

WorkspaceDep = Annotated[WorkspaceManager, Depends(get_workspace)]
