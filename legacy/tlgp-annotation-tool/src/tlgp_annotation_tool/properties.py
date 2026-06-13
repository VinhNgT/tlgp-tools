import tkinter as tk
from tkinter import messagebox

import ttkbootstrap as tb

from tlgp_annotation_tool.controller import NavigationContext, SessionController
from tlgp_annotation_tool.models import AnnotationBox


class CornerSelector(tk.Canvas):
    def __init__(self, parent, on_corner_selected_callback, **kwargs):
        # Create a compact square canvas with a solid border
        super().__init__(
            parent, width=64, height=64, highlightthickness=1, bd=0, **kwargs
        )
        self.on_corner_selected = on_corner_selected_callback
        self.selected_corner = "top_left"
        self.enabled = True

        # Coordinates of the outer layout box corners
        self.x1, self.y1 = 10, 10
        self.x2, self.y2 = 54, 54

        self.corners = {
            "top_left": (self.x1, self.y1),
            "top_right": (self.x2, self.y1),
            "bottom_left": (self.x1, self.y2),
            "bottom_right": (self.x2, self.y2),
        }

        self.bind("<Button-1>", self.on_click)
        self.bind("<Motion>", self.on_motion)
        self.draw()

    def set_corner(self, corner: str):
        if corner in self.corners:
            self.selected_corner = corner
            self.draw()

    def set_state(self, state: str):
        self.enabled = state != "disabled"
        self.draw()

    def get_colors(self):
        try:
            style = tb.Style.get_instance()
            primary = style.colors.primary
            bg = style.colors.inputbg or "#222222"
            border = style.colors.border or "#444444"
            disabled_bg = style.colors.bg or "#2b2b2b"
        except Exception:
            primary = "#375a7f"
            bg = "#222222"
            border = "#444444"
            disabled_bg = "#2b2b2b"

        if not self.enabled:
            return "#444444", disabled_bg, border
        return primary, bg, border

    def draw(self):
        self.delete("all")

        primary, bg, border = self.get_colors()

        self.configure(bg=bg, highlightbackground=border)

        # Draw the virtual container dashed boundary box
        self.create_rectangle(
            self.x1,
            self.y1,
            self.x2,
            self.y2,
            outline="#555555" if self.enabled else "#3a3a3a",
            dash=(2, 2),
            width=1,
        )

        # Draw crosshairs
        cx = (self.x1 + self.x2) // 2
        cy = (self.y1 + self.y2) // 2
        line_color = "#444444" if self.enabled else "#303030"
        self.create_line(self.x1, cy, self.x2, cy, fill=line_color, dash=(1, 3))
        self.create_line(cx, self.y1, cx, self.y2, fill=line_color, dash=(1, 3))

        # Draw four corner dots
        r = 5
        for name, (cx, cy) in self.corners.items():
            if self.enabled and self.selected_corner == name:
                # Selected dot
                self.create_oval(
                    cx - r,
                    cy - r,
                    cx + r,
                    cy + r,
                    fill=primary,
                    outline="#ffffff",
                    width=1.5,
                )
            else:
                # Unselected or disabled dot
                dot_fill = "#333333" if not self.enabled else "#555555"
                dot_outline = "#444444" if not self.enabled else "#888888"
                self.create_oval(
                    cx - r,
                    cy - r,
                    cx + r,
                    cy + r,
                    fill=dot_fill,
                    outline=dot_outline,
                    width=1,
                )

    def get_closest_corner(self, mx: int, my: int) -> str | None:
        best_corner = None
        min_dist = 18.0
        for name, (cx, cy) in self.corners.items():
            dist = ((mx - cx) ** 2 + (my - cy) ** 2) ** 0.5
            if dist < min_dist:
                min_dist = dist
                best_corner = name
        return best_corner

    def on_click(self, event):
        if not self.enabled:
            return
        clicked = self.get_closest_corner(event.x, event.y)
        if clicked:
            self.set_corner(clicked)
            if self.on_corner_selected:
                self.on_corner_selected(clicked)

    def on_motion(self, event):
        if not self.enabled:
            self.configure(cursor="")
            return
        hovered = self.get_closest_corner(event.x, event.y)
        if hovered:
            self.configure(cursor="hand2")
        else:
            self.configure(cursor="")


class PropertiesPanel(tb.Frame):
    def __init__(
        self, parent, controller: SessionController, on_export_callback, **kwargs
    ):
        super().__init__(parent, **kwargs)
        self.controller = controller
        self.session = controller.session
        self.on_export = on_export_callback

        self.selected_boxes: list[AnnotationBox] = []

        # Build UI Sections
        self.create_layer_section()

        # Subscribe to controller updates
        self.controller.subscribe("update_coords", self.on_coords_updated)
        self.controller.subscribe("rename", self.on_name_updated)
        self.controller.subscribe("undo_redo", self.on_state_synced)
        self.controller.subscribe("selection_change", self._on_selection_change)

        # Initialize widget states based on initial empty selection
        self.refresh_layer_display()

    def create_separator(self):
        sep = tb.Separator(self, orient="horizontal")
        sep.pack(fill=tk.X, pady=10)

    def create_layer_section(self):
        tb.Label(self, text="LAYER PROPERTIES", font=("", 9, "bold")).pack(
            anchor="w", pady=(0, 8)
        )

        # Name field
        name_frame = tb.Frame(self)
        name_frame.pack(fill=tk.X, pady=3)
        tb.Label(name_frame, text="Name:", font=("", 9), width=5, anchor="w").pack(
            side=tk.LEFT
        )
        self.entry_name = tb.Entry(name_frame, font=("", 9))
        self.entry_name.pack(fill=tk.X, expand=True)
        self.entry_name.bind("<Return>", self.save_box_name)
        self.entry_name.bind("<FocusOut>", self.save_box_name)
        self.entry_name.bind("<Escape>", self.cancel_box_name)

        # Coordinates grid (X, Y, W, H)
        coords_frame = tb.Frame(self)
        coords_frame.pack(fill=tk.X, pady=8)

        tb.Label(coords_frame, text="X", font=("", 8, "bold"), width=3).grid(
            row=0, column=0, sticky="w"
        )
        self.lbl_x = tb.Entry(
            coords_frame, font=("", 9), width=10, justify="center", state="readonly"
        )
        self.lbl_x.grid(row=0, column=1, padx=(0, 10), pady=2)

        tb.Label(coords_frame, text="Y", font=("", 8, "bold"), width=3).grid(
            row=0, column=2, sticky="w"
        )
        self.lbl_y = tb.Entry(
            coords_frame, font=("", 9), width=10, justify="center", state="readonly"
        )
        self.lbl_y.grid(row=0, column=3, pady=2)

        tb.Label(coords_frame, text="W", font=("", 8, "bold"), width=3).grid(
            row=1, column=0, sticky="w", pady=5
        )
        self.lbl_w = tb.Entry(
            coords_frame, font=("", 9), width=10, justify="center", state="readonly"
        )
        self.lbl_w.grid(row=1, column=1, padx=(0, 10), pady=5)

        tb.Label(coords_frame, text="H", font=("", 8, "bold"), width=3).grid(
            row=1, column=2, sticky="w", pady=5
        )
        self.lbl_h = tb.Entry(
            coords_frame, font=("", 9), width=10, justify="center", state="readonly"
        )
        self.lbl_h.grid(row=1, column=3, pady=5)

        # Pill Corner selector
        pill_frame = tb.Frame(self)
        pill_frame.pack(fill=tk.X, pady=(5, 8))
        tb.Label(
            pill_frame, text="Pill Corner:", font=("", 9), width=10, anchor="w"
        ).pack(side=tk.LEFT, pady=10)
        self.corner_selector = CornerSelector(
            pill_frame, on_corner_selected_callback=self.on_pill_corner_selected
        )
        self.corner_selector.pack(side=tk.LEFT, padx=(5, 0), pady=10)

    # ── Internal Helpers ───────────────────────────────────────────────

    def _set_entry_val(self, entry: tb.Entry, val: str):
        entry.config(state="normal")
        entry.delete(0, tk.END)
        entry.insert(0, val)
        entry.config(state="readonly")

    def cancel_box_name(self, event=None):
        if len(self.selected_boxes) == 1:
            self.entry_name.delete(0, tk.END)
            self.entry_name.insert(0, self.selected_boxes[0].label)
        self.focus_set()
        return "break"

    def _save_pending_name(self):
        if (
            len(self.selected_boxes) == 1
            and hasattr(self, "entry_name")
            and self.entry_name.winfo_exists()
        ):
            try:
                if str(self.entry_name["state"]) == tk.NORMAL:
                    self.save_box_name()
            except Exception:
                pass

    def _on_selection_change(
        self, nav: "NavigationContext", boxes: list[AnnotationBox]
    ):
        self._save_pending_name()
        self.selected_boxes = boxes
        self.refresh_layer_display()

    def refresh_layer_display(self):
        if not self.selected_boxes:
            self.entry_name.config(state=tk.NORMAL)
            self.entry_name.delete(0, tk.END)
            self.entry_name.config(state=tk.DISABLED)

            self._set_entry_val(self.lbl_x, "-")
            self._set_entry_val(self.lbl_y, "-")
            self._set_entry_val(self.lbl_w, "-")
            self._set_entry_val(self.lbl_h, "-")

            self.lbl_x.config(state=tk.DISABLED)
            self.lbl_y.config(state=tk.DISABLED)
            self.lbl_w.config(state=tk.DISABLED)
            self.lbl_h.config(state=tk.DISABLED)

            # Disable selector
            self.corner_selector.set_state("disabled")
        elif len(self.selected_boxes) > 1:
            self.entry_name.config(state=tk.NORMAL)
            self.entry_name.delete(0, tk.END)
            self.entry_name.insert(0, f"{len(self.selected_boxes)} selected")
            self.entry_name.config(state=tk.DISABLED)

            self._set_entry_val(self.lbl_x, "-")
            self._set_entry_val(self.lbl_y, "-")
            self._set_entry_val(self.lbl_w, "-")
            self._set_entry_val(self.lbl_h, "-")

            self.lbl_x.config(state=tk.DISABLED)
            self.lbl_y.config(state=tk.DISABLED)
            self.lbl_w.config(state=tk.DISABLED)
            self.lbl_h.config(state=tk.DISABLED)

            # Disable selector
            self.corner_selector.set_state("disabled")
        else:
            self.entry_name.config(state=tk.NORMAL)
            self.entry_name.delete(0, tk.END)
            box = self.selected_boxes[0]
            self.entry_name.insert(0, box.label)

            # Display coordinates relative to the current parent
            display_x = box.left
            display_y = box.top
            parent = self.controller.nav.current_parent
            if parent:
                display_x -= parent.left
                display_y -= parent.top

            self._set_entry_val(self.lbl_x, str(display_x))
            self._set_entry_val(self.lbl_y, str(display_y))
            self._set_entry_val(self.lbl_w, str(box.width))
            self._set_entry_val(self.lbl_h, str(box.height))

            # Enable and set corner selection
            self.corner_selector.set_state("normal")
            corner = getattr(box, "pill_corner", "top_left")
            self.corner_selector.set_corner(corner)

    def on_pill_corner_selected(self, corner: str):
        if len(self.selected_boxes) == 1:
            box = self.selected_boxes[0]
            if getattr(box, "pill_corner", "top_left") != corner:
                self.controller.update_box_pill_corner(box, corner)

    def save_box_name(self, event=None):
        if len(self.selected_boxes) == 1:
            val = self.entry_name.get().strip()
            if val and val != self.selected_boxes[0].label:
                self.controller.rename_box(self.selected_boxes[0], val)
        if event and event.keysym == "Return":
            self.focus_set()

    # ── Actions ────────────────────────────────────────────────────────

    def delete_box(self):
        if not self.selected_boxes:
            return

        has_children = any(box.children for box in self.selected_boxes)

        if has_children:
            ans = messagebox.askyesno(
                "Confirm",
                "One or more selected items contain children. Delete anyway?",
                parent=self.winfo_toplevel(),
            )
            if not ans:
                return

        self.controller.delete_boxes(self.selected_boxes)

    def move_up(self):
        if len(self.selected_boxes) == 1:
            self.controller.move_box_order(self.selected_boxes[0], "up")

    def move_down(self):
        if len(self.selected_boxes) == 1:
            self.controller.move_box_order(self.selected_boxes[0], "down")

    # ── Event Handlers ─────────────────────────────────────────────────

    def on_coords_updated(self, box: AnnotationBox | None):
        if len(self.selected_boxes) == 1 and self.selected_boxes[0] is box:
            self.refresh_layer_display()
        elif not box:
            self.refresh_layer_display()

    def on_name_updated(self, box: AnnotationBox):
        if len(self.selected_boxes) == 1 and self.selected_boxes[0] is box:
            self.refresh_layer_display()

    def on_state_synced(self, arg):
        # Verify if selected boxes still exist in the active list
        active = self.controller.active_list()
        self.selected_boxes = [b for b in self.selected_boxes if b in active]

        self.refresh_layer_display()
