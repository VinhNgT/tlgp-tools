"""Core workspace state manager and monolithic entrypoint for mutating annotation state."""

import io
import json
import re
import threading
import uuid
import zipfile
from collections.abc import Callable, Generator
from typing import Any, Literal, TypedDict

import jsonpatch
from PIL import Image
from tlgp_contracts import TreeUtils

from annotator.models import (
    Bounds,
    Component,
    ImageInfo,
    ScreenInfo,
    Style,
    WorkspaceState,
)
from annotator.rendering import paint_annotations

from .errors import (
    ComponentNotFoundError,
    InvalidArchiveError,
    InvalidImageError,
    InvalidStateError,
    ParentNotFoundError,
    ReadOnlyError,
)
from .ordering import ROOTS_CHANGED, recalculate_tree
from .validation import MIN_CUT_GAP, CutValidator


class ExportNode(TypedDict):
    is_leaf: bool
    bounds: tuple[int, int, int, int]
    children: list[Component]
    parent_comp: Component | None
    filename: str
    comp_id: uuid.UUID | None


class WorkspaceManager:
    """Manages annotation workspace state with thread-safe mutations and undo/redo.

    Thread safety model:
    - All mutations acquire self._lock and operate on a deep copy of the state.
    - After mutation, the state reference is swapped atomically.
    - Reads (workspace.state) return the current snapshot without locking.
    - Subscribers are called outside the lock with an immutable snapshot.
    """

    MAX_HISTORY_SIZE = 100

    def __init__(self):
        self._lock = threading.Lock()
        self._state = WorkspaceState(workspaceId=uuid.uuid4())

        # Raw screenshot bytes kept in-memory for export_zip() and API image
        # generation. This is one of three image representations held
        # simultaneously (raw bytes, decoded PIL Image in the canvas, and
        # QPixmap for Qt rendering). Each serves a distinct purpose and
        # cannot be eliminated without fundamentally changing the pipeline.
        self.raw_image_bytes: bytes = b""

        # Patch-based undo/redo. Each entry is a (reverse_patch, forward_patch)
        # tuple computed via jsonpatch, excluding the revision counter.
        self._undo_stack: list[tuple[list, list]] = []
        self._redo_stack: list[tuple[list, list]] = []

        self._subscribers: list[Callable] = []

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

    @staticmethod
    def _strip_revision(dump: dict) -> dict:
        """Return a copy of the state dump without the revision counter.

        Undo/redo patches must be independent of the monotonically-increasing
        revision field so that patches can be replayed regardless of how many
        times the user undoes/redoes.
        """
        return {k: v for k, v in dump.items() if k != "revision"}

    def mutate(self, fn, force=False):
        """Apply a mutation function to a deep copy of the state.

        Swaps the state reference atomically after mutation.
        Subscribers are notified outside the lock.
        """
        with self._lock:
            if self._state.readOnly and not force:
                raise ReadOnlyError(
                    "Workspace is read-only", workspace_id=str(self._state.workspaceId)
                )

            old_state = self._state
            old_dump = old_state.model_dump(mode="json")
            old_workspace_id = old_state.workspaceId

            new_state = old_state.model_copy(deep=True)
            fn(new_state)

            if new_state.workspaceId != old_workspace_id:
                self._undo_stack.clear()
                self._redo_stack.clear()
                new_state.revision = 0
                self._state = new_state
                new_dump = new_state.model_dump(mode="json")
                patch = [{"op": "replace", "path": "", "value": new_dump}]
            else:
                new_state.revision += 1
                self._state = new_state  # Atomic reference swap
                new_dump = new_state.model_dump(mode="json")

                # Store revision-independent patches for undo/redo
                old_content = self._strip_revision(old_dump)
                new_content = self._strip_revision(new_dump)
                fwd = jsonpatch.make_patch(old_content, new_content).patch
                rev = jsonpatch.make_patch(new_content, old_content).patch
                if fwd:
                    self._undo_stack.append((rev, fwd))
                    self._redo_stack.clear()
                    if len(self._undo_stack) > self.MAX_HISTORY_SIZE:
                        self._undo_stack.pop(0)

                patch = jsonpatch.make_patch(old_dump, new_dump).patch

        # Notify outside lock — subscribers handle their own threading
        for cb in list(self._subscribers):
            cb(patch, new_state)

    def _shift_descendants(
        self, state: WorkspaceState, comp_id: uuid.UUID, dx: int, dy: int
    ):
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
            )
            state.components[comp_id] = new_comp
            if parent_id:
                state.components[parent_id].childrenIds.append(comp_id)
            else:
                state.rootComponents.append(comp_id)
            recalculate_tree(state, changed_id=comp_id)

            intersecting_cut = CutValidator.get_intersecting_cut(
                new_comp.bounds, state.cutLines
            )
            if intersecting_cut is not None:
                raise InvalidStateError(
                    f"Component '{new_comp.label}' intersects existing cut line at Y={intersecting_cut}",
                    component_id=str(comp_id),
                    cut_y=intersecting_cut,
                )

        self.mutate(mutation)

    def move_component(self, comp_id: uuid.UUID, x: int, y: int):
        if not self.state.image:
            raise InvalidStateError("No screenshot/image loaded in workspace")

        def mutation(state: WorkspaceState):
            if comp_id not in state.components:
                raise ComponentNotFoundError(
                    "Component not found", component_id=str(comp_id)
                )
            comp = state.components[comp_id]
            dx = x - comp.bounds.x
            dy = y - comp.bounds.y
            comp.bounds.x = x
            comp.bounds.y = y
            if dx != 0 or dy != 0:
                self._shift_descendants(state, comp_id, dx, dy)
            recalculate_tree(state, changed_id=comp_id)

            descendants = []

            def collect_descendants(c_id: uuid.UUID):
                descendants.append(c_id)
                comp = state.components.get(c_id)
                if comp:
                    for child_id in comp.childrenIds:
                        collect_descendants(child_id)

            collect_descendants(comp_id)

            for cid in descendants:
                c = state.components[cid]
                intersecting_cut = CutValidator.get_intersecting_cut(
                    c.bounds, state.cutLines
                )
                if intersecting_cut is not None:
                    raise InvalidStateError(
                        f"Component '{c.label}' intersects existing cut line at Y={intersecting_cut}",
                        component_id=str(cid),
                        cut_y=intersecting_cut,
                    )

        self.mutate(mutation)

    def move_components(self, moves: dict[uuid.UUID, tuple[int, int]]):
        if not self.state.image:
            raise InvalidStateError("No screenshot/image loaded in workspace")

        def mutation(state: WorkspaceState):
            all_descendants = set()
            for comp_id, (x, y) in moves.items():
                if comp_id not in state.components:
                    raise ComponentNotFoundError(
                        "Component not found", component_id=str(comp_id)
                    )
                comp = state.components[comp_id]
                dx = x - comp.bounds.x
                dy = y - comp.bounds.y
                comp.bounds.x = x
                comp.bounds.y = y
                if dx != 0 or dy != 0:
                    self._shift_descendants(state, comp_id, dx, dy)
                recalculate_tree(state, changed_id=comp_id)

                def collect_descendants(c_id: uuid.UUID):
                    all_descendants.add(c_id)
                    comp = state.components.get(c_id)
                    if comp:
                        for child_id in comp.childrenIds:
                            collect_descendants(child_id)

                collect_descendants(comp_id)

            for cid in all_descendants:
                c = state.components[cid]
                intersecting_cut = CutValidator.get_intersecting_cut(
                    c.bounds, state.cutLines
                )
                if intersecting_cut is not None:
                    raise InvalidStateError(
                        f"Component '{c.label}' intersects existing cut line at Y={intersecting_cut}",
                        component_id=str(cid),
                        cut_y=intersecting_cut,
                    )

        self.mutate(mutation)

    def update_component(
        self,
        comp_id: uuid.UUID,
        label: str | None = None,
        bounds: Bounds | None = None,
        parent_id: uuid.UUID | None = None,
        style: Style | None = None,
    ):
        if not self.state.image:
            raise InvalidStateError("No screenshot/image loaded in workspace")

        def mutation(state: WorkspaceState):
            if comp_id not in state.components:
                raise ComponentNotFoundError(
                    "Component not found", component_id=str(comp_id)
                )

            comp = state.components[comp_id]

            if label is not None:
                comp.label = label
            if bounds is not None:
                comp.bounds = bounds
            if style is not None:
                comp.style = style

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

            if bounds is not None:
                intersecting_cut = CutValidator.get_intersecting_cut(
                    comp.bounds, state.cutLines
                )
                if intersecting_cut is not None:
                    raise InvalidStateError(
                        f"Component '{comp.label}' intersects existing cut line at Y={intersecting_cut}",
                        component_id=str(comp_id),
                        cut_y=intersecting_cut,
                    )

        self.mutate(mutation)

    def delete_component(self, comp_id: uuid.UUID):
        if not self.state.image:
            raise InvalidStateError("No screenshot/image loaded in workspace")

        def mutation(state: WorkspaceState):
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
            recalculate_tree(
                state, changed_id=parent_id if parent_id else ROOTS_CHANGED
            )

        self.mutate(mutation)

    def update_cut_lines(self, lines: list[int]):
        if not self.state.image:
            raise InvalidStateError("No screenshot/image loaded in workspace")

        CutValidator.validate_cut_lines(lines, self.state.image.height, MIN_CUT_GAP)

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
            state.workspaceId = uuid.uuid4()
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
                raise ReadOnlyError(
                    "Workspace is read-only", workspace_id=str(self._state.workspaceId)
                )
            if not self._undo_stack:
                return False

            old_dump = self._state.model_dump(mode="json")
            entry = self._undo_stack.pop()

            # Apply reverse patch to content (excluding revision)
            old_content = self._strip_revision(old_dump)
            restored_content = jsonpatch.apply_patch(old_content, entry[0])
            restored_content["revision"] = old_dump["revision"] + 1

            self._state = WorkspaceState.model_validate(restored_content)
            new_dump = self._state.model_dump(mode="json")
            self._redo_stack.append(entry)

            patch = jsonpatch.make_patch(old_dump, new_dump).patch
            new_state = self._state

        for cb in list(self._subscribers):
            cb(patch, new_state)
        return True

    def redo(self, force: bool = False) -> bool:
        with self._lock:
            if self._state.readOnly and not force:
                raise ReadOnlyError(
                    "Workspace is read-only", workspace_id=str(self._state.workspaceId)
                )
            if not self._redo_stack:
                return False

            old_dump = self._state.model_dump(mode="json")
            entry = self._redo_stack.pop()

            # Apply forward patch to content (excluding revision)
            old_content = self._strip_revision(old_dump)
            restored_content = jsonpatch.apply_patch(old_content, entry[1])
            restored_content["revision"] = old_dump["revision"] + 1

            self._state = WorkspaceState.model_validate(restored_content)
            new_dump = self._state.model_dump(mode="json")
            self._undo_stack.append(entry)

            patch = jsonpatch.make_patch(old_dump, new_dump).patch
            new_state = self._state

        for cb in list(self._subscribers):
            cb(patch, new_state)
        return True

    def import_zip(self, file_bytes: bytes):

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
            state.workspaceId = uuid.uuid4()
            state.screen = new_state.screen
            state.image = new_state.image
            state.cutLines = new_state.cutLines
            state.rootComponents = new_state.rootComponents
            state.components = new_state.components
            recalculate_tree(state)

        self.mutate(mutation, force=True)

    def import_image(self, file_bytes: bytes, filename: str = "screenshot.png"):
        # Validate image BEFORE committing bytes to prevent storing corrupt
        # data that would be served by export_zip() or image endpoints.
        try:
            with Image.open(io.BytesIO(file_bytes)) as img:
                width, height = img.width, img.height
        except Exception as e:
            raise InvalidImageError(
                f"Invalid image format: {e}", filename=filename
            ) from e

        with self._lock:
            self.raw_image_bytes = file_bytes

        def mutation(state: WorkspaceState):
            state.workspaceId = uuid.uuid4()
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
            # Strip folder paths to just get the file name (handle both \ and /)
            base_filename = state_snapshot.image.filename.replace('\\', '/').split('/')[-1]
            state_snapshot.image.filename = base_filename
            state_json = state_snapshot.model_dump_json(indent=2)
            zf.writestr("workspace.json", state_json)
            zf.writestr(base_filename, image_bytes)

        return buf.getvalue()

    def get_default_export_name(self, mode: Literal["annotated", "raw", "both"]) -> str:
        """Get the default filename (without extension) for exporting images, using the mode."""
        with self._lock:
            state_snapshot = self._state.model_copy(deep=True)
        raw_filename = (
            state_snapshot.image.filename
            if (state_snapshot.image and state_snapshot.image.filename)
            else "exported_images"
        )
        if "." in raw_filename:
            base_name = raw_filename.rsplit(".", 1)[0]
        else:
            base_name = raw_filename

        folder_name = re.sub(r'[\\/*?:"<>|]', "_", base_name).strip()
        if not folder_name:
            folder_name = "exported_images"
        return f"{folder_name}_{mode}"

    def _write_img_to_zip(
        self, zf: zipfile.ZipFile, img: Image.Image, archive_path: str
    ):
        img_buf = io.BytesIO()
        img.save(img_buf, format="PNG")
        zf.writestr(archive_path, img_buf.getvalue())

    def _update_export_mapping(
        self,
        mapping: dict,
        comp_id: uuid.UUID | None,
        archive_path: str,
        mode: str,
        submode: str,
    ):
        target_map = mapping[submode] if mode == "both" else mapping
        if comp_id is None:
            target_map["root"].append(archive_path)
        else:
            target_map["components"][str(comp_id)] = archive_path

    def _export_node_annotated(
        self,
        img: Image.Image,
        node: ExportNode,
        state_snapshot: WorkspaceState,
        zf: zipfile.ZipFile,
        mapping: dict,
        mode: str,
    ) -> bool:
        if node["is_leaf"]:
            return False
        assert state_snapshot.image is not None
        cropped_ann = img.crop(node["bounds"])
        if node["children"]:
            cropped_ann = paint_annotations(
                img=cropped_ann,
                children=node["children"],
                offset_x=node["bounds"][0],
                offset_y=node["bounds"][1],
                parent_comp=node["parent_comp"],
                full_img_width=state_snapshot.image.width,
            )
        archive_path = (
            f"annotated/{node['filename']}" if mode == "both" else node["filename"]
        )
        self._write_img_to_zip(zf, cropped_ann, archive_path)
        self._update_export_mapping(
            mapping, node["comp_id"], archive_path, mode, "annotated"
        )
        return True

    def _export_node_raw(
        self,
        img: Image.Image,
        node: ExportNode,
        zf: zipfile.ZipFile,
        mapping: dict,
        mode: str,
    ) -> bool:
        cropped_raw = img.crop(node["bounds"])
        archive_path = f"raw/{node['filename']}" if mode == "both" else node["filename"]
        self._write_img_to_zip(zf, cropped_raw, archive_path)
        self._update_export_mapping(mapping, node["comp_id"], archive_path, mode, "raw")
        return True

    def export_images(self, mode: Literal["annotated", "raw", "both"]) -> bytes:
        """Export component cropped images as a ZIP file.

        - annotated: Crop non-leaf components and draw children on them. Won't export leaves.
        - raw: Crop all components. Do not draw children. Includes leaves.
        - both: Export both options into separate subdirectories (annotated/ and raw/).
        """
        with self._lock:
            state_snapshot = self._state.model_copy(deep=True)
            image_bytes = self.raw_image_bytes

        if not state_snapshot.image or not state_snapshot.image.filename:
            raise InvalidStateError("No image in workspace")

        if not image_bytes:
            raise InvalidStateError("No image bytes in RAM")

        def sanitize_filename(name: str) -> str:
            # Replace invalid filename characters with underscores
            cleaned = re.sub(r'[\\/*?:"<>|]', "_", name)
            return cleaned.strip()

        buf = io.BytesIO()
        with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
            with Image.open(io.BytesIO(image_bytes)) as img:

                def get_export_nodes() -> Generator[ExportNode]:
                    # Yield root node(s) — split by cut lines into segments
                    root_children = TreeUtils.get_children(state_snapshot, None)
                    root_base = (
                        state_snapshot.image.filename.rsplit(".", 1)[0]
                        if state_snapshot.image.filename
                        else "root"
                    )
                    img_w = state_snapshot.image.width
                    img_h = state_snapshot.image.height
                    cuts = sorted(state_snapshot.cutLines)
                    boundaries = [0, *cuts, img_h]
                    segments = [
                        (boundaries[i], boundaries[i + 1])
                        for i in range(len(boundaries) - 1)
                    ]

                    if len(segments) <= 1:
                        # No cuts: single root node (original behavior)
                        yield {
                            "is_leaf": False,  # Root is a screen crop, always export
                            "bounds": (0, 0, img_w, img_h),
                            "children": root_children,
                            "parent_comp": None,
                            "filename": f"root_{sanitize_filename(root_base)}.png",
                            "comp_id": None,
                        }
                    else:
                        # Yield one root segment per cut-delimited strip
                        for seg_idx, (seg_start, seg_end) in enumerate(segments):
                            seg_children = [
                                c
                                for c in root_children
                                if c.bounds.top >= seg_start
                                and c.bounds.bottom <= seg_end
                            ]
                            yield {
                                "is_leaf": False,  # Root segment is a screen crop, always export
                                "bounds": (0, seg_start, img_w, seg_end),
                                "children": seg_children,
                                "parent_comp": None,
                                "filename": f"root_{sanitize_filename(root_base)}_segment_{seg_idx + 1}.png",
                                "comp_id": None,
                            }

                    # Yield component nodes
                    for comp_id, comp in state_snapshot.components.items():
                        children = TreeUtils.get_children(state_snapshot, comp_id)
                        name_parts = []
                        if comp.number:
                            name_parts.append(sanitize_filename(comp.number))
                        if comp.label:
                            name_parts.append(sanitize_filename(comp.label))
                        name_parts.append(comp.id.hex[:8])

                        yield {
                            "is_leaf": len(children) == 0,
                            "bounds": (
                                comp.bounds.left,
                                comp.bounds.top,
                                comp.bounds.right,
                                comp.bounds.bottom,
                            ),
                            "children": children,
                            "parent_comp": comp,
                            "filename": f"{'_'.join(name_parts)}.png",
                            "comp_id": comp_id,
                        }

                mapping: dict[str, Any] = {}
                if mode == "both":
                    mapping["annotated"] = {"root": [], "components": {}}
                    mapping["raw"] = {"root": [], "components": {}}
                else:
                    mapping["root"] = []
                    mapping["components"] = {}

                exported_count = 0
                for node in get_export_nodes():
                    if mode in ("annotated", "both"):
                        if self._export_node_annotated(
                            img, node, state_snapshot, zf, mapping, mode
                        ):
                            exported_count += 1

                    if mode in ("raw", "both"):
                        if self._export_node_raw(img, node, zf, mapping, mode):
                            exported_count += 1

                if exported_count == 0:
                    raise InvalidStateError(
                        "No images to export under the selected mode (e.g. no annotations found)."
                    )

                # Write self-describing mapping.json to ZIP root
                zf.writestr("mapping.json", json.dumps(mapping, indent=2))

        return buf.getvalue()
