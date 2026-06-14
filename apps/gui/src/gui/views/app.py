import tkinter as tk
from tkinter import ttk

from tlgp_logger import get_logger

from .canvas import AnnotationCanvasView
from .properties import ComponentPropertiesView
from .sidebar import SidebarTreeView

logger = get_logger(__name__)


class MainAppWindow(tk.Tk):
    """Passive main application window container. Delegates menus, shortcuts, and layout actions to controller."""

    def __init__(self, store, transformer, gestures):
        super().__init__()
        self.title("TLGP Annotation Client")
        self.geometry("1200x800")
        try:
            self.state("zoomed")
        except Exception:
            pass

        self.store = store
        self.transformer = transformer
        self.gestures = gestures

        self._space_release_timer = None
        self._prev_mode_before_space = None

        self.on_mode_change_request = None
        self.on_undo_request = None
        self.on_redo_request = None
        self.on_delete_request = None
        self.on_back_request = None
        self.on_import_zip_request = None
        self.on_import_image_request = None
        self.on_export_zip_request = None
        self.on_open_cut_editor_request = None
        self.on_open_screen_info_request = None

        self.mode_var = tk.StringVar(value="select")

        self.create_widgets()
        self.create_menu_bar()
        self.bind_shortcuts()

    def create_widgets(self):
        # Top toolbar
        self.toolbar = ttk.Frame(self, padding=5)
        self.toolbar.pack(fill=tk.X, side=tk.TOP)

        # Mode Selection
        self.btn_mode_select = ttk.Radiobutton(
            self.toolbar,
            text="Select (V)",
            value="select",
            variable=self.mode_var,
            command=self._update_tool_mode,
            takefocus=False,
        )
        self.btn_mode_select.pack(side=tk.LEFT, padx=2)

        self.btn_mode_draw = ttk.Radiobutton(
            self.toolbar,
            text="Draw (R)",
            value="draw",
            variable=self.mode_var,
            command=self._update_tool_mode,
            takefocus=False,
        )
        self.btn_mode_draw.pack(side=tk.LEFT, padx=2)

        self.btn_mode_pan = ttk.Radiobutton(
            self.toolbar,
            text="Pan (H)",
            value="pan",
            variable=self.mode_var,
            command=self._update_tool_mode,
            takefocus=False,
        )
        self.btn_mode_pan.pack(side=tk.LEFT, padx=2)

        ttk.Label(self.toolbar, text="|").pack(side=tk.LEFT, padx=5)

        # Navigation controls
        self.btn_back = ttk.Button(
            self.toolbar,
            text="← Back",
            command=lambda: self.on_back_request() if self.on_back_request else None,
            state=tk.DISABLED,
            takefocus=False,
        )
        self.btn_back.pack(side=tk.LEFT, padx=2)

        self.lbl_breadcrumb = ttk.Label(self.toolbar, text="Root", font=("", 9, "bold"))
        self.lbl_breadcrumb.pack(side=tk.LEFT, padx=5)

        ttk.Label(self.toolbar, text="|").pack(side=tk.LEFT, padx=5)

        # Zoom controls
        self.lbl_zoom = ttk.Label(self.toolbar, text="100%", font=("", 9))
        self.lbl_zoom.pack(side=tk.LEFT, padx=5)

        self.btn_zoom_out = ttk.Button(
            self.toolbar,
            text="-",
            width=3,
            command=lambda: self.canvas.zoom(-0.1),
            takefocus=False,
        )
        self.btn_zoom_out.pack(side=tk.LEFT, padx=1)

        self.btn_zoom_in = ttk.Button(
            self.toolbar,
            text="+",
            width=3,
            command=lambda: self.canvas.zoom(0.1),
            takefocus=False,
        )
        self.btn_zoom_in.pack(side=tk.LEFT, padx=1)

        self.btn_zoom_focus = ttk.Button(
            self.toolbar,
            text="Focus",
            command=lambda: self.canvas.zoom_focus_target(),
            takefocus=False,
        )
        self.btn_zoom_focus.pack(side=tk.LEFT, padx=2)

        ttk.Label(self.toolbar, text="|").pack(side=tk.LEFT, padx=5)

        self.btn_cut_lines = ttk.Button(
            self.toolbar,
            text="Cut Lines (C)",
            command=lambda: (
                self.on_open_cut_editor_request()
                if self.on_open_cut_editor_request
                else None
            ),
            takefocus=False,
        )
        self.btn_cut_lines.pack(side=tk.LEFT, padx=2)

        self.lbl_status = ttk.Label(self.toolbar, text="Connecting to Engine...")
        self.lbl_status.pack(side=tk.RIGHT, padx=5)

        self.btn_screen_info = ttk.Button(
            self.toolbar,
            text="Screen Info",
            command=lambda: (
                self.on_open_screen_info_request()
                if self.on_open_screen_info_request
                else None
            ),
            takefocus=False,
        )
        self.btn_screen_info.pack(side=tk.RIGHT, padx=5)

        # Main Layout (PanedWindow)
        self.paned = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
        self.paned.pack(fill=tk.BOTH, expand=True)

        # Left Sidebar (Treeview)
        left_frame = ttk.Frame(self.paned)
        self.paned.add(left_frame, weight=1)

        tree_scroll = ttk.Scrollbar(left_frame)
        tree_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        self.tree = SidebarTreeView(left_frame, yscrollcommand=tree_scroll.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        tree_scroll.config(command=self.tree.yview)

        # Middle Area (Canvas)
        middle_frame = ttk.Frame(self.paned)
        self.paned.add(middle_frame, weight=3)

        self.canvas = AnnotationCanvasView(
            middle_frame, self.store, self.transformer, self.gestures
        )
        self.canvas.pack(fill=tk.BOTH, expand=True)

        # Right Sidebar (Properties Panel)
        self.properties = ComponentPropertiesView(self.paned, self.store)
        self.paned.add(self.properties, weight=0)

    def create_menu_bar(self):
        menu_bar = tk.Menu(self)

        self.file_menu = tk.Menu(menu_bar, tearoff=0)
        self.file_menu.add_command(
            label="Import Session Zip...",
            command=lambda: (
                self.on_import_zip_request() if self.on_import_zip_request else None
            ),
        )
        self.file_menu.add_command(
            label="Import Image...",
            command=lambda: (
                self.on_import_image_request() if self.on_import_image_request else None
            ),
        )
        self.file_menu.add_command(
            label="Export Session Zip",
            command=lambda: (
                self.on_export_zip_request() if self.on_export_zip_request else None
            ),
        )
        self.file_menu.add_separator()
        self.file_menu.add_command(label="Quit", command=self.quit)
        menu_bar.add_cascade(label="File", menu=self.file_menu)

        self.edit_menu = tk.Menu(menu_bar, tearoff=0)
        self.edit_menu.add_command(
            label="Undo (Ctrl+Z)",
            command=lambda: self.on_undo_request() if self.on_undo_request else None,
        )
        self.edit_menu.add_command(
            label="Redo (Ctrl+Y / Ctrl+Shift+Z)",
            command=lambda: self.on_redo_request() if self.on_redo_request else None,
        )
        self.edit_menu.add_separator()
        self.edit_menu.add_command(
            label="Cut Lines (C)...",
            command=lambda: (
                self.on_open_cut_editor_request()
                if self.on_open_cut_editor_request
                else None
            ),
        )
        self.edit_menu.add_separator()
        self.edit_menu.add_command(
            label="Screen Info...",
            command=lambda: (
                self.on_open_screen_info_request()
                if self.on_open_screen_info_request
                else None
            ),
        )
        self.edit_menu.add_separator()
        self.edit_menu.add_command(
            label="Delete (Delete)",
            command=lambda: (
                self.on_delete_request() if self.on_delete_request else None
            ),
        )
        menu_bar.add_cascade(label="Edit", menu=self.edit_menu)

        self.config(menu=menu_bar)

    def bind_shortcut(self, sequence: str, func, needs_unfocused: bool = True):
        """Binds a keyboard shortcut to the main window. If needs_unfocused is True,
        the callback will be ignored if any text input widget has focus, allowing native entry behavior.
        """
        def wrapper(event):
            if needs_unfocused and self.is_text_focused():
                return None
            return func(event)
        self.bind(sequence, wrapper)

    def bind_shortcuts(self):
        self.bind_shortcut(
            "<Control-z>",
            lambda e: self.on_undo_request() if self.on_undo_request else None,
        )
        self.bind_shortcut(
            "<Control-Z>",
            lambda e: self.on_undo_request() if self.on_undo_request else None,
        )
        self.bind_shortcut(
            "<Control-y>",
            lambda e: self.on_redo_request() if self.on_redo_request else None,
        )
        self.bind_shortcut(
            "<Control-Y>",
            lambda e: self.on_redo_request() if self.on_redo_request else None,
        )
        self.bind_shortcut(
            "<Control-Shift-z>",
            lambda e: self.on_redo_request() if self.on_redo_request else None,
        )
        self.bind_shortcut(
            "<Control-Shift-Z>",
            lambda e: self.on_redo_request() if self.on_redo_request else None,
        )

        self.bind_shortcut(
            "<Delete>",
            lambda e: self.on_delete_request() if self.on_delete_request else None,
        )
        self.bind_shortcut(
            "<BackSpace>",
            lambda e: self.on_delete_request() if self.on_delete_request else None,
        )

        self.bind_shortcut("<KeyPress-space>", self._on_space_press)
        self.bind_shortcut("<KeyRelease-space>", self._on_space_release)

        self.bind_shortcut("<v>", lambda e: self._set_mode_str("select"))
        self.bind_shortcut("<V>", lambda e: self._set_mode_str("select"))
        self.bind_shortcut("<r>", lambda e: self._set_mode_str("draw"))
        self.bind_shortcut("<R>", lambda e: self._set_mode_str("draw"))
        self.bind_shortcut("<h>", lambda e: self._set_mode_str("pan"))
        self.bind_shortcut("<H>", lambda e: self._set_mode_str("pan"))
        self.bind_shortcut("<f>", lambda e: self.canvas.zoom_focus_target())
        self.bind_shortcut("<F>", lambda e: self.canvas.zoom_focus_target())
        self.bind_shortcut("<t>", lambda e: self.canvas.toggle_labels_visibility())
        self.bind_shortcut("<T>", lambda e: self.canvas.toggle_labels_visibility())
        self.bind_shortcut("<c>", lambda e: self._hotkey_open_cut_editor())
        self.bind_shortcut("<C>", lambda e: self._hotkey_open_cut_editor())
        self.bind_shortcut("<Button-1>", self._on_window_click, needs_unfocused=False)
        self.bind_shortcut("<Return>", self._on_key_enter, needs_unfocused=True)
        self.bind_shortcut("<Escape>", self._on_key_escape, needs_unfocused=False)

    def is_text_focused(self) -> bool:
        return self.store.state.text_focused

    def set_ui_interactive(self, enabled: bool):
        state = tk.NORMAL if enabled else tk.DISABLED
        self.btn_mode_select.config(state=state)
        self.btn_mode_draw.config(state=state)
        self.btn_mode_pan.config(state=state)
        self.btn_zoom_out.config(state=state)
        self.btn_zoom_in.config(state=state)
        self.btn_zoom_focus.config(state=state)
        self.btn_cut_lines.config(state=state)
        self.btn_screen_info.config(state=state)

        if not enabled:
            self.btn_back.config(state=state)

        try:
            self.file_menu.entryconfig("Export Session Zip", state=state)
        except Exception:
            pass

        for label in [
            "Undo (Ctrl+Z)",
            "Redo (Ctrl+Y / Ctrl+Shift+Z)",
            "Cut Lines (C)...",
            "Screen Info...",
            "Delete (Delete)",
        ]:
            try:
                self.edit_menu.entryconfig(label, state=state)
            except Exception:
                pass

    def _update_tool_mode(self):
        mode = self.mode_var.get()
        self.canvas.set_mode(mode)
        if self.on_mode_change_request:
            self.on_mode_change_request(mode)

    def _set_mode_str(self, mode: str):
        if not self.canvas.full_pil_img:
            return
        self.mode_var.set(mode)
        self.canvas.set_mode(mode)
        if self.on_mode_change_request:
            self.on_mode_change_request(mode)

    def _on_space_press(self, event):
        if self.is_text_focused():
            return None
        if self._space_release_timer is not None:
            self.after_cancel(self._space_release_timer)
            self._space_release_timer = None
        else:
            self._prev_mode_before_space = self.mode_var.get()
            self.mode_var.set("pan")
            self.canvas.start_space_pan()
        return "break"

    def _on_space_release(self, event):
        if self.is_text_focused():
            return None
        if self._space_release_timer is not None:
            self.after_cancel(self._space_release_timer)
        self._space_release_timer = self.after(20, self._execute_space_release)
        return "break"

    def _execute_space_release(self):
        self._space_release_timer = None
        self.canvas.stop_space_pan()
        if getattr(self, "_prev_mode_before_space", None) is not None:
            self.mode_var.set(self._prev_mode_before_space)
            self._prev_mode_before_space = None

    def _on_key_enter(self, event):
        if self.is_text_focused():
            return None
        if not self.canvas.full_pil_img:
            return None
        state = self.store.state.workspace_state
        selected_boxes = [
            state.components[uid]
            for uid in self.store.state.selected_component_ids
            if state and uid in state.components
        ]
        if len(selected_boxes) == 1:
            self.canvas.drill_into(selected_boxes[0].id)
            return "break"
        return None

    def _on_key_escape(self, event):
        if self.is_text_focused():
            self.focus_set()
            return "break"
        if self.store.state.parent_stack:
            self.canvas.drill_out()
            return "break"
        return None

    def _on_window_click(self, event):
        widget = event.widget
        if not widget:
            return
        if isinstance(widget, str):
            try:
                widget = self.nametowidget(widget)
            except Exception:
                return
        if isinstance(widget, (ttk.Entry, tk.Entry, tk.Text, ttk.Combobox)):
            return
        if self.is_text_focused():
            self.focus_set()

    def _hotkey_open_cut_editor(self):
        if self.is_text_focused():
            return
        if not self.canvas.full_pil_img:
            return
        if self.on_open_cut_editor_request:
            self.on_open_cut_editor_request()
