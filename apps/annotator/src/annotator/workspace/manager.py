import io
import threading
import uuid
import zipfile
from collections.abc import Callable

import jsonpatch
from PIL import Image

from annotator.models import (
    Bounds,
    Component,
    ImageInfo,
    ScreenInfo,
    Style,
    Visibility,
    WorkspaceState,
)

from .errors import (
    ComponentNotFoundError,
    InvalidArchiveError,
    InvalidImageError,
    InvalidStateError,
    ParentNotFoundError,
    ReadOnlyError,
)
from .ordering import recalculate_tree


class WorkspaceManager:
    """Manages annotation workspace state with thread-safe mutations and undo/redo.

    Thread safety model:
    - All mutations acquire self._lock and operate on a deep copy of the state.
    - After mutation, the state reference is swapped atomically.
    - Reads (workspace.state) return the current snapshot without locking.
    - Subscribers are called outside the lock with an immutable snapshot.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self._state = WorkspaceState(sessionId=uuid.uuid4())
        self.raw_image_bytes: bytes = b""
        self._history: list[dict] = []
        self._pointer: int = -1
        self._subscribers: list[Callable] = []
        self._save_history_snapshot(self._state.model_dump(mode="json"))

    @property
    def state(self) -> WorkspaceState:
        """Returns the current state snapshot. Safe to read from any thread."""
        return self._state

    def subscribe(self, callback: Callable[[list[dict], WorkspaceState], None]):
        """Register for mutation notifications.
        Callback receives (json_patch_ops, new_state_snapshot).
        Called after every successful mutation, outside the lock.
        """
        self._subscribers.append(callback)

    def _save_history_snapshot(self, dump: dict):
        if self._pointer < len(self._history) - 1:
            self._history = self._history[: self._pointer + 1]
        self._history.append(dump)
        self._pointer += 1

    def mutate(self, fn, force=False):
        """Apply a mutation function to a deep copy of the state.
        Swaps the state reference atomically after mutation.
        Subscribers are notified outside the lock.
        """
        with self._lock:
            if self._state.readOnly and not force:
                raise ReadOnlyError("Workspace is read-only", session_id=str(self._state.sessionId))

            old_state = self._state
            old_dump = old_state.model_dump(mode="json")
            old_session_id = old_state.sessionId

            new_state = old_state.model_copy(deep=True)
            fn(new_state)

            if new_state.sessionId != old_session_id:
                self._history = []
                self._pointer = -1
                new_state.revision = 0
                new_dump = new_state.model_dump(mode="json")
                self._state = new_state
                self._save_history_snapshot(new_dump)
                patch = [{"op": "replace", "path": "", "value": new_dump}]
            else:
                new_state.revision += 1
                self._state = new_state  # Atomic reference swap
                new_dump = new_state.model_dump(mode="json")
                self._save_history_snapshot(new_dump)
                patch = jsonpatch.make_patch(old_dump, new_dump).patch

        # Notify outside lock — subscribers handle their own threading
        for cb in list(self._subscribers):
            cb(patch, new_state)

    def _shift_descendants(self, state: WorkspaceState, comp_id: uuid.UUID, dx: int, dy: int):
        comp = state.components.get(comp_id)
        if not comp:
            return
        for child_id in comp.childrenIds:
            child = state.components.get(child_id)
            if child:
                child.bounds.x += dx
                child.bounds.y += dy
                self._shift_descendants(state, child_id, dx, dy)

    # ── Domain Service Methods ─────────────────────────────────────────────

    def add_component(
        self,
        comp_id: uuid.UUID,
        label: str,
        bounds: dict | Bounds,
        parent_id: uuid.UUID | None = None,
        style: Style | None = None,
        visibility: Visibility | None = None,
    ):
        if not self.state.image:
            raise InvalidStateError("No screenshot/image loaded in workspace")

        def mutation(state: WorkspaceState):
            if parent_id and parent_id not in state.components:
                raise ParentNotFoundError(
                    f"Parent {parent_id} not found",
                    parent_id=str(parent_id),
                    component_id=str(comp_id),
                )
            new_comp = Component(
                id=comp_id,
                number="",  # Auto-assigned
                label=label,
                parentId=parent_id,
                bounds=bounds if isinstance(bounds, Bounds) else Bounds(**bounds),
                style=style or Style(),
                visibility=visibility or Visibility(),
            )
            state.components[comp_id] = new_comp
            if parent_id:
                state.components[parent_id].childrenIds.append(comp_id)
            else:
                state.rootComponents.append(comp_id)
            recalculate_tree(state, changed_id=comp_id)

        self.mutate(mutation)

    def move_component(self, comp_id: uuid.UUID, x: int, y: int):
        if not self.state.image:
            raise InvalidStateError("No screenshot/image loaded in workspace")

        def mutation(state: WorkspaceState):
            if comp_id not in state.components:
                raise ComponentNotFoundError("Component not found", component_id=str(comp_id))
            comp = state.components[comp_id]
            dx = x - comp.bounds.x
            dy = y - comp.bounds.y
            comp.bounds.x = x
            comp.bounds.y = y
            if dx != 0 or dy != 0:
                self._shift_descendants(state, comp_id, dx, dy)
            recalculate_tree(state, changed_id=comp_id)

        self.mutate(mutation)

    def update_component(
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

        def mutation(state: WorkspaceState):
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
                if comp.parentId:
                    old_parent = state.components.get(comp.parentId)
                    if old_parent and comp_id in old_parent.childrenIds:
                        old_parent.childrenIds.remove(comp_id)
                else:
                    if comp_id in state.rootComponents:
                        state.rootComponents.remove(comp_id)

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

        self.mutate(mutation)

    def delete_component(self, comp_id: uuid.UUID):
        if not self.state.image:
            raise InvalidStateError("No screenshot/image loaded in workspace")

        def mutation(state: WorkspaceState):
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

        self.mutate(mutation)

    def update_cut_lines(self, lines: list[int]):
        if not self.state.image:
            raise InvalidStateError("No screenshot/image loaded in workspace")

        def mutation(state: WorkspaceState):
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

        self.mutate(mutation)

    def update_screen_info(self, name: str, description: str):
        if not self.state.image:
            raise InvalidStateError("No screenshot/image loaded in workspace")

        def mutation(state: WorkspaceState):
            state.screen.name = name
            state.screen.description = description

        self.mutate(mutation)

    def clear_workspace(self, force: bool = False):
        def mutation(state: WorkspaceState):
            state.sessionId = uuid.uuid4()
            state.image = None
            state.screen = ScreenInfo()
            state.cutLines = []
            state.rootComponents = []
            state.components = {}
            state.readOnly = False
        with self._lock:
            self.raw_image_bytes = b""
        self.mutate(mutation, force=force)

    def undo(self, force: bool = False) -> bool:
        with self._lock:
            if self._state.readOnly and not force:
                raise ReadOnlyError("Workspace is read-only", session_id=str(self._state.sessionId))
            if self._pointer > 0:
                old_dump = self._state.model_dump(mode="json")
                self._pointer -= 1
                state_data = self._history[self._pointer]
                self._state = WorkspaceState.model_validate(state_data)
                self._state.revision += 1
                new_dump = self._state.model_dump(mode="json")
                self._history[self._pointer] = new_dump # Keep updated
                patch = jsonpatch.make_patch(old_dump, new_dump).patch
                new_state = self._state
            else:
                return False

        for cb in list(self._subscribers):
            cb(patch, new_state)
        return True

    def redo(self, force: bool = False) -> bool:
        with self._lock:
            if self._state.readOnly and not force:
                raise ReadOnlyError("Workspace is read-only", session_id=str(self._state.sessionId))
            if self._pointer < len(self._history) - 1:
                old_dump = self._state.model_dump(mode="json")
                self._pointer += 1
                state_data = self._history[self._pointer]
                self._state = WorkspaceState.model_validate(state_data)
                self._state.revision += 1
                new_dump = self._state.model_dump(mode="json")
                self._history[self._pointer] = new_dump
                patch = jsonpatch.make_patch(old_dump, new_dump).patch
                new_state = self._state
            else:
                return False

        for cb in list(self._subscribers):
            cb(patch, new_state)
        return True

    def import_zip(self, file_bytes: bytes):
        import json  # noqa: PLC0415
        with zipfile.ZipFile(io.BytesIO(file_bytes), "r") as zf:
            if "workspace.json" not in zf.namelist():
                raise InvalidArchiveError("Invalid archive: Missing workspace.json")

            try:
                state_data = json.loads(zf.read("workspace.json").decode("utf-8"))
                new_state = WorkspaceState.model_validate(state_data)
            except Exception as e:
                raise InvalidArchiveError(f"Failed to parse workspace JSON: {e}") from e

            image_filename = new_state.image.filename if new_state.image else None
            if image_filename and image_filename in zf.namelist():
                with self._lock:
                    self.raw_image_bytes = zf.read(image_filename)
            else:
                with self._lock:
                    self.raw_image_bytes = b""

        def mutation(state: WorkspaceState):
            state.sessionId = uuid.uuid4()
            state.screen = new_state.screen
            state.image = new_state.image
            state.cutLines = new_state.cutLines
            state.rootComponents = new_state.rootComponents
            state.components = new_state.components
            recalculate_tree(state)

        self.mutate(mutation, force=True)

    def import_image(self, file_bytes: bytes, filename: str = "screenshot.png"):
        with self._lock:
            self.raw_image_bytes = file_bytes

        try:
            with Image.open(io.BytesIO(file_bytes)) as img:
                width, height = img.width, img.height
        except Exception as e:
            raise InvalidImageError(f"Invalid image format: {e}", filename=filename) from e

        def mutation(state: WorkspaceState):
            state.sessionId = uuid.uuid4()
            state.image = ImageInfo(filename=filename, width=width, height=height)
            state.cutLines = []
            state.rootComponents = []
            state.components = {}

        self.mutate(mutation, force=True)

    def export_zip(self) -> bytes:
        with self._lock:
            state_snapshot = self._state.model_copy(deep=True)
            image_bytes = self.raw_image_bytes

        if not state_snapshot.image or not state_snapshot.image.filename:
            raise InvalidStateError("No image in workspace")

        if not image_bytes:
            raise InvalidStateError("No image bytes in RAM")

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            state_json = state_snapshot.model_dump_json(indent=2)
            zf.writestr("workspace.json", state_json)
            zf.writestr(state_snapshot.image.filename, image_bytes)

        return buf.getvalue()
