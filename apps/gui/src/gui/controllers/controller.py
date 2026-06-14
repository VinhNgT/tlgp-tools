import io
import tkinter as tk
from uuid import UUID

from models import Component
from PIL import Image
from tlgp_logger import get_logger

from ..api_client import EngineClient
from ..dialog_service import DialogService
from ..state import UIStateStore
from ..views.app import MainAppWindow

logger = get_logger(__name__)


class AppController:
    """Coordinates events between the client API, observable state store, and passive views."""

    def __init__(
        self,
        client: EngineClient,
        store: UIStateStore,
        view: MainAppWindow,
        dialog_service: DialogService,
    ):
        self.client = client
        self.store = store
        self.view = view
        self.dialog_service = dialog_service
        self._loaded_session_id = None
        self.context_menu = tk.Menu(self.view, tearoff=0)

        self.view.report_callback_exception = self._global_error_handler

        # Observable state subscriptions
        self.store.subscribe("workspace", self._on_workspace_updated)
        self.store.subscribe("selection", self._on_selection_updated)
        self.store.subscribe("viewport", self._on_viewport_updated)

        # API client callbacks
        self.client.on_state_changed = self._on_state_sync_received
        self.client.on_error = self._show_async_error

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

        # Canvas callbacks
        self.view.canvas.on_import_zip = self._on_import_zip_request
        self.view.canvas.on_import_image = self._on_import_image_request
        self.view.canvas.on_selection_changed = self._on_canvas_selection_changed
        self.view.canvas.on_drill_into = self._on_canvas_drill_into
        self.view.canvas.on_drill_out = self._on_canvas_drill_out
        self.view.canvas.bind("<<ComponentMoved>>", self._handle_component_moved)
        self.view.canvas.bind("<<ComponentResized>>", self._handle_component_resized)
        self.view.canvas.bind("<<ComponentCreated>>", self._handle_component_created)
        self.view.canvas.on_request_context_menu = self._on_canvas_context_menu

        # Treeview callback
        self.view.tree.on_component_selected = self._on_tree_component_selected

        # Properties callback
        self.view.properties.on_property_changed = self._on_property_changed

    def _global_error_handler(self, exc, val, tb):
        logger.exception("Unhandled GUI exception", exc_info=(exc, val, tb))
        self.dialog_service.show_error(
            self.view,
            "Unhandled Error",
            f"An unexpected error occurred:\n{val}",
        )

    def _show_async_error(self, message: str):
        def show():
            self.dialog_service.show_error(self.view, "Error", message)

        self.view.after(0, show)

    def _on_state_sync_received(self):
        self.view.after(0, self._apply_state_sync)

    def _apply_state_sync(self):
        state = self.client.state
        if not state:
            self.view.lbl_status.config(text="Connecting to Engine...")
            self.view.set_ui_interactive(False)
            self._loaded_session_id = None
            self.store.update_state("workspace", workspace_state=None)
            return

        self.view.lbl_status.config(
            text=f"Connected to Engine | Session: {state.sessionId}"
        )

        if state.image:
            self.view.set_ui_interactive(True)
            current_session_id = str(state.sessionId) if state.sessionId else None
            if (
                current_session_id != self._loaded_session_id
                or self.view.canvas.full_pil_img is None
            ):
                try:
                    res = self.client._request("GET", self.client.get_raw_image_url())
                    img = Image.open(io.BytesIO(res.content))
                    self.view.canvas.set_background_image(img)
                    self._loaded_session_id = current_session_id
                    self.view.canvas.fit_to_screen()
                    self.view.after(100, self.check_trigger_screen_info)
                except Exception as e:
                    logger.exception("Failed to load raw background image")
                    self.dialog_service.show_error(
                        self.view,
                        "Error",
                        f"Failed to load background image: {e}",
                    )
        else:
            self.view.set_ui_interactive(False)
            self.view.canvas.full_pil_img = None
            self.view.canvas.current_pil_img = None
            if self.view.canvas.image_item_id is not None:
                self.view.canvas.delete(self.view.canvas.image_item_id)
                self.view.canvas.image_item_id = None
            self._loaded_session_id = None
            self.view.canvas.show_welcome_screen()

        # Re-resolve selection bounds with updated components list
        canvas_sel = self.store.state.selected_component_ids
        updated_sel = [uid for uid in canvas_sel if uid in state.components]
        self.store.update_state("selection", selected_component_ids=updated_sel)

        # Notify workspace state observers
        self.store.update_state("workspace", workspace_state=state)

        # Sync visual navigation controls
        self._update_navigation_ui()

    def _on_workspace_updated(self):
        state = self.store.state.workspace_state
        self.view.tree.rebuild_tree(state)
        self._sync_properties_panel()

    def _on_selection_updated(self):
        self._sync_properties_panel()
        self._sync_tree_selection()

    def _on_viewport_updated(self):
        self.view.canvas._mask_cached_img = None
        self.view.canvas._mask_cached_key = None
        self.view.canvas._last_pil_img = None

        self._update_navigation_ui()
        self._update_zoom_ui()

    def _sync_properties_panel(self):
        selected_ids = self.store.state.selected_component_ids
        state = self.store.state.workspace_state
        if len(selected_ids) == 1 and state:
            comp_id = selected_ids[0]
            comp = state.components.get(comp_id)
            if comp:
                self.view.properties.update_properties_panel(comp)
                return
        self.view.properties.disable_properties_fields()

    def _sync_tree_selection(self):
        selected_ids = self.store.state.selected_component_ids
        if selected_ids:
            self.view.tree.select_component(selected_ids[-1])
        else:
            self.view.tree.clear_selection()

    def _update_navigation_ui(self):
        nav_stack = self.store.state.parent_stack
        state = self.store.state.workspace_state
        if nav_stack:
            self.view.btn_back.config(state=tk.NORMAL)
            breadcrumbs = []
            if state:
                for comp_id in nav_stack:
                    comp = state.components.get(comp_id)
                    if comp:
                        breadcrumbs.append(
                            str(comp.number) if comp.number else comp.label
                        )
            self.view.lbl_breadcrumb.config(text=" / ".join(["Root"] + breadcrumbs))
        else:
            self.view.btn_back.config(state=tk.DISABLED)
            self.view.lbl_breadcrumb.config(text="Root")

    def _update_zoom_ui(self):
        zoom_pct = int(self.store.state.zoom_factor * 100)
        self.view.lbl_zoom.config(text=f"{zoom_pct}%")

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
        self.store.update_state("viewport", current_mode=mode)

    def _on_undo_request(self):
        if self.view.canvas.full_pil_img:
            self.client.undo()

    def _on_redo_request(self):
        if self.view.canvas.full_pil_img:
            self.client.redo()

    def _on_delete_request(self, event=None):
        if self.store.state.text_focused:
            return
        if not self.view.canvas.full_pil_img:
            return
        selected_ids = self.store.state.selected_component_ids
        if selected_ids:
            for comp_id in list(selected_ids):
                self.client.delete_component(str(comp_id))
            self.store.update_state("selection", selected_component_ids=[])

    def _on_back_request(self):
        self.view.canvas.drill_out()

    def _on_import_zip_request(self):
        path = self.dialog_service.ask_open_filename(
            self.view, title="Select session zip", filetypes=[("Zip files", "*.zip")]
        )
        if not path:
            return
        dialog = self.dialog_service.show_importing_dialog(
            self.view, message="Importing workspace session..."
        )

        def on_complete(err):
            def gui_callback():
                dialog.destroy()
                if err:
                    self.dialog_service.show_error(
                        self.view,
                        "Import Failed",
                        f"Failed to import workspace session:\n{err}",
                    )

            self.view.after(0, gui_callback)

        self.client.import_zip(path, on_complete=on_complete)

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

        def on_complete(err):
            def gui_callback():
                dialog.destroy()
                if err:
                    self.dialog_service.show_error(
                        self.view,
                        "Import Failed",
                        f"Failed to import raw image:\n{err}",
                    )

            self.view.after(0, gui_callback)

        self.client.import_image(path, on_complete=on_complete)

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

        def on_complete(err, content):
            def gui_callback():
                dialog.destroy()
                if err:
                    self.dialog_service.show_error(
                        self.view,
                        "Export Failed",
                        f"Failed to export workspace session:\n{err}",
                    )
                else:
                    try:
                        with open(path, "wb") as f:
                            f.write(content)
                        self.dialog_service.show_info(
                            self.view,
                            "Success",
                            "Workspace exported successfully!",
                        )
                    except Exception as e:
                        self.dialog_service.show_error(
                            self.view,
                            "Save Failed",
                            f"Failed to save zip to disk:\n{e}",
                        )

            self.view.after(0, gui_callback)

        self.client.export_zip_data(on_complete=on_complete)

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
            self.client.update_cut_lines(result)

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
            self.client.update_screen_info(
                result["screen_name"], result["description"]
            )

    def _on_canvas_selection_changed(self, boxes: list[Component]):
        pass

    def _on_canvas_drill_into(self, comp_id: UUID):
        pass

    def _on_canvas_drill_out(self):
        pass

    def _handle_component_moved(self, event):
        canvas = event.widget
        if getattr(canvas, "last_moved_component", None) is not None:
            box, x, y = canvas.last_moved_component
            canvas.last_moved_component = None
            self.client.move_component(str(box.id), x, y)

    def _handle_component_resized(self, event):
        canvas = event.widget
        if getattr(canvas, "last_resized_component", None) is not None:
            box, bounds = canvas.last_resized_component
            canvas.last_resized_component = None
            self.client.update_component(str(box.id), bounds=bounds)

    def _handle_component_created(self, event):
        canvas = event.widget
        if getattr(canvas, "last_created_component", None) is not None:
            bounds = canvas.last_created_component
            canvas.last_created_component = None
            parent_id = (
                self.store.state.parent_stack[-1] if self.store.state.parent_stack else None
            )
            self.client.add_component(label="Component", bounds=bounds, parent_id=parent_id)
            self.view._set_mode_str("select")

    def _on_canvas_context_menu(self, event, clicked: Component | None):
        if not self.view.canvas.full_pil_img:
            return

        self.context_menu.delete(0, tk.END)

        if clicked:
            self.view.canvas.set_selection([clicked])
            num_str = str(clicked.number) if clicked.number else clicked.label
            self.context_menu.add_command(
                label=f"Drill into Component {num_str}",
                command=lambda: self.view.canvas.drill_into(clicked.id),
            )
            is_visible = getattr(clicked.visibility, "visible", True)
            vis_label = "Hide Component" if is_visible else "Show Component"
            self.context_menu.add_command(
                label=vis_label,
                command=lambda: self.client.update_component(
                    str(clicked.id),
                    visibility={
                        "visible": not is_visible,
                        "locked": getattr(clicked.visibility, "locked", False),
                    },
                ),
            )
            is_locked = getattr(clicked.visibility, "locked", False)
            lock_label = "Unlock Component" if is_locked else "Lock Component"
            self.context_menu.add_command(
                label=lock_label,
                command=lambda: self.client.update_component(
                    str(clicked.id),
                    visibility={
                        "visible": getattr(clicked.visibility, "visible", True),
                        "locked": not is_locked,
                    },
                ),
            )
            self.context_menu.add_command(
                label="Delete (Delete)",
                command=self._on_delete_request,
            )
            self.context_menu.add_separator()

        self.context_menu.add_command(
            label="Focus Target", command=self.view.canvas.zoom_focus_target
        )
        self.context_menu.add_command(
            label="Toggle Labels (T)", command=self.view.canvas.toggle_labels_visibility
        )
        self.context_menu.post(event.x_root, event.y_root)

    def _on_tree_component_selected(self, comp_id: UUID):
        state = self.store.state.workspace_state
        if not state:
            return
        comp = state.components.get(comp_id)
        if comp:
            ancestors = self.get_ancestor_chain(comp_id)
            self.store.update_state("viewport", parent_stack=ancestors)
            self.store.update_state("selection", selected_component_ids=[comp_id])

    def _on_property_changed(self, box: Component, **kwargs):
        self.client.update_component(str(box.id), **kwargs)
