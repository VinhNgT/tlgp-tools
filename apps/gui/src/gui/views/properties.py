import tkinter as tk
from tkinter import ttk

from models import Component


class CornerSelector(tk.Canvas):
    def __init__(self, parent, on_corner_selected_callback, **kwargs):
        super().__init__(
            parent,
            width=64,
            height=64,
            highlightthickness=1,
            bd=0,
            bg="#1a1a1a",
            highlightbackground="#333333",
            **kwargs,
        )
        self.on_corner_selected = on_corner_selected_callback
        self.selected_corner = "top_left"
        self.enabled = True

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

    def draw(self):
        self.delete("all")
        primary = "#0c8ce9"
        bg = "#1e1e1e" if self.enabled else "#121212"
        border = "#444444" if self.enabled else "#2c2c2c"

        self.configure(bg=bg, highlightbackground=border)

        self.create_rectangle(
            self.x1,
            self.y1,
            self.x2,
            self.y2,
            outline="#555555" if self.enabled else "#2c2c2c",
            dash=(2, 2),
            width=1,
        )

        cx = (self.x1 + self.x2) // 2
        cy = (self.y1 + self.y2) // 2
        line_color = "#333333" if self.enabled else "#222222"
        self.create_line(self.x1, cy, self.x2, cy, fill=line_color, dash=(1, 3))
        self.create_line(cx, self.y1, cx, self.y2, fill=line_color, dash=(1, 3))

        r = 5
        for name, (px, py) in self.corners.items():
            if self.enabled and self.selected_corner == name:
                self.create_oval(
                    px - r,
                    py - r,
                    px + r,
                    py + r,
                    fill=primary,
                    outline="#ffffff",
                    width=1.5,
                )
            else:
                dot_fill = "#2c2c2c" if not self.enabled else "#444444"
                dot_outline = "#333333" if not self.enabled else "#666666"
                self.create_oval(
                    px - r,
                    py - r,
                    px + r,
                    py + r,
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


class ComponentPropertiesView(ttk.Frame):
    """Passive metadata editor properties panel. Fires changes to the controller via callbacks."""

    def __init__(self, parent, store, **kwargs):
        super().__init__(parent, padding=10, **kwargs)
        self.store = store
        self.on_property_changed = None

        self.visible_var = tk.BooleanVar(value=True)
        self.locked_var = tk.BooleanVar(value=False)
        self._selected_box = None

        ttk.Label(self, text="PROPERTIES", font=("", 9, "bold")).pack(
            anchor="w", pady=(0, 8)
        )

        name_frame = ttk.Frame(self)
        name_frame.pack(fill=tk.X, pady=3)
        ttk.Label(name_frame, text="Name:", font=("", 9), width=8, anchor="w").pack(
            side=tk.LEFT
        )
        self.entry_name = ttk.Entry(name_frame, font=("", 9))
        self.entry_name.pack(fill=tk.X, expand=True)
        self.entry_name.bind("<Return>", self._save_name)
        self.entry_name.bind("<FocusOut>", self._save_name)
        self.entry_name.bind("<FocusIn>", lambda e: self._on_focus_in())
        self.entry_name.bind("<FocusOut>", lambda e: self._on_focus_out(), add="+")

        coords_frame = ttk.Frame(self)
        coords_frame.pack(fill=tk.X, pady=10)

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
            entry.bind("<Return>", self._save_coords)
            entry.bind("<FocusOut>", self._save_coords)
            entry.bind("<FocusIn>", lambda e: self._on_focus_in())
            entry.bind("<FocusOut>", lambda e: self._on_focus_out(), add="+")
            self.prop_entries[key] = entry

        visibility_frame = ttk.Frame(self)
        visibility_frame.pack(fill=tk.X, pady=5)
        self.chk_visible = ttk.Checkbutton(
            visibility_frame,
            text="Visible",
            variable=self.visible_var,
            command=self._save_visibility,
        )
        self.chk_visible.pack(side=tk.LEFT, padx=(0, 10))
        self.chk_locked = ttk.Checkbutton(
            visibility_frame,
            text="Locked",
            variable=self.locked_var,
            command=self._save_visibility,
        )
        self.chk_locked.pack(side=tk.LEFT)

        self.pill_frame = ttk.Frame(self)
        self.pill_frame.pack(fill=tk.X, pady=(15, 8))
        ttk.Label(self.pill_frame, text="Pill Corner:", font=("", 9)).pack(
            side=tk.LEFT, pady=10
        )
        self.corner_selector = CornerSelector(
            self.pill_frame, on_corner_selected_callback=self._save_corner
        )
        self.corner_selector.pack(side=tk.LEFT, padx=(10, 0), pady=10)

        self.disable_properties_fields()

    def update_properties_panel(self, box: Component):
        self._selected_box = box
        is_locked = getattr(box.visibility, "locked", False)
        is_visible = getattr(box.visibility, "visible", True)

        self.chk_visible.config(state=tk.NORMAL)
        self.chk_locked.config(state=tk.NORMAL)
        self.visible_var.set(is_visible)
        self.locked_var.set(is_locked)

        entry_state = tk.DISABLED if is_locked else tk.NORMAL

        self.entry_name.config(state=entry_state)
        for entry in self.prop_entries.values():
            entry.config(state=entry_state)

        self.corner_selector.set_state("disabled" if is_locked else "normal")
        corner = getattr(box.style, "pillCorner", "top_left")
        self.corner_selector.set_corner(corner)

    def is_field_focused(self, field_name: str) -> bool:
        """Returns True if the specified field currently has keyboard focus."""
        focused = self.focus_get()
        if field_name == "name":
            return focused == self.entry_name
        elif field_name in self.prop_entries:
            return focused == self.prop_entries[field_name]
        return False

    def update_field_value(self, field_name: str, value: str):
        """Updates the text content of a properties field if it is not disabled."""
        if field_name == "name":
            if self.entry_name["state"] != tk.DISABLED:
                self.entry_name.delete(0, tk.END)
                self.entry_name.insert(0, value)
        elif field_name in self.prop_entries:
            entry = self.prop_entries[field_name]
            if entry["state"] != tk.DISABLED:
                entry.delete(0, tk.END)
                entry.insert(0, value)

    def disable_properties_fields(self):
        self._selected_box = None
        self.entry_name.delete(0, tk.END)
        self.entry_name.config(state=tk.DISABLED)
        for entry in self.prop_entries.values():
            entry.delete(0, tk.END)
            entry.config(state=tk.DISABLED)

        self.corner_selector.set_state("disabled")
        self.chk_visible.config(state=tk.DISABLED)
        self.chk_locked.config(state=tk.DISABLED)

    def _on_focus_in(self):
        self.store.update_state("viewport", text_focused=True)

    def _on_focus_out(self):
        self.after(50, self._check_focus_still_on_text)

    def _check_focus_still_on_text(self):
        focused = self.focus_get()
        still_focused = isinstance(focused, (tk.Entry, tk.Text, ttk.Entry, ttk.Combobox))
        self.store.update_state("viewport", text_focused=still_focused)

    def is_text_focused(self) -> bool:
        return self.store.state.text_focused

    def _save_name(self, event=None):
        if self._selected_box and self.on_property_changed:
            val = self.entry_name.get().strip()
            if val and val != self._selected_box.label:
                self.on_property_changed(self._selected_box, label=val)
        if event and event.keysym == "Return":
            self.focus_set()

    def _save_coords(self, event=None):
        if self._selected_box and self.on_property_changed:
            try:
                bounds_dict = {
                    "x": int(self.prop_entries["x"].get().strip()),
                    "y": int(self.prop_entries["y"].get().strip()),
                    "w": int(self.prop_entries["w"].get().strip()),
                    "h": int(self.prop_entries["h"].get().strip()),
                }
                self.on_property_changed(self._selected_box, bounds=bounds_dict)
            except ValueError:
                pass
        if event and event.keysym == "Return":
            self.focus_set()

    def _save_visibility(self):
        if self._selected_box and self.on_property_changed:
            visible = self.visible_var.get()
            locked = self.locked_var.get()
            current_visible = getattr(self._selected_box.visibility, "visible", True)
            current_locked = getattr(self._selected_box.visibility, "locked", False)
            if visible != current_visible or locked != current_locked:
                self.on_property_changed(
                    self._selected_box,
                    visibility={"visible": visible, "locked": locked},
                )

    def _save_corner(self, corner: str):
        if self._selected_box and self.on_property_changed:
            if getattr(self._selected_box.style, "pillCorner", "top_left") != corner:
                self.on_property_changed(
                    self._selected_box, style={"pillCorner": corner}
                )
