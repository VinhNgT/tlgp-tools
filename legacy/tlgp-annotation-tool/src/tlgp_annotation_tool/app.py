import json
import os
import sys
import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import tkinterdnd2
import tkinterdnd2.TkinterDnD
import ttkbootstrap as tb
from PIL import Image

from tlgp_annotation_tool.canvas import AnnotationCanvas
from tlgp_annotation_tool.controller import SessionController
from tlgp_annotation_tool.cut_editor import CutEditorDialog
from tlgp_annotation_tool.dialogs import ScreenInfoDialog
from tlgp_annotation_tool.exporter import export_session
from tlgp_annotation_tool.history import HistoryManager
from tlgp_annotation_tool.models import AnnotationBox, ScreenSession
from tlgp_annotation_tool.properties import PropertiesPanel
from tlgp_annotation_tool.sidebar import ComponentSidebar


class TlgpAnnotationApp(tb.Window, tkinterdnd2.TkinterDnD.DnDWrapper):
    """
    TlgpAnnotationApp is the main window of the TLGP Annotation Tool application.
    It builds the application layout (Toolbar, layers sidebar, canvas, properties panel),
    manages keyboard shortcuts, and synchronizes interaction modes (Select, Draw, Pan)
    centrally through the SessionController.
    """

    def __init__(
        self,
        initial_image: str | None = None,
        session_path: str | None = None,
        default_output_dir: str | None = None,
    ):
        super().__init__(themename="darkly", title="TLGP Annotation Tool")
        self.geometry("1200x800")
        try:
            self.state("zoomed")
        except Exception:
            pass

        # Core data structures
        self.session = ScreenSession()
        if initial_image:
            self.session.original_image = os.path.abspath(initial_image)

        self.default_output_dir = (
            os.path.abspath(default_output_dir) if default_output_dir else None
        )
        self._pending_session_path = (
            os.path.abspath(session_path) if session_path else None
        )

        self.controller = SessionController(self.session)
        self._last_touchpad_scroll_time = 0.0

        # UI building
        self.create_widgets()
        self.create_menu_bar()
        self.bind_shortcuts()

        # Listeners
        self.controller.subscribe("undo_redo", lambda arg: self.on_undo_redo_sync())
        self.controller.subscribe("screen_info", lambda arg: self.title_label_update())
        self.controller.subscribe("zoom_change", self.on_zoom_changed)
        self.controller.subscribe(
            "selection_change", lambda nav, boxes: self._update_status()
        )
        self.controller.subscribe("navigation_change", self._on_navigation_change)
        self.controller.subscribe("mode_change", self.on_mode_changed)

        # Set initial toolbar state and load initial image if provided
        if self._pending_session_path:
            # Load a previously exported session — deferred to ensure widgets are ready
            self.update()
            self._load_session_from_path(self._pending_session_path)
            self._pending_session_path = None
        elif self.session.original_image:
            self.update()
            self.load_session_image()
            self.sidebar.refresh_list()
            self.after(100, self.check_trigger_screen_info)
        else:
            self.set_toolbar_state(tk.DISABLED)

        self.setup_drag_and_drop()

    def create_widgets(self):
        # Top toolbar
        toolbar = tb.Frame(self, padding=6)
        toolbar.pack(fill=tk.X, side=tk.TOP)

        # Tool mode selectors
        self.tool_mode_var = tk.StringVar(value="select")

        tool_radio_opts = {"variable": self.tool_mode_var, "bootstyle": "toolbutton"}

        self.btn_select = tb.Radiobutton(
            toolbar,
            text="Select (V)",
            value="select",
            command=self.toggle_tool_mode,
            width=8,
            **tool_radio_opts,
        )
        self.btn_select.pack(side=tk.LEFT, padx=2)

        self.btn_draw = tb.Radiobutton(
            toolbar,
            text="Draw (R)",
            value="draw",
            command=self.toggle_tool_mode,
            width=8,
            **tool_radio_opts,
        )
        self.btn_draw.pack(side=tk.LEFT, padx=2)

        self.btn_pan = tb.Radiobutton(
            toolbar,
            text="Pan (H)",
            value="pan",
            command=self.toggle_tool_mode,
            width=8,
            **tool_radio_opts,
        )
        self.btn_pan.pack(side=tk.LEFT, padx=2)

        # Back button for navigation
        self.btn_back = tb.Button(
            toolbar,
            text="← Back",
            command=self.drill_out,
            bootstyle="secondary",
            state=tk.DISABLED,
        )
        self.btn_back.pack(side=tk.LEFT, padx=2)

        tb.Label(toolbar, text="|").pack(side=tk.LEFT, padx=5)

        # Breadcrumb label
        self.breadcrumb_label = tb.Label(
            toolbar, text="Root", font=("", 9), bootstyle="info"
        )
        self.breadcrumb_label.pack(side=tk.LEFT, padx=5)

        tb.Label(toolbar, text="|").pack(side=tk.LEFT, padx=5)

        # Zoom level label and controls
        self.zoom_label = tb.Label(toolbar, text="100%", font=("", 9), width=6)
        self.zoom_label.pack(side=tk.LEFT, padx=2)

        self.btn_zoom_out = tb.Button(
            toolbar,
            text="-",
            width=3,
            bootstyle="primary-outline",
            command=lambda: self.do_zoom(-0.1),
        )
        self.btn_zoom_out.pack(side=tk.LEFT, padx=1)

        self.btn_zoom_in = tb.Button(
            toolbar,
            text="+",
            width=3,
            bootstyle="primary-outline",
            command=lambda: self.do_zoom(0.1),
        )
        self.btn_zoom_in.pack(side=tk.LEFT, padx=1)

        self.btn_zoom_focus = tb.Button(
            toolbar,
            text="Focus",
            width=6,
            bootstyle="primary-outline",
            command=self.zoom_focus_target,
        )
        self.btn_zoom_focus.pack(side=tk.LEFT, padx=1)

        # Auto-Number button
        self.btn_auto_number = tb.Button(
            toolbar,
            text="Auto-Number",
            command=self.auto_number_components,
            bootstyle="secondary-outline",
        )
        self.btn_auto_number.pack(side=tk.LEFT, padx=10)

        # Cut Lines button
        self.btn_cut_lines = tb.Button(
            toolbar,
            text="Cut Lines (C)",
            command=self.open_cut_editor,
            bootstyle="secondary-outline",
        )
        self.btn_cut_lines.pack(side=tk.LEFT, padx=2)

        # Screen Info button
        self.btn_screen_info = tb.Button(
            toolbar,
            text="Screen Info...",
            command=self.edit_screen_info,
            bootstyle="info-outline",
        )
        self.btn_screen_info.pack(side=tk.RIGHT, padx=3)

        # Export button
        self.btn_export_toolbar = tb.Button(
            toolbar,
            text="Export (Ctrl+S)",
            command=self.export_spec,
            bootstyle="success",
        )
        self.btn_export_toolbar.pack(side=tk.RIGHT, padx=3)

        # Overlap warning label
        self.lbl_export_warning = tb.Label(
            toolbar,
            text="⚠️ Overlapping regions",
            bootstyle="warning",
            font=("", 9, "bold"),
        )

        # Main Layout
        main_frame = tb.Frame(self)
        main_frame.pack(fill=tk.BOTH, expand=True)

        self.paned_window = tk.PanedWindow(
            main_frame,
            orient=tk.HORIZONTAL,
            sashwidth=4,
            sashpad=0,
            bd=0,
            showhandle=False,
        )
        self.paned_window.pack(fill=tk.BOTH, expand=True)

        # Left Panel (Sidebar)
        left_panel = tb.Frame(self.paned_window)

        self.sidebar = ComponentSidebar(
            left_panel,
            controller=self.controller,
            on_select_callback=self.on_layers_select,
            width=320,
        )
        self.sidebar.pack(fill=tk.BOTH, expand=True)

        # Center Canvas
        canvas_frame = tb.Frame(self.paned_window)

        hbar = tb.Scrollbar(canvas_frame, orient=tk.HORIZONTAL)
        hbar.pack(side=tk.BOTTOM, fill=tk.X)
        vbar = tb.Scrollbar(canvas_frame, orient=tk.VERTICAL)
        vbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.canvas = AnnotationCanvas(
            canvas_frame,
            controller=self.controller,
            on_select_callback=self.on_canvas_select,
            bg="#121212",
            xscrollcommand=hbar.set,
            yscrollcommand=vbar.set,
            xscrollincrement=1,
            yscrollincrement=1,
        )
        self.canvas.pack(fill=tk.BOTH, expand=True)

        hbar.config(command=self.canvas.xview)
        vbar.config(command=self.canvas.yview)

        # Placeholder frame for empty state
        self.placeholder_frame = tb.Frame(self.canvas)

        lbl_welcome = tb.Label(
            self.placeholder_frame,
            text="TLGP Annotation Tool",
            font=("", 14, "bold"),
            bootstyle="secondary",
        )
        lbl_welcome.pack(pady=(0, 15))

        btn_open_img = tb.Button(
            self.placeholder_frame,
            text="Open Screenshot...",
            command=self.open_images,
            bootstyle="primary",
            width=22,
        )
        btn_open_img.pack(pady=5)

        btn_open_json = tb.Button(
            self.placeholder_frame,
            text="Open Session JSON...",
            command=self.open_session,
            bootstyle="info-outline",
            width=22,
        )
        btn_open_json.pack(pady=5)

        if not self.session.original_image:
            self.placeholder_frame.place(relx=0.5, rely=0.5, anchor=tk.CENTER)

        # Right Panel (Properties)
        right_panel = tb.Frame(self.paned_window)

        self.properties = PropertiesPanel(
            right_panel,
            controller=self.controller,
            on_export_callback=self.export_spec,
            width=280,
            padding=10,
        )
        self.properties.pack(fill=tk.BOTH, expand=True)

        # Add panes
        self.paned_window.add(left_panel, minsize=150, stretch="never", width=320)
        self.paned_window.add(canvas_frame, minsize=300, stretch="always")
        self.paned_window.add(right_panel, minsize=180, stretch="never", width=280)

        # Status bar
        self.statusbar = tb.Frame(self, height=22)
        self.statusbar.pack(fill=tk.X, side=tk.BOTTOM)
        self.status_mode_label = tb.Label(
            self.statusbar, text="Mode: Select", font=("", 8), padding=5
        )
        self.status_mode_label.pack(side=tk.LEFT)
        self.status_info_label = tb.Label(
            self.statusbar, text="Depth: Root", font=("", 8), padding=5
        )
        self.status_info_label.pack(side=tk.RIGHT)

        # Subscribe to overlap-related events
        self.controller.subscribe("add", lambda box: self.check_and_update_overlaps())
        self.controller.subscribe("delete", lambda box: self.on_delete_sync())
        self.controller.subscribe(
            "update_coords", lambda box: self.check_and_update_overlaps()
        )
        self.controller.subscribe(
            "reorder", lambda box: self.check_and_update_overlaps()
        )
        self.controller.subscribe(
            "undo_redo", lambda box: self.check_and_update_overlaps()
        )

    def bind_shortcuts(self):
        self.bind("<v>", lambda e: self._hotkey_set_mode("select"))
        self.bind("<V>", lambda e: self._hotkey_set_mode("select"))
        self.bind("<s>", lambda e: self._hotkey_set_mode("select"))
        self.bind("<S>", lambda e: self._hotkey_set_mode("select"))
        self.bind("<r>", lambda e: self._hotkey_set_mode("draw"))
        self.bind("<R>", lambda e: self._hotkey_set_mode("draw"))
        self.bind("<d>", lambda e: self._hotkey_set_mode("draw"))
        self.bind("<D>", lambda e: self._hotkey_set_mode("draw"))
        self.bind("<h>", lambda e: self._hotkey_set_mode("pan"))
        self.bind("<H>", lambda e: self._hotkey_set_mode("pan"))
        self.bind("<t>", lambda e: self.toggle_labels_visibility())
        self.bind("<T>", lambda e: self.toggle_labels_visibility())

        self.bind("<Control-equal>", lambda e: self._hotkey_zoom(0.1))
        self.bind("<Control-plus>", lambda e: self._hotkey_zoom(0.1))
        self.bind("<Control-KP_Add>", lambda e: self._hotkey_zoom(0.1))
        self.bind("<Control-minus>", lambda e: self._hotkey_zoom(-0.1))
        self.bind("<Control-KP_Subtract>", lambda e: self._hotkey_zoom(-0.1))
        self.bind("<f>", lambda e: self._hotkey_focus_target())
        self.bind("<F>", lambda e: self._hotkey_focus_target())
        self.bind("<c>", lambda e: self._hotkey_open_cut_editor())
        self.bind("<C>", lambda e: self._hotkey_open_cut_editor())

        self.bind("<Control-z>", lambda e: self.undo())
        self.bind("<Control-Z>", lambda e: self.undo())
        self.bind("<Control-y>", lambda e: self.redo())
        self.bind("<Control-Y>", lambda e: self.redo())

        self.bind("<Control-s>", lambda e: self.export_spec())
        self.bind("<Control-S>", lambda e: self.export_spec())
        self.bind("<Control-a>", self.select_all_boxes)
        self.bind("<Control-A>", self.select_all_boxes)

        self.bind("<Delete>", lambda e: self.delete_selected_box())
        self.bind("<BackSpace>", lambda e: self.delete_selected_box())

        self.canvas.bind("<Control-MouseWheel>", self.on_control_scroll)
        self.canvas.bind("<Shift-MouseWheel>", self.on_shift_scroll)
        self.canvas.bind("<MouseWheel>", self.on_canvas_scroll)

        if sys.platform == "darwin":
            self.bind_all("<TouchpadScroll>", self.on_canvas_touchpad_scroll)

        self.bind("<KeyPress-space>", self.start_space_pan)
        self.bind("<KeyRelease-space>", self.stop_space_pan)
        self.bind_all("<ButtonPress-1>", self.on_global_click)
        self.bind("<Return>", self.on_key_enter)
        self.bind("<Escape>", self.on_key_escape)

    def is_text_focused(self) -> bool:
        focused = self.focus_get()
        return isinstance(
            focused, (tb.Entry, tb.Text, tk.Entry, tk.Text, ttk.Entry, ttk.Combobox)
        )

    def on_global_click(self, event):
        clicked_widget = event.widget
        if clicked_widget:
            # If the click occurred in a different top-level window, ignore it to prevent focus redirection.
            if clicked_widget.winfo_toplevel() is not self:
                return

            # Check if the clicked widget is an input widget, a combobox, a popdown listbox, or scrollbars
            is_input = (
                isinstance(
                    clicked_widget,
                    (
                        tk.Entry,
                        tk.Text,
                        ttk.Entry,
                        ttk.Combobox,
                        tk.Listbox,
                        tk.Scrollbar,
                        ttk.Scrollbar,
                    ),
                )
                or "popdown" in str(clicked_widget).lower()
                or "scrollbar" in str(clicked_widget).lower()
            )
            if not is_input:
                if clicked_widget is self.canvas:
                    self.canvas.focus_set()
                elif clicked_widget is self.sidebar.tree:
                    self.sidebar.tree.focus_set()
                else:
                    self.focus_set()

    def _hotkey_set_mode(self, mode: str):
        if self.is_text_focused():
            return
        self.set_tool_mode(mode)

    def _hotkey_zoom(self, delta: float):
        if self.is_text_focused():
            return
        self.do_zoom(delta)

    def _hotkey_focus_target(self):
        if self.is_text_focused():
            return
        self.zoom_focus_target()

    def start_space_pan(self, event):
        if self.is_text_focused():
            return
        self.canvas.start_space_pan()
        self.tool_mode_var.set("pan")
        self._update_status()

    def stop_space_pan(self, event):
        if self.is_text_focused():
            return
        self.canvas.stop_space_pan()
        self.tool_mode_var.set(self.canvas.mode)
        self._update_status()

    def on_control_scroll(self, event):

        if sys.platform == "darwin":
            if time.time() - getattr(self, "_last_touchpad_scroll_time", 0.0) < 0.1:
                return "break"
        if event.delta > 0:
            self.do_zoom(0.1, mouse_pos=(event.x, event.y))
        else:
            self.do_zoom(-0.1, mouse_pos=(event.x, event.y))
        return "break"

    def on_canvas_scroll(self, event):
        """Handle regular mousewheel scrolling on the canvas."""
        # On Windows, event.delta is typically ±120 per notch
        # Scroll by a fraction of the scrollregion based on delta
        scroll_amount = -1 * (event.delta / 120) * 60  # 60 pixels per notch
        sr = self.canvas.cget("scrollregion")
        if sr:
            parts = sr.split()
            total_h = float(parts[3]) - float(parts[1])
            if total_h > 0:
                frac = scroll_amount / total_h
                current = self.canvas.yview()[0]
                self.canvas.yview_moveto(current + frac)
        self.canvas._start_active_interaction()
        self.canvas.check_viewport_crop()
        return "break"

    def on_shift_scroll(self, event):
        """Handle Shift+mousewheel for horizontal scrolling on the canvas."""
        scroll_amount = -1 * (event.delta / 120) * 60  # 60 pixels per notch
        sr = self.canvas.cget("scrollregion")
        if sr:
            parts = sr.split()
            total_w = float(parts[2]) - float(parts[0])
            if total_w > 0:
                frac = scroll_amount / total_w
                current = self.canvas.xview()[0]
                self.canvas.xview_moveto(current + frac)
        self.canvas._start_active_interaction()
        self.canvas.check_viewport_crop()
        return "break"

    def on_canvas_touchpad_scroll(self, event):
        """Handles macOS trackpad gestures via TouchpadScroll events."""
        if str(event.widget) == str(self.canvas):
            try:
                res = self.tk.call("tk::PreciseScrollDeltas", event.delta)
                deltas = self.tk.splitlist(res)
                delta_x = float(deltas[0])
                delta_y = float(deltas[1])
            except Exception:
                return "break"

            is_control = (event.state & 0x0004) != 0
            is_command = (event.state & 0x0008) != 0 or (event.state & 0x0010) != 0

            if is_control or is_command:
                self._last_touchpad_scroll_time = time.time()
                zoom_delta = delta_y * 0.01
                self.do_zoom(zoom_delta, mouse_pos=(event.x, event.y))
            else:
                self.canvas._start_active_interaction()
                if delta_y != 0:
                    self.canvas.yview_scroll(int(-delta_y), "units")
                if delta_x != 0:
                    self.canvas.xview_scroll(int(-delta_x), "units")
                self.canvas.check_viewport_crop()
            return "break"

    def do_zoom(self, delta: float, mouse_pos: tuple[int, int] | None = None):
        self.canvas.zoom(delta, mouse_pos)

    def _update_status(self):
        mode_names = {"select": "Select", "draw": "Draw", "pan": "Pan"}
        mode_str = mode_names.get(self.canvas.mode, self.canvas.mode)
        self.status_mode_label.config(text=f"Mode: {mode_str}")

        nav = self.controller.nav
        if nav.depth == 0:
            depth_str = "Root"
        else:
            depth_str = nav.breadcrumb()

        self.status_info_label.config(text=f"Depth: {depth_str}")

    def _on_navigation_change(self):
        """Update UI elements when navigation depth changes."""
        nav = self.controller.nav
        if nav.depth > 0:
            self.btn_back.config(state=tk.NORMAL)
            self.breadcrumb_label.config(text=nav.breadcrumb())
        else:
            self.btn_back.config(state=tk.DISABLED)
            self.breadcrumb_label.config(text="Root")
        self._update_status()

    # ── Navigation ─────────────────────────────────────────────────────

    def drill_out(self):
        self.controller.drill_out()

    def on_key_enter(self, event):
        if self.is_text_focused():
            return
        # Drill into the selected box (Enter key is the only canvas-based way to drill in)
        if len(self.controller.selected_boxes) == 1:
            box = self.controller.selected_boxes[0]
            self.controller.drill_into(box)
            return "break"

    def on_key_escape(self, event):
        if self.is_text_focused():
            focused = self.focus_get()
            if focused:
                self.focus_set()
            return "break"
        if self.controller.nav.depth > 0:
            self.drill_out()
            return "break"

    # ── File Operations ────────────────────────────────────────────────

    def set_toolbar_state(self, state: str):
        self.btn_select.config(state=state)
        self.btn_draw.config(state=state)
        self.btn_pan.config(state=state)
        self.btn_back.config(
            state=state if self.controller.nav.depth > 0 else tk.DISABLED
        )
        self.btn_zoom_in.config(state=state)
        self.btn_zoom_out.config(state=state)
        self.btn_zoom_focus.config(state=state)
        self.btn_auto_number.config(state=state)
        self.btn_cut_lines.config(state=state)
        self.btn_screen_info.config(state=state)

        # Export controls state
        self.btn_export_toolbar.config(state=state)
        try:
            self.file_menu.entryconfig("Export (Ctrl+S)", state=state)
        except Exception:
            pass

        # Edit menu items
        for label in [
            "Undo (Ctrl+Z)",
            "Redo (Ctrl+Y)",
            "Delete (Delete)",
            "Select All (Ctrl+A)",
            "Auto-Number",
            "Screen Info...",
        ]:
            try:
                self.edit_menu.entryconfig(label, state=state)
            except Exception:
                pass

        # View and Navigate cascades
        try:
            self.menu_bar.entryconfig("View", state=state)
        except Exception:
            pass
        try:
            self.menu_bar.entryconfig("Navigate", state=state)
        except Exception:
            pass

    def open_images(self):
        path = filedialog.askopenfilename(
            title="Select screenshot",
            filetypes=[("Image files", "*.png *.jpg *.jpeg *.webp")],
        )
        if path:
            self.session.original_image = os.path.abspath(path)
            self.session.components = []
            self.session.cut_lines = []
            self.controller.nav.parent_stack.clear()
            self.controller.history.save_snapshot()
            self.load_session_image()
            self.sidebar.refresh_list()
            self.check_trigger_screen_info()

    def open_session(self):

        path = filedialog.askopenfilename(
            title="Select session JSON file", filetypes=[("JSON files", "*.json")]
        )
        if not path:
            return

        self._load_session_from_path(path)

    def _load_session_from_path(self, path: str):
        """Load an exported session JSON and restore the annotation state.

        Handles image resolution, dimension validation, component
        deserialization, and UI refresh. If the original image cannot be
        found automatically, prompts the user to select it manually.
        """

        # 1. Parse JSON
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
        except Exception as e:
            messagebox.showerror(
                "Error", f"Failed to parse JSON file: {e}", parent=self
            )
            return

        # Check required fields
        if "original_image" not in data or "components" not in data:
            messagebox.showerror(
                "Error",
                "Invalid session file format: missing image or components data.",
                parent=self,
            )
            return

        # 2. Resolve image path
        img_path = data["original_image"]
        expected_w = data.get("image_width")
        expected_h = data.get("image_height")

        # Check if the path exists. If not, try in the same directory as the JSON
        if img_path and not os.path.exists(img_path):
            filename = os.path.basename(img_path)
            sibling_path = os.path.join(os.path.dirname(path), filename)
            if os.path.exists(sibling_path):
                img_path = sibling_path

        resolved_img = None
        # Verify the dimensions of the file if it exists at img_path
        if img_path and os.path.exists(img_path):
            try:
                with Image.open(img_path) as temp_img:
                    w, h = temp_img.width, temp_img.height
                if expected_w is not None and expected_h is not None:
                    if w == expected_w and h == expected_h:
                        resolved_img = os.path.abspath(img_path)
                    else:
                        messagebox.showwarning(
                            "Dimension Mismatch",
                            f"The screenshot found at '{img_path}' has dimensions ({w}x{h}), "
                            f"which do not match the expected ({expected_w}x{expected_h}).\n"
                            f"Please select the correct screenshot manually.",
                            parent=self,
                        )
                else:
                    # Accept directly if JSON does not include dimension metadata
                    resolved_img = os.path.abspath(img_path)
            except Exception:
                pass

        # Loop until a valid image is selected or loading is aborted
        while not resolved_img:
            man_path = filedialog.askopenfilename(
                title="Select screenshot",
                filetypes=[("Image files", "*.png *.jpg *.jpeg *.webp")],
            )
            if not man_path:
                # Abort session loading
                return

            try:
                with Image.open(man_path) as temp_img:
                    w, h = temp_img.width, temp_img.height
            except Exception as e:
                messagebox.showerror(
                    "Error", f"Failed to read selected image: {e}", parent=self
                )
                continue

            if expected_w is not None and expected_h is not None:
                if w != expected_w or h != expected_h:
                    messagebox.showerror(
                        "Dimension Mismatch",
                        f"Selected image dimensions ({w}x{h}) do not match "
                        f"expected ({expected_w}x{expected_h}).\n\nPlease select the correct image.",
                        parent=self,
                    )
                    continue

            resolved_img = os.path.abspath(man_path)

        # 3. Recursive deserialization helper
        def parse_box(
            box_data: dict, parent_x: int = 0, parent_y: int = 0
        ) -> AnnotationBox:
            b = box_data["bounds"]
            abs_x1 = b["x"] + parent_x
            abs_y1 = b["y"] + parent_y
            abs_x2 = abs_x1 + b["w"]
            abs_y2 = abs_y1 + b["h"]

            box_obj = AnnotationBox(
                id=box_data["id"],
                label=box_data["label"],
                x1=abs_x1,
                y1=abs_y1,
                x2=abs_x2,
                y2=abs_y2,
                children=[],
                pill_corner=box_data.get("pill_corner", "top_left"),
            )
            if "children" in box_data:
                box_obj.children = [
                    parse_box(child, parent_x=abs_x1, parent_y=abs_y1)
                    for child in box_data["children"]
                ]
            return box_obj

        # Deserialize all components
        try:
            loaded_components = []
            for comp_data in data["components"]:
                loaded_components.append(parse_box(comp_data))
        except Exception as e:
            messagebox.showerror(
                "Error", f"Failed to parse annotation components: {e}", parent=self
            )
            return

        # 4. Apply new session state
        self.session.original_image = resolved_img
        self.session.screen_name = data.get("screen_name", "")
        self.session.description = data.get("description", "")
        self.session.components = loaded_components
        self.session.cut_lines = sorted(data.get("cut_lines", []))

        # Reset navigation context
        self.controller.nav.parent_stack.clear()

        # Re-initialize history manager to start with a clean undo/redo stack
        self.controller.history = HistoryManager(self.session)

        # Load image and refresh UI
        self.load_session_image()
        self.sidebar.refresh_list()
        self.title_label_update()

    def load_session_image(self):
        try:
            if self.session.original_image:
                img = Image.open(self.session.original_image)
                self.canvas.load_image(img)
                if hasattr(self, "placeholder_frame"):
                    self.placeholder_frame.place_forget()
                self.set_toolbar_state(tk.NORMAL)
        except Exception as e:
            messagebox.showerror("Error", f"Failed to load image: {e}", parent=self)

    # ── Tool Mode ──────────────────────────────────────────────────────

    def set_tool_mode(self, mode: str):
        self.controller.set_mode(mode)

    def toggle_tool_mode(self):
        self.controller.set_mode(self.tool_mode_var.get())

    def on_mode_changed(self, mode: str):
        self.tool_mode_var.set(mode)
        self._update_status()

    # ── Actions ────────────────────────────────────────────────────────

    def delete_selected_box(self):
        if self.is_text_focused():
            return
        if self.controller.selected_boxes:
            self.properties.delete_box()

    def select_all_boxes(self, event=None):
        if self.is_text_focused():
            focused = self.focus_get()
            if isinstance(focused, (tb.Entry, tk.Entry, ttk.Entry, ttk.Combobox)):
                focused.select_range(0, tk.END)
                focused.icursor(tk.END)
            elif isinstance(focused, (tb.Text, tk.Text)):
                focused.tag_add("sel", "1.0", tk.END)
            return "break"

        boxes = self.canvas._active_boxes()
        if boxes:
            self.controller.set_selection(list(boxes))
        return "break"

    def on_delete_sync(self):
        self.canvas.update_view()
        self.sidebar.refresh_list()
        self.check_and_update_overlaps()

    def undo(self):
        if self.is_text_focused():
            return
        self.controller.undo()

    def redo(self):
        if self.is_text_focused():
            return
        self.controller.redo()

    def on_undo_redo_sync(self):
        self.canvas.update_view()
        self.sidebar.refresh_list()
        self.title_label_update()
        self._on_navigation_change()

    def title_label_update(self):
        title_str = "TLGP Annotation Tool"
        if self.session.screen_name:
            title_str += f" - {self.session.screen_name}"
        self.title(title_str)

    def check_and_update_overlaps(self):
        overlaps = self.controller.get_all_overlaps()

        # If no image is loaded, export must remain disabled regardless of overlaps
        if not self.session.original_image:
            self.lbl_export_warning.pack_forget()
            self.btn_export_toolbar.config(state=tk.DISABLED)
            try:
                self.file_menu.entryconfig("Export (Ctrl+S)", state=tk.DISABLED)
            except Exception:
                pass
        elif overlaps:
            self.lbl_export_warning.pack(side=tk.RIGHT, padx=5)
            self.btn_export_toolbar.config(state=tk.DISABLED)
            try:
                self.file_menu.entryconfig("Export (Ctrl+S)", state=tk.DISABLED)
            except Exception:
                pass
        else:
            self.lbl_export_warning.pack_forget()
            self.btn_export_toolbar.config(state=tk.NORMAL)
            try:
                self.file_menu.entryconfig("Export (Ctrl+S)", state=tk.NORMAL)
            except Exception:
                pass

        overlapping_boxes = []
        for b1, b2 in overlaps:
            if b1 not in overlapping_boxes:
                overlapping_boxes.append(b1)
            if b2 not in overlapping_boxes:
                overlapping_boxes.append(b2)
        self.canvas.set_overlapping_boxes(overlapping_boxes)

    def create_menu_bar(self):
        self.menu_bar = tk.Menu(self)

        self.file_menu = tk.Menu(self.menu_bar, tearoff=0)
        self.file_menu.add_command(label="Open image...", command=self.open_images)
        self.file_menu.add_command(
            label="Open session (JSON)...", command=self.open_session
        )
        self.file_menu.add_command(label="Export (Ctrl+S)", command=self.export_spec)
        self.file_menu.add_separator()
        self.file_menu.add_command(label="Quit", command=self.quit)
        self.menu_bar.add_cascade(label="File", menu=self.file_menu)

        self.edit_menu = tk.Menu(self.menu_bar, tearoff=0)
        self.edit_menu.add_command(label="Undo (Ctrl+Z)", command=self.undo)
        self.edit_menu.add_command(label="Redo (Ctrl+Y)", command=self.redo)
        self.edit_menu.add_command(
            label="Delete (Delete)", command=self.delete_selected_box
        )
        self.edit_menu.add_command(
            label="Select All (Ctrl+A)", command=self.select_all_boxes
        )
        self.edit_menu.add_command(
            label="Auto-Number", command=self.auto_number_components
        )
        self.edit_menu.add_command(label="Cut Lines...", command=self.open_cut_editor)
        self.edit_menu.add_command(
            label="Screen Info...", command=self.edit_screen_info
        )
        self.menu_bar.add_cascade(label="Edit", menu=self.edit_menu)

        self.view_menu = tk.Menu(self.menu_bar, tearoff=0)
        self.view_menu.add_command(label="Zoom in", command=lambda: self.do_zoom(0.1))
        self.view_menu.add_command(label="Zoom out", command=lambda: self.do_zoom(-0.1))
        self.view_menu.add_command(label="Focus Target", command=self.zoom_focus_target)
        self.view_menu.add_command(
            label="Toggle labels (T)", command=self.toggle_labels_visibility
        )
        self.menu_bar.add_cascade(label="View", menu=self.view_menu)

        self.nav_menu = tk.Menu(self.menu_bar, tearoff=0)
        self.nav_menu.add_command(
            label="Drill into (Enter)", command=lambda: self.on_key_enter(None)
        )
        self.nav_menu.add_command(label="Go back (Escape)", command=self.drill_out)
        self.nav_menu.add_command(
            label="Go to root", command=self.controller.drill_to_root
        )
        self.menu_bar.add_cascade(label="Navigate", menu=self.nav_menu)

        self.help_menu = tk.Menu(self.menu_bar, tearoff=0)
        self.help_menu.add_command(label="Shortcuts", command=self.show_shortcuts_help)
        self.menu_bar.add_cascade(label="Help", menu=self.help_menu)

        self.config(menu=self.menu_bar)

    def auto_number_components(self):
        self.controller.renumber_all()

    def open_cut_editor(self):
        """Opens the cut line editor dialog."""
        if not self.canvas.full_pil_img:
            messagebox.showwarning(
                "Warning", "Please open an image first!", parent=self
            )
            return
        dialog = CutEditorDialog(
            self,
            image=self.canvas.full_pil_img,
            initial_cuts=self.controller.get_cut_lines(),
        )
        if dialog.result is not None:
            self.controller.set_cut_lines(dialog.result)

    def _hotkey_open_cut_editor(self):
        if self.is_text_focused():
            return
        self.open_cut_editor()

    def zoom_focus_target(self):
        self.canvas.zoom_focus_target()

    def toggle_labels_visibility(self):
        if self.is_text_focused():
            return
        self.canvas.toggle_labels_visibility()

    def on_zoom_changed(self, zoom_factor: float):
        pct = int(zoom_factor * 100)
        self.zoom_label.config(text=f"{pct}%")

    def show_shortcuts_help(self):
        dialog = tb.Toplevel(title="Keyboard Shortcuts", master=self)
        dialog.geometry("500x620")
        dialog.resizable(False, False)
        dialog.transient(self)
        dialog.grab_set()

        # Center dialog relative to main window
        dialog.update_idletasks()
        x = self.winfo_rootx() + (self.winfo_width() - dialog.winfo_width()) // 2
        y = self.winfo_rooty() + (self.winfo_height() - dialog.winfo_height()) // 2
        dialog.geometry(f"+{x}+{y}")

        frame = tb.Frame(dialog, padding=20)
        frame.pack(fill=tk.BOTH, expand=True)

        tb.Label(
            frame, text="KEYBOARD SHORTCUTS", font=("", 11, "bold"), bootstyle="info"
        ).pack(anchor="w", pady=(0, 15))

        shortcuts = [
            ("V, S", "Select mode"),
            ("R, D", "Draw mode"),
            ("H", "Pan mode"),
            ("Spacebar (hold)", "Temporary pan mode"),
            ("Ctrl + Scroll", "Zoom in / out at cursor"),
            ("Ctrl + +/-", "Zoom in / out"),
            ("F", "Focus Target (zoom fit selected/parent)"),
            ("Ctrl + Z", "Undo action"),
            ("Ctrl + Y", "Redo action"),
            ("Ctrl + S", "Export session (JSON & PNG)"),
            ("Ctrl + A", "Select all boxes"),
            ("T", "Toggle labels visibility"),
            ("Delete / Backspace", "Delete selected boxes"),
            ("Enter", "Drill down into selected box"),
            ("Escape", "Go back one level / Unfocus"),
        ]

        for key, desc in shortcuts:
            row = tb.Frame(frame)
            row.pack(fill=tk.X, pady=4)

            lbl_key = tb.Label(
                row,
                text=key,
                font=("Courier", 8, "bold"),
                bootstyle="inverse-info",
                padding=(6, 2),
                anchor="center",
                width=20,
            )
            lbl_key.pack(side=tk.LEFT)

            lbl_desc = tb.Label(row, text=desc, font=("", 9), padding=(10, 0))
            lbl_desc.pack(side=tk.LEFT, fill=tk.X, expand=True)

        tb.Separator(frame, orient="horizontal").pack(fill=tk.X, pady=15)

        btn_close = tb.Button(
            frame, text="Close", command=dialog.destroy, bootstyle="secondary"
        )
        btn_close.pack(side=tk.BOTTOM, anchor="e")

        dialog.bind("<Escape>", lambda e: dialog.destroy())
        dialog.bind("<Return>", lambda e: dialog.destroy())

    def edit_screen_info(self):
        dialog = ScreenInfoDialog(
            self,
            screen_name=self.session.screen_name,
            description=self.session.description,
        )
        if dialog.result:
            self.controller.update_screen_info(
                dialog.result["screen_name"], dialog.result["description"]
            )

    def check_trigger_screen_info(self):
        if not self.session.screen_name:
            self.edit_screen_info()

    def export_spec(self):
        if not self.session.original_image:
            messagebox.showwarning(
                "Warning", "Please open images before exporting!", parent=self
            )
            return

        if not self.session.screen_name:
            messagebox.showwarning(
                "Warning",
                "Please fill in the Screen Info before exporting!",
                parent=self,
            )
            return

        overlaps = self.controller.get_all_overlaps()
        if overlaps:
            messagebox.showerror(
                "Export error",
                "Cannot export: overlapping annotation regions exist. Please fix them first.",
                parent=self,
            )
            return

        output_dir = None
        if self.default_output_dir:
            # MCP-provided save path: use silently on first save
            output_dir = self.default_output_dir
        else:
            output_dir = filedialog.askdirectory(title="Select output directory")

        if not output_dir:
            return

        # Save-path mismatch warning: if a default path was provided by
        # the MCP server but the user selects a different path, warn
        # that the agent won't find the files at the new location.
        if (
            self.default_output_dir
            and os.path.abspath(output_dir) != self.default_output_dir
        ):
            proceed = messagebox.askyesno(
                "⚠️ Save path mismatch",
                f"The AI agent expects exported files at:\n"
                f"{self.default_output_dir}\n\n"
                f"Saving to a different location will cause the agent to "
                f"fail when it tries to find your exported files. The agent "
                f"will not be able to generate the specification document.\n\n"
                f"Save to the expected path instead?",
                parent=self,
            )
            if proceed:
                output_dir = self.default_output_dir

        try:
            json_path, root_paths = export_session(self.session, output_dir)
            actual_dir = os.path.dirname(json_path)
            parts_info = (
                f"{len(root_paths)} annotated image(s)"
                if root_paths
                else "annotated images"
            )
            messagebox.showinfo(
                "Success",
                f"Exported successfully:\n- JSON: {os.path.basename(json_path)}\n- {parts_info}\n- Directory: {actual_dir}",
                parent=self,
            )
        except Exception as e:
            messagebox.showerror("Error", f"Export failed: {e}", parent=self)

    # Canvas select callback
    def on_canvas_select(self, box: AnnotationBox | None):
        pass

    # Layers sidebar select callback
    def on_layers_select(self, *args):
        pass

    def setup_drag_and_drop(self):
        try:
            tkinterdnd2.TkinterDnD.require(self)

            self.drop_target_register(tkinterdnd2.DND_FILES)

            # Bind the Drop event
            self.dnd_bind("<<Drop>>", self.on_file_dropped_dnd)
        except Exception as e:
            print("Failed to initialize platform-agnostic Drag & Drop:", e)

    def on_file_dropped_dnd(self, event):
        filepath = event.data
        if filepath:
            if filepath.startswith("{") and filepath.endswith("}"):
                filepath = filepath[1:-1]
            self.on_file_dropped(filepath)

    def on_file_dropped(self, filepath: str):
        if filepath.lower().endswith((".png", ".jpg", ".jpeg", ".webp")):
            self.session.original_image = os.path.abspath(filepath)
            self.session.components = []
            self.session.cut_lines = []
            self.controller.nav.parent_stack.clear()
            self.controller.history.save_snapshot()
            self.load_session_image()
            self.sidebar.refresh_list()
            self.check_trigger_screen_info()
