import io
import uuid
from concurrent.futures import ThreadPoolExecutor
from uuid import UUID

from PIL import Image
from PySide6.QtCore import QObject, QTimer, Signal, Slot
from tlgp_logger import get_logger

from annotator.models import Bounds, Component, Style, Visibility
from annotator.workspace import WorkspaceManager

from .app import MainAppWindow
from .dialog_service import DialogService
from .state import UIStateStore

logger = get_logger(__name__)


class _MainThreadInvoker(QObject):
    """Thread-safe bridge for posting callables from worker threads to the main thread."""

    _call = Signal(object)

    def __init__(self, parent=None):
        super().__init__(parent)
        self._call.connect(self._execute)

    def invoke(self, fn):
        """Emit fn to be executed on the main thread."""
        self._call.emit(fn)

    @Slot(object)
    def _execute(self, fn):
        fn()


class AppController:
    """Coordinates events between the workspace manager, observable state store, and passive views."""

    def __init__(
        self,
        workspace: WorkspaceManager,
        store: UIStateStore,
        view: MainAppWindow,
        dialog_service: DialogService,
    ):
        self.workspace = workspace
        self.store = store
        self.view = view
        self.dialog_service = dialog_service
        self._loaded_session_id = None
        self.pending_created_ids: set[UUID] = set()
        self._io_pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="annotator-io")
        self._invoker = _MainThreadInvoker(self.view)

        # Observable state subscriptions
        self.store.subscribe("workspace", self._on_workspace_updated)
        self.store.subscribe("selection", self._on_selection_updated)
        self.store.subscribe("viewport", self._on_viewport_updated)

        # Bind passive view callbacks
        self._bind_view_callbacks()

        # Handle initial state sync
        self._apply_state_sync()

    def _bind_view_callbacks(self):
        # App layout window callbacks
        self.view.on_mode_change_request = self._on_mode_change_request
        self.view.on_undo_request = self._on_undo_request
        self.view.on_redo_request = self._on_redo_request
        self.view.on_delete_request = self._on_delete_request
        self.view.on_back_request = self._on_back_request
        self.view.on_import_zip_request = self._on_import_zip_request
        self.view.on_import_image_request = self._on_import_image_request
        self.view.on_export_zip_request = self._on_export_zip_request
        self.view.on_open_cut_editor_request = self._on_open_cut_editor_request
        self.view.on_open_screen_info_request = self._on_open_screen_info_request
        self.view.on_enter_pressed = self._on_enter_pressed
        self.view.on_escape_pressed = self._on_escape_pressed
        self.view.on_arrow_key_pressed = self._on_arrow_key_pressed

        # Canvas callbacks
        self.view.canvas.on_import_zip = self._on_import_zip_request
        self.view.canvas.on_import_image = self._on_import_image_request
        self.view.canvas.on_drill_into = self._on_canvas_drill_into
        self.view.canvas.on_drill_out = self._on_canvas_drill_out
        self.view.canvas.on_component_moved = self._on_component_moved
        self.view.canvas.on_component_resized = self._on_component_resized
        self.view.canvas.on_component_created = self._on_component_created
        self.view.canvas.on_request_context_menu = self._on_canvas_context_menu

        # Canvas decoupled store request callbacks
        self.view.canvas.on_viewport_change_request = (
            self._on_canvas_viewport_change_request
        )
        self.view.canvas.on_active_interaction_changed = (
            self._on_canvas_active_interaction_changed
        )
        self.view.canvas.on_selection_ids_changed = (
            self._on_canvas_selection_ids_changed
        )
        self.view.canvas.on_viewport_size_changed = (
            self._on_canvas_viewport_size_changed
        )
        self.view.canvas.on_canvas_mode_change_request = self._on_mode_change_request

        # Sidebar callbacks
        self.view.tree.on_component_selected = self._on_tree_component_selected
        self.view.tree.on_context_menu_request = self._on_sidebar_context_menu
        self.view.tree.on_rename_request = self._on_sidebar_rename_request

        # Properties callback
        self.view.properties.on_property_changed = self._on_property_changed
        self.view.properties.on_focus_changed = self._on_properties_focus_changed

    def _global_error_handler(self, exc, val, tb):
        logger.exception("Unhandled GUI exception", exc_info=(exc, val, tb))
        self.dialog_service.show_error(
            self.view,
            "Unhandled Error",
            f"An unexpected error occurred:\n{val}",
        )

    def _show_async_error(self, message: str):
        self.store.update_state("selection", active_interaction=None)
        self.dialog_service.show_error(self.view, "Error", message)

    def _apply_state_sync(self):
        state = self.workspace.state
        if not state:
            return

        self.view.update_status(
            f"Local workspace | Session: {state.sessionId}",
            is_error=False,
        )

        current_session_id = str(state.sessionId) if state.sessionId else None
        if self._loaded_session_id is not None and current_session_id != self._loaded_session_id:
            self.store.update_state("selection", selected_component_ids=[], active_interaction=None)
            self.store.update_state("viewport", parent_stack=[], zoom_factor=1.0, pan_offset=(0.0, 0.0))

        if state.image:
            if (
                current_session_id != self._loaded_session_id
                or self.view.canvas.full_pil_img is None
            ):
                try:
                    img = Image.open(io.BytesIO(self.workspace.raw_image_bytes))
                    self.view.set_canvas_image(img)
                    self._loaded_session_id = current_session_id
                    self.view.canvas.fit_to_screen()
                    QTimer.singleShot(100, self.check_trigger_screen_info)
                except Exception as e:
                    logger.exception("Failed to load raw background image")
                    self.dialog_service.show_error(
                        self.view,
                        "Error",
                        f"Failed to load background image: {e}",
                    )
        else:
            self.view.set_canvas_image(None)
            self._loaded_session_id = current_session_id

        # Check and remove synchronized transient overrides from active_interaction
        active_interaction = self.store.state.active_interaction
        if active_interaction and not self.view.canvas.gestures.is_dragging:
            active_interaction = dict(active_interaction)
            to_remove = []
            for comp_id, transient_bounds in active_interaction.items():
                comp = state.components.get(comp_id)
                if not comp:
                    to_remove.append(comp_id)
                    continue
                cb = comp.bounds
                if (
                    cb.x == transient_bounds.x
                    and cb.y == transient_bounds.y
                    and cb.w == transient_bounds.w
                    and cb.h == transient_bounds.h
                ):
                    to_remove.append(comp_id)

            for comp_id in to_remove:
                active_interaction.pop(comp_id, None)

            if not active_interaction:
                active_interaction = None

        # Re-resolve selection bounds with updated components list
        canvas_sel = self.store.state.selected_component_ids
        for uid in list(self.pending_created_ids):
            if uid in state.components:
                self.pending_created_ids.remove(uid)
        updated_sel = [
            uid
            for uid in canvas_sel
            if uid in state.components or uid in self.pending_created_ids
        ]
        self.store.update_state("selection", selected_component_ids=updated_sel)

        # Notify workspace state observers
        self.store.update_state(
            "workspace", workspace_state=state, active_interaction=active_interaction
        )

        # Sync visual navigation controls
        self._sync_breadcrumbs()

    def _on_workspace_updated(self):
        nodes = self._build_tree_nodes()
        self.view.tree.rebuild_tree(nodes)
        self._sync_properties()
        self.view.canvas.set_workspace_state(
            self.store.state.workspace_state,
            self.store.state.active_interaction,
        )

    def _is_effectively_visible(self, comp_id: UUID) -> bool:
        state = self.store.state.workspace_state
        if not state:
            return True
        comp = state.components.get(comp_id)
        if not comp:
            return True
        if not comp.visibility.visible:
            return False
        if comp.parentId:
            return self._is_effectively_visible(comp.parentId)
        return True

    def _is_effectively_locked(self, comp_id: UUID) -> bool:
        state = self.store.state.workspace_state
        if not state:
            return False
        comp = state.components.get(comp_id)
        if not comp:
            return False
        if comp.visibility.locked:
            return True
        if comp.parentId:
            return self._is_effectively_locked(comp.parentId)
        return False

    def _build_tree_nodes(self) -> list[dict]:
        state = self.store.state.workspace_state
        if not state:
            return []

        def build_node(comp_uuid: UUID, parent_visible: bool = True, parent_locked: bool = False) -> dict | None:
            comp = state.components.get(comp_uuid)
            if not comp:
                return None

            comp_id_str = str(comp.id)
            node_text = f"{comp.number} {comp.label}" if comp.number else comp.label

            comp_visible = comp.visibility.visible
            comp_locked = comp.visibility.locked

            is_effectively_visible = comp_visible and parent_visible
            is_effectively_locked = comp_locked or parent_locked

            tags = []
            if not is_effectively_visible:
                tags.append("hidden")
            if is_effectively_locked:
                tags.append("locked")

            children = []
            for child_uuid in comp.childrenIds:
                child_node = build_node(child_uuid, is_effectively_visible, is_effectively_locked)
                if child_node:
                    children.append(child_node)

            return {
                "id": comp_id_str,
                "text": node_text,
                "label": comp.label,
                "tags": tags,
                "children": children,
            }

        root_nodes = []
        for root_uuid in state.rootComponents:
            node = build_node(root_uuid)
            if node:
                root_nodes.append(node)
        return root_nodes

    def _on_selection_updated(self):
        self._sync_properties()
        selected_ids = self.store.state.selected_component_ids
        if selected_ids:
            self.view.tree.select_component(selected_ids[-1])
        else:
            self.view.tree.clear_selection()
        self.view.canvas.set_selection_state(
            self.store.state.selected_component_ids,
            self.store.state.active_interaction,
        )

    def _on_viewport_updated(self):
        st = self.store.state
        self._sync_breadcrumbs()
        self.view.update_zoom_display(st.zoom_factor)
        self.view.canvas.set_viewport_state(
            zoom_factor=st.zoom_factor,
            pan_offset=st.pan_offset,
            parent_stack=st.parent_stack,
            current_mode=st.current_mode,
            active_interaction=st.active_interaction,
        )

    def _sync_breadcrumbs(self):
        parent_stack = self.store.state.parent_stack
        state = self.store.state.workspace_state
        breadcrumbs = []
        if parent_stack and state:
            for comp_id in parent_stack:
                comp = state.components.get(comp_id)
                if comp:
                    breadcrumbs.append(str(comp.number) if comp.number else comp.label)
        self.view.update_breadcrumbs(breadcrumbs)

    def _sync_properties(self):
        selected_ids = self.store.state.selected_component_ids
        state = self.store.state.workspace_state
        active_interaction = self.store.state.active_interaction

        if len(selected_ids) == 1 and state:
            comp_id = selected_ids[0]
            comp = state.components.get(comp_id)
            if comp:
                bounds = comp.bounds
                if active_interaction and comp_id in active_interaction:
                    bounds = active_interaction[comp_id]

                prev_box_id = self.view.properties._selected_box_id  # noqa: SLF001
                current_box_id = str(comp.id)
                box_changed = prev_box_id != current_box_id

                self.view.properties.update_properties_panel(
                    box_id=current_box_id,
                    label=comp.label,
                    x=int(bounds.x),
                    y=int(bounds.y),
                    w=int(bounds.w),
                    h=int(bounds.h),
                    is_visible=comp.visibility.visible,
                    is_locked=comp.visibility.locked,
                    is_effectively_locked=self._is_effectively_locked(comp.id),
                    pill_corner=comp.style.pillCorner,
                )
                if box_changed or not self.view.properties.is_field_focused("name"):
                    self.view.properties.update_field_value("name", comp.label)
                for key in ["x", "y", "w", "h"]:
                    if box_changed or not self.view.properties.is_field_focused(key):
                        val = getattr(bounds, key, 0)
                        self.view.properties.update_field_value(key, str(int(val)))
                return
        self.view.properties.disable_properties_fields()

    def check_trigger_screen_info(self):
        state = self.store.state.workspace_state
        if state and state.image:
            screen_name = getattr(state.screen, "name", "")
            if not screen_name:
                self._on_open_screen_info_request()

    def get_ancestor_chain(self, comp_id: UUID) -> list[UUID]:
        state = self.store.state.workspace_state
        if not state:
            return []
        chain = []
        curr_id = comp_id
        visited = set()
        while curr_id:
            if curr_id in visited:
                break
            visited.add(curr_id)
            comp = state.components.get(curr_id)
            if not comp or not comp.parentId:
                break
            chain.append(comp.parentId)
            curr_id = comp.parentId
        chain.reverse()
        return chain

    # ── View Callback Handlers ──────────────────────────────────────────

    def _on_mode_change_request(self, mode: str):
        self.store.update_state("selection", active_interaction=None)
        self.store.update_state("viewport", current_mode=mode)

    def _on_undo_request(self):
        if self.view.canvas.full_pil_img:
            self.store.update_state("selection", active_interaction=None)
            self.workspace.undo()

    def _on_redo_request(self):
        if self.view.canvas.full_pil_img:
            self.store.update_state("selection", active_interaction=None)
            self.workspace.redo()

    def _on_delete_request(self, event=None):
        if self.store.state.text_focused:
            return
        if not self.view.canvas.full_pil_img:
            return
        self.store.update_state("selection", active_interaction=None)
        selected_ids = self.store.state.selected_component_ids
        if selected_ids:
            for comp_id in list(selected_ids):
                self.workspace.delete_component(comp_id)
            self.store.update_state("selection", selected_component_ids=[])

    def _on_sidebar_context_menu(self, comp_id: UUID, x_root: int, y_root: int):
        state = self.store.state.workspace_state
        if not state:
            return
        comp = state.components.get(comp_id)
        if not comp:
            return

        is_visible = comp.visibility.visible
        is_locked = comp.visibility.locked

        def toggle_visible():
            self.workspace.update_component(comp_id, visibility=Visibility(visible=not is_visible, locked=is_locked))

        def toggle_lock():
            self.workspace.update_component(comp_id, visibility=Visibility(visible=is_visible, locked=not is_locked))

        def delete_comp():
            self.workspace.delete_component(comp_id)

        actions = [
            {"label": "Hide" if is_visible else "Show", "command": toggle_visible},
            {"label": "Unlock" if is_locked else "Lock", "command": toggle_lock},
            {"separator": True},
            {"label": "Delete", "command": delete_comp},
        ]
        self.view.show_context_menu(x_root, y_root, actions)

    def _on_sidebar_rename_request(self, comp_id: UUID, new_label: str):
        self.workspace.update_component(comp_id, label=new_label)

    def _on_back_request(self):
        self.view.canvas.drill_out()

    def _on_enter_pressed(self):
        state = self.store.state.workspace_state
        selected_ids = self.store.state.selected_component_ids
        if len(selected_ids) == 1 and state:
            comp_id = selected_ids[0]
            if comp_id in state.components:
                self.view.canvas.drill_into(comp_id)
                return "break"
        return None

    def _on_escape_pressed(self):
        if self.store.state.parent_stack:
            self.view.canvas.drill_out()
            return "break"
        return None

    def _on_arrow_key_pressed(self, dx: int, dy: int):
        selected_ids = self.store.state.selected_component_ids
        if not selected_ids:
            return
        state = self.store.state.workspace_state
        if not state:
            return

        for comp_id in selected_ids:
            comp = state.components.get(comp_id)
            if comp and not self._is_effectively_locked(comp_id):
                new_x = int(comp.bounds.x) + dx
                new_y = int(comp.bounds.y) + dy
                self.workspace.move_component(comp_id, new_x, new_y)

    def _on_import_zip_request(self):
        path = self.dialog_service.ask_open_filename(
            self.view, title="Select session zip", filetypes=[("Zip files", "*.zip")]
        )
        if not path:
            return
        dialog = self.dialog_service.show_importing_dialog(
            self.view, message="Importing workspace session..."
        )

        def do_import():
            with open(path, "rb") as f:
                self.workspace.import_zip(f.read())

        future = self._io_pool.submit(do_import)
        future.add_done_callback(
            lambda f: self._invoker.invoke(lambda: self._handle_io_result(f, dialog, "Import Failed", "Failed to import workspace session"))
        )

    def _on_import_image_request(self):
        path = self.dialog_service.ask_open_filename(
            self.view,
            title="Select raw image",
            filetypes=[("Image files", "*.png *.jpg *.jpeg")],
        )
        if not path:
            return
        dialog = self.dialog_service.show_importing_dialog(
            self.view, message="Importing raw image..."
        )

        def do_import():
            with open(path, "rb") as f:
                self.workspace.import_image(f.read(), path)

        future = self._io_pool.submit(do_import)
        future.add_done_callback(
            lambda f: self._invoker.invoke(lambda: self._handle_io_result(f, dialog, "Import Failed", "Failed to import raw image"))
        )

    def _on_export_zip_request(self):
        if not self.view.canvas.full_pil_img:
            return
        path = self.dialog_service.ask_save_as_filename(
            self.view,
            title="Save session zip",
            filetypes=[("Zip files", "*.zip")],
            defaultextension=".zip",
        )
        if not path:
            return
        dialog = self.dialog_service.show_importing_dialog(
            self.view, message="Exporting workspace session..."
        )

        def do_export():
            zip_bytes = self.workspace.export_zip()
            with open(path, "wb") as f:
                f.write(zip_bytes)

        future = self._io_pool.submit(do_export)
        future.add_done_callback(
            lambda f: self._invoker.invoke(lambda: self._handle_export_result(f, dialog))
        )

    def _handle_io_result(self, future, dialog, title, message_prefix):
        """Handle the result of a background I/O operation."""
        dialog.dismiss()
        exc = future.exception()
        if exc:
            self.dialog_service.show_error(
                self.view, title, f"{message_prefix}:\n{exc}"
            )

    def _handle_export_result(self, future, dialog):
        """Handle the result of a background export operation."""
        dialog.dismiss()
        exc = future.exception()
        if exc:
            self.dialog_service.show_error(
                self.view, "Export Failed", f"Failed to export workspace session:\n{exc}"
            )
        else:
            self.dialog_service.show_info(
                self.view, "Export Successful", "Session zip exported successfully."
            )

    def _on_open_cut_editor_request(self):
        if not self.view.canvas.full_pil_img:
            self.dialog_service.show_warning(
                self.view, "Warning", "Please open an image first!"
            )
            return
        root_comps = []
        state = self.store.state.workspace_state
        if state:
            root_comps = [
                state.components[rid]
                for rid in state.rootComponents
                if rid in state.components
            ]

        result = self.dialog_service.show_cut_editor(
            self.view,
            image=self.view.canvas.full_pil_img,
            initial_cuts=state.cutLines if state else [],
            components=root_comps,
        )
        if result is not None:
            self.workspace.update_cut_lines(result)

    def _on_open_screen_info_request(self):
        state = self.store.state.workspace_state
        if not state or not state.image:
            self.dialog_service.show_warning(
                self.view, "Warning", "Please open an image first!"
            )
            return

        screen_name = getattr(state.screen, "name", "")
        description = getattr(state.screen, "description", "")

        result = self.dialog_service.show_screen_info(
            self.view, screen_name=screen_name, description=description
        )
        if result is not None:
            self.workspace.update_screen_info(result["screen_name"], result["description"])

    def _on_canvas_drill_into(self, comp_id: UUID):
        stack = list(self.store.state.parent_stack)
        stack.append(comp_id)
        self.store.update_state(
            "selection",
            selected_component_ids=[],
            active_interaction=None,
        )
        self.store.update_state(
            "viewport",
            parent_stack=stack,
        )

    def _on_canvas_drill_out(self):
        stack = list(self.store.state.parent_stack)
        if stack:
            popped = stack.pop()
            self.store.update_state(
                "selection",
                selected_component_ids=[popped],
                active_interaction=None,
            )
            self.store.update_state(
                "viewport",
                parent_stack=stack,
            )

    def _on_canvas_viewport_change_request(
        self, zoom_factor: float, pan_offset: tuple[float, float]
    ):
        self.store.update_state(
            "viewport", zoom_factor=zoom_factor, pan_offset=pan_offset
        )

    def _on_canvas_active_interaction_changed(self, active_interaction: dict | None):
        self.store.update_state("selection", active_interaction=active_interaction)

    def _on_canvas_selection_ids_changed(self, selected_ids: list[UUID]):
        self.store.update_state("selection", selected_component_ids=selected_ids)

    def _on_canvas_viewport_size_changed(self, cw: int, ch: int):
        self.store.update_state("viewport", viewport_size=(cw, ch))

    def _on_component_moved(self, comp_id: str, x: int, y: int):
        self.workspace.move_component(UUID(str(comp_id)), x, y)

    def _on_component_resized(self, comp_id: str, bounds: dict):
        self.workspace.update_component(UUID(str(comp_id)), bounds=Bounds(**bounds))

    def _on_component_created(self, bounds: dict):
        parent_id = (
            self.store.state.parent_stack[-1] if self.store.state.parent_stack else None
        )
        comp_id = uuid.uuid4()
        self.workspace.add_component(
            comp_id=comp_id, label="Component", bounds=bounds, parent_id=parent_id
        )
        self.pending_created_ids.add(comp_id)
        self.store.update_state("selection", selected_component_ids=[comp_id])
        self.view.set_mode_str("select")

    def _on_canvas_context_menu(self, event, clicked: Component | None):
        if not self.view.canvas.full_pil_img:
            return

        items = []

        if clicked:
            self.view.canvas.set_selection([clicked])
            num_str = str(clicked.number) if clicked.number else clicked.label
            items.append(
                {
                    "label": f"Drill into Component {num_str}",
                    "command": lambda: self.view.canvas.drill_into(clicked.id),
                }
            )
            is_visible = clicked.visibility.visible
            vis_label = "Hide Component" if is_visible else "Show Component"
            items.append(
                {
                    "label": vis_label,
                    "command": lambda: self.workspace.update_component(
                        clicked.id,
                        visibility=Visibility(
                            visible=not is_visible,
                            locked=clicked.visibility.locked,
                        ),
                    ),
                }
            )
            is_locked = clicked.visibility.locked
            lock_label = "Unlock Component" if is_locked else "Lock Component"
            items.append(
                {
                    "label": lock_label,
                    "command": lambda: self.workspace.update_component(
                        clicked.id,
                        visibility=Visibility(
                            visible=clicked.visibility.visible,
                            locked=not is_locked,
                        ),
                    ),
                }
            )
            items.append(
                {
                    "label": "Delete (Delete)",
                    "command": self._on_delete_request,
                }
            )
            items.append({"separator": True})

        items.append(
            {
                "label": "Focus Target",
                "command": self.view.canvas.zoom_focus_target,
            }
        )
        items.append(
            {
                "label": "Toggle Labels (T)",
                "command": self.view.canvas.toggle_labels_visibility,
            }
        )
        self.view.show_context_menu(event.x_root, event.y_root, items)

    def _on_tree_component_selected(self, comp_id: UUID):
        state = self.store.state.workspace_state
        if not state:
            return
        comp = state.components.get(comp_id)
        if comp:
            ancestors = self.get_ancestor_chain(comp_id)
            self.store.update_state("viewport", parent_stack=ancestors)
            self.store.update_state("selection", selected_component_ids=[comp_id])

    def _on_property_changed(self, comp_id: str, **kwargs):
        # Translate simple kwargs to Style/Visibility updates
        comp = self.workspace.state.components.get(UUID(comp_id))
        if not comp:
            return

        update_kwargs = {}
        if "label" in kwargs:
            update_kwargs["label"] = kwargs["label"]
        if "pillCorner" in kwargs:
            style = comp.style.model_copy() if comp.style else Style()
            style.pillCorner = kwargs["pillCorner"]
            update_kwargs["style"] = style
        if "visible" in kwargs or "locked" in kwargs:
            vis = comp.visibility.model_copy() if comp.visibility else Visibility()
            if "visible" in kwargs:
                vis.visible = kwargs["visible"]
            if "locked" in kwargs:
                vis.locked = kwargs["locked"]
            update_kwargs["visibility"] = vis

        # properties sends x, y, w, h
        x = kwargs.get("x")
        y = kwargs.get("y")
        w = kwargs.get("w")
        h = kwargs.get("h")
        if any(v is not None for v in [x, y, w, h]):
            bounds = comp.bounds.model_copy()
            if x is not None:
                bounds.x = x
            if y is not None:
                bounds.y = y
            if w is not None:
                bounds.w = w
            if h is not None:
                bounds.h = h
            update_kwargs["bounds"] = bounds

        self.workspace.update_component(UUID(comp_id), **update_kwargs)

    def _on_properties_focus_changed(self, focused: bool):
        self.store.update_state("viewport", text_focused=focused)
