import io
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import requests
from models import Component
from PIL import Image
from tlgp_logger import get_logger, setup_excepthook, setup_logging

from .api_client import EngineClient
from .canvas import AnnotationCanvas

logger = get_logger(__name__)


class TlgpApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("TLGP Annotation Client")
        self.geometry("1200x800")

        # Centralized error handler
        self.report_callback_exception = self.global_error_handler

        # Engine client
        self.client = EngineClient(on_state_changed=self.on_state_sync)

        self.create_widgets()
        self.create_menu_bar()
        self.bind_shortcuts()

    def global_error_handler(self, exc, val, tb):
        logger.exception("Unhandled GUI exception", exc_info=(exc, val, tb))
        messagebox.showerror("Unhandled Error", f"An unexpected error occurred:\n{val}")

    def create_widgets(self):
        # Top toolbar
        self.toolbar = ttk.Frame(self, padding=5)
        self.toolbar.pack(fill=tk.X, side=tk.TOP)

        self.btn_import = ttk.Button(
            self.toolbar, text="Import Session...", command=self.do_import
        )
        self.btn_import.pack(side=tk.LEFT, padx=2)

        self.btn_import_img = ttk.Button(
            self.toolbar, text="Import Image...", command=self.do_import_image
        )
        self.btn_import_img.pack(side=tk.LEFT, padx=2)

        ttk.Label(self.toolbar, text="|").pack(side=tk.LEFT, padx=5)

        # Mode Selection
        self.mode_var = tk.StringVar(value="select")
        self.btn_mode_select = ttk.Radiobutton(
            self.toolbar,
            text="Select (V)",
            value="select",
            variable=self.mode_var,
            command=self.update_tool_mode,
        )
        self.btn_mode_select.pack(side=tk.LEFT, padx=2)

        self.btn_mode_draw = ttk.Radiobutton(
            self.toolbar,
            text="Draw (R)",
            value="draw",
            variable=self.mode_var,
            command=self.update_tool_mode,
        )
        self.btn_mode_draw.pack(side=tk.LEFT, padx=2)

        self.btn_mode_pan = ttk.Radiobutton(
            self.toolbar,
            text="Pan (H)",
            value="pan",
            variable=self.mode_var,
            command=self.update_tool_mode,
        )
        self.btn_mode_pan.pack(side=tk.LEFT, padx=2)

        ttk.Label(self.toolbar, text="|").pack(side=tk.LEFT, padx=5)

        # Navigation controls
        self.btn_back = ttk.Button(
            self.toolbar, text="← Back", command=self.do_back, state=tk.DISABLED
        )
        self.btn_back.pack(side=tk.LEFT, padx=2)

        self.lbl_breadcrumb = ttk.Label(self.toolbar, text="Root", font=("", 9, "bold"))
        self.lbl_breadcrumb.pack(side=tk.LEFT, padx=5)

        ttk.Label(self.toolbar, text="|").pack(side=tk.LEFT, padx=5)

        # Zoom controls
        self.lbl_zoom = ttk.Label(self.toolbar, text="100%", font=("", 9))
        self.lbl_zoom.pack(side=tk.LEFT, padx=5)

        self.btn_zoom_out = ttk.Button(
            self.toolbar, text="-", width=3, command=lambda: self.canvas.zoom(-0.1)
        )
        self.btn_zoom_out.pack(side=tk.LEFT, padx=1)

        self.btn_zoom_in = ttk.Button(
            self.toolbar, text="+", width=3, command=lambda: self.canvas.zoom(0.1)
        )
        self.btn_zoom_in.pack(side=tk.LEFT, padx=1)

        self.btn_zoom_focus = ttk.Button(
            self.toolbar, text="Focus", command=lambda: self.canvas.zoom_focus_target()
        )
        self.btn_zoom_focus.pack(side=tk.LEFT, padx=2)

        self.lbl_status = ttk.Label(self.toolbar, text="Connecting to Engine...")
        self.lbl_status.pack(side=tk.RIGHT, padx=5)

        # Main Layout (PanedWindow)
        self.paned = ttk.PanedWindow(self, orient=tk.HORIZONTAL)
        self.paned.pack(fill=tk.BOTH, expand=True)

        # Left Sidebar (Treeview)
        left_frame = ttk.Frame(self.paned)
        self.paned.add(left_frame, weight=1)

        tree_scroll = ttk.Scrollbar(left_frame)
        tree_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        self.tree = ttk.Treeview(
            left_frame, yscrollcommand=tree_scroll.set, selectmode="browse"
        )
        self.tree.heading("#0", text="Components", anchor=tk.W)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        tree_scroll.config(command=self.tree.yview)
        self.tree.bind("<<TreeviewSelect>>", self.on_tree_select)
        self.tree.bind("<Double-Button-1>", self.on_tree_double_click)

        # Middle Area (Canvas)
        middle_frame = ttk.Frame(self.paned)
        self.paned.add(middle_frame, weight=3)

        self.canvas = AnnotationCanvas(middle_frame, self.client)
        self.canvas.pack(fill=tk.BOTH, expand=True)

        # Right Sidebar (Properties Panel)
        self.right_frame = ttk.Frame(self.paned, padding=10)
        self.paned.add(self.right_frame, weight=1)

        ttk.Label(self.right_frame, text="PROPERTIES", font=("", 9, "bold")).pack(
            anchor="w", pady=(0, 8)
        )

        name_frame = ttk.Frame(self.right_frame)
        name_frame.pack(fill=tk.X, pady=3)
        ttk.Label(name_frame, text="Name:", font=("", 9), width=8, anchor="w").pack(
            side=tk.LEFT
        )
        self.entry_name = ttk.Entry(name_frame, font=("", 9))
        self.entry_name.pack(fill=tk.X, expand=True)
        self.entry_name.bind("<Return>", self.save_property_name)
        self.entry_name.bind("<FocusOut>", self.save_property_name)

        coords_frame = ttk.Frame(self.right_frame)
        coords_frame.pack(fill=tk.X, pady=10)

        # X, Y, W, H Entries
        self.prop_entries = {}
        for idx, (label, key) in enumerate(
            [("X", "x"), ("Y", "y"), ("W", "w"), ("H", "h")]
        ):
            row = idx // 2
            col = (idx % 2) * 2
            ttk.Label(coords_frame, text=label, font=("", 8, "bold"), width=3).grid(
                row=row, column=col, sticky="w", pady=2
            )
            entry = ttk.Entry(coords_frame, font=("", 9), width=8, justify="center")
            entry.grid(row=row, column=col + 1, padx=(2, 8), pady=2)
            entry.bind("<Return>", self.save_property_coords)
            entry.bind("<FocusOut>", self.save_property_coords)
            self.prop_entries[key] = entry

        self.disable_properties_fields()

    def create_menu_bar(self):
        menu_bar = tk.Menu(self)

        file_menu = tk.Menu(menu_bar, tearoff=0)
        file_menu.add_command(label="Import Session Zip...", command=self.do_import)
        file_menu.add_command(label="Import Image...", command=self.do_import_image)
        file_menu.add_command(label="Export Session Zip", command=self.do_export)
        file_menu.add_separator()
        file_menu.add_command(label="Quit", command=self.quit)
        menu_bar.add_cascade(label="File", menu=file_menu)

        edit_menu = tk.Menu(menu_bar, tearoff=0)
        edit_menu.add_command(label="Undo (Ctrl+Z)", command=self.do_undo)
        edit_menu.add_command(
            label="Redo (Ctrl+Y / Ctrl+Shift+Z)", command=self.do_redo
        )
        menu_bar.add_cascade(label="Edit", menu=edit_menu)

        self.config(menu=menu_bar)

    def bind_shortcuts(self):
        self.bind("<Control-z>", lambda e: self.do_undo())
        self.bind("<Control-Z>", lambda e: self.do_undo())
        self.bind("<Control-y>", lambda e: self.do_redo())
        self.bind("<Control-Y>", lambda e: self.do_redo())
        self.bind("<Control-Shift-z>", lambda e: self.do_redo())
        self.bind("<Control-Shift-Z>", lambda e: self.do_redo())

        self.bind("<KeyPress-space>", lambda e: self.canvas.start_space_pan())
        self.bind("<KeyRelease-space>", lambda e: self.canvas.stop_space_pan())

        self.bind("<v>", lambda e: self.set_mode_str("select"))
        self.bind("<V>", lambda e: self.set_mode_str("select"))
        self.bind("<r>", lambda e: self.set_mode_str("draw"))
        self.bind("<R>", lambda e: self.set_mode_str("draw"))
        self.bind("<h>", lambda e: self.set_mode_str("pan"))
        self.bind("<H>", lambda e: self.set_mode_str("pan"))
        self.bind("<f>", lambda e: self.canvas.zoom_focus_target())
        self.bind("<F>", lambda e: self.canvas.zoom_focus_target())
        self.bind("<t>", lambda e: self.canvas.toggle_labels_visibility())
        self.bind("<T>", lambda e: self.canvas.toggle_labels_visibility())

        self.canvas.bind("<Control-MouseWheel>", self.on_control_scroll)
        self.canvas.bind("<Shift-MouseWheel>", self.on_shift_scroll)
        self.canvas.bind("<MouseWheel>", self.on_canvas_scroll)

    # ── Scroll / Zoom Event Redirects ───────────────────────────────────

    def on_canvas_scroll(self, event):
        scroll_amount = -1 * (event.delta / 120) * 60
        self.canvas.yview_scroll(int(scroll_amount), "units")
        self.canvas.check_viewport_crop()
        return "break"

    def on_shift_scroll(self, event):
        scroll_amount = -1 * (event.delta / 120) * 60
        self.canvas.xview_scroll(int(scroll_amount), "units")
        self.canvas.check_viewport_crop()
        return "break"

    def on_control_scroll(self, event):
        if event.delta > 0:
            self.canvas.zoom(0.1, mouse_pos=(event.x, event.y))
        else:
            self.canvas.zoom(-0.1, mouse_pos=(event.x, event.y))
        return "break"

    # ── Interaction & Sync ─────────────────────────────────────────────

    def set_mode_str(self, mode: str):
        self.mode_var.set(mode)
        self.canvas.set_mode(mode)

    def update_tool_mode(self):
        self.canvas.set_mode(self.mode_var.get())

    def do_back(self):
        self.canvas.drill_out()

    def on_navigation_change(self):
        nav_stack = self.canvas.parent_stack
        if nav_stack:
            self.btn_back.config(state=tk.NORMAL)
            breadcrumbs = []
            if self.client.state:
                for comp_id in nav_stack:
                    comp = self.client.state.components.get(comp_id)
                    if comp:
                        breadcrumbs.append(comp.number)
            self.lbl_breadcrumb.config(text=" / ".join(["Root"] + breadcrumbs))
        else:
            self.btn_back.config(state=tk.DISABLED)
            self.lbl_breadcrumb.config(text="Root")
        self.canvas.draw_boxes()

    def on_state_sync(self):
        self.after(0, self._refresh_ui)

    def _refresh_ui(self):
        if not self.client.state:
            return

        self.lbl_status.config(
            text=f"Connected | Session: {self.client.state.sessionId}"
        )

        try:
            res = requests.get(self.client.get_raw_image_url())
            res.raise_for_status()
            img = Image.open(io.BytesIO(res.content))
            self.canvas.set_background_image(img)
        except Exception as e:
            logger.error("Could not load image from Engine", error=str(e))

        # Rebuild selection list based on local selected state
        if self.canvas.selected_boxes:
            updated_selection = []
            for b in self.canvas.selected_boxes:
                if str(b.id) in self.client.state.components:
                    updated_selection.append(self.client.state.components[str(b.id)])
            self.canvas.selected_boxes = updated_selection

        self.canvas.draw_boxes()
        self._rebuild_tree()
        self.update_properties_panel()

    def _rebuild_tree(self):
        self.tree.delete(*self.tree.get_children())
        if not self.client.state:
            return

        def insert_node(parent_tvid, comp_id):
            comp = self.client.state.components.get(str(comp_id))
            if not comp:
                return

            node_text = f"{comp.number} {comp.label}" if comp.number else comp.label
            tvid = self.tree.insert(
                parent_tvid, tk.END, iid=str(comp.id), text=node_text, open=True
            )

            for child_id in comp.childrenIds:
                insert_node(tvid, child_id)

        for root_id in self.client.state.rootComponents:
            insert_node("", root_id)

    # ── Sidebar & Properties Actions ──────────────────────────────────

    def on_tree_select(self, event):
        item = self.tree.selection()
        if item and self.client.state:
            comp_id = item[0]
            comp = self.client.state.components.get(comp_id)
            if comp:
                self.canvas.selected_boxes = [comp]
                self.canvas.draw_boxes()
                self.update_properties_panel()

    def on_tree_double_click(self, event):
        item = self.tree.selection()
        if item:
            comp_id = item[0]
            self.canvas.drill_into(comp_id)

    def on_canvas_select(self, box: Component | None):
        self.update_properties_panel()
        if box:
            # Highlight in treeview
            comp_id = str(box.id)
            if self.tree.exists(comp_id):
                self.tree.selection_set(comp_id)

    def update_properties_panel(self):
        if not self.canvas.selected_boxes or len(self.canvas.selected_boxes) != 1:
            self.disable_properties_fields()
            return

        box = self.canvas.selected_boxes[0]
        self.entry_name.config(state=tk.NORMAL)
        self.entry_name.delete(0, tk.END)
        self.entry_name.insert(0, box.label)

        for key, entry in self.prop_entries.items():
            entry.config(state=tk.NORMAL)
            entry.delete(0, tk.END)
            val = getattr(box.bounds, key, 0)
            entry.insert(0, str(int(val)))

    def disable_properties_fields(self):
        self.entry_name.delete(0, tk.END)
        self.entry_name.config(state=tk.DISABLED)
        for entry in self.prop_entries.values():
            entry.delete(0, tk.END)
            entry.config(state=tk.DISABLED)

    def save_property_name(self, event=None):
        if len(self.canvas.selected_boxes) == 1:
            box = self.canvas.selected_boxes[0]
            val = self.entry_name.get().strip()
            if val and val != box.label:
                self.client.update_component(str(box.id), label=val)
        if event and event.keysym == "Return":
            self.focus_set()

    def save_property_coords(self, event=None):
        if len(self.canvas.selected_boxes) == 1:
            box = self.canvas.selected_boxes[0]
            bounds_dict = {
                "x": int(self.prop_entries["x"].get().strip()),
                "y": int(self.prop_entries["y"].get().strip()),
                "w": int(self.prop_entries["w"].get().strip()),
                "h": int(self.prop_entries["h"].get().strip()),
            }
            self.client.update_component(str(box.id), bounds=bounds_dict)
        if event and event.keysym == "Return":
            self.focus_set()

    # ── History & File Actions ──────────────────────────────────────────

    def do_undo(self):
        self.client.undo()

    def do_redo(self):
        self.client.redo()

    def do_import(self):
        path = filedialog.askopenfilename(
            title="Select session zip", filetypes=[("Zip files", "*.zip")]
        )
        if not path:
            return
        self.client.import_zip(path)
        messagebox.showinfo("Success", "Workspace imported to Engine!")

    def do_import_image(self):
        path = filedialog.askopenfilename(
            title="Select raw image", filetypes=[("Image files", "*.png *.jpg *.jpeg")]
        )
        if not path:
            return
        self.client.import_image(path)
        messagebox.showinfo("Success", "Image imported to Engine!")

    def do_export(self):
        path = filedialog.asksaveasfilename(
            title="Save session zip",
            filetypes=[("Zip files", "*.zip")],
            defaultextension=".zip",
        )
        if not path:
            return
        res = self.client.export_zip_data()
        with open(path, "wb") as f:
            f.write(res.content)
        messagebox.showinfo("Success", "Workspace exported successfully!")


def main():
    setup_logging()
    setup_excepthook()
    app = TlgpApp()
    app.mainloop()


if __name__ == "__main__":
    main()
