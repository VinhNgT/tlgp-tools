"""Cut Editor Dialog — modal for managing horizontal cut lines.

Shows the full ungapped screenshot with draggable cut lines overlaid.
The user can add, move, and remove cut lines. On OK, the lines are
committed to the controller; on Cancel, changes are discarded.
"""

import tkinter as tk
from tkinter import ttk
import ttkbootstrap as tb
from typing import List, Optional, Tuple
from PIL import Image, ImageTk, ImageDraw


# Minimum distance (in image pixels) between two cut lines or
# between a cut line and the image top/bottom edge.
MIN_CUT_GAP = 50

# Snap distance in canvas pixels — how close the cursor must be to
# a cut line to start a drag.
SNAP_DISTANCE = 8


class CutEditorDialog(tb.Toplevel):
    """Modal dialog for editing horizontal cut lines on the full screenshot."""

    def __init__(self, parent, image: Image.Image, initial_cuts: List[int]):
        super().__init__(parent)
        self.title("Edit Cut Lines")
        self.geometry("900x700")
        self.resizable(True, True)
        self.transient(parent)
        self.grab_set()

        # Center relative to parent
        self.update_idletasks()
        pw = parent.winfo_width()
        ph = parent.winfo_height()
        px = parent.winfo_rootx()
        py = parent.winfo_rooty()
        x = px + (pw - 900) // 2
        y = py + (ph - 700) // 2
        self.geometry(f"+{max(0, x)}+{max(0, y)}")

        self.source_image = image
        self.cut_lines: List[int] = sorted(initial_cuts)
        self.result: Optional[List[int]] = None

        # Canvas state
        self.zoom_factor: float = 1.0
        self.tk_photo = None
        self._prev_tk_photo = None
        self.image_item_id = None

        # Interaction state
        self._mode: str = "idle"  # "idle", "adding", "dragging"
        self._drag_index: int = -1
        self._drag_start_y: int = 0
        self._selected_index: int = -1

        self._build_ui()
        self._bind_events()

        # Populate the cut line listbox with initial values on open.
        self._refresh_listbox()

        # Initial render after the dialog has sized itself
        self.after(50, self._fit_and_render)

        self.protocol("WM_DELETE_WINDOW", self._on_cancel)
        self.wait_window(self)

    # ── UI Construction ────────────────────────────────────────────────

    def _build_ui(self):
        main = tb.Frame(self)
        main.pack(fill=tk.BOTH, expand=True)

        # Left: scrollable canvas
        canvas_frame = tb.Frame(main)
        canvas_frame.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        vbar = tb.Scrollbar(canvas_frame, orient=tk.VERTICAL)
        vbar.pack(side=tk.RIGHT, fill=tk.Y)

        self.canvas = tk.Canvas(
            canvas_frame, bg="#1a1a1a",
            highlightthickness=0, borderwidth=0,
            yscrollcommand=vbar.set,
            yscrollincrement=1,
        )
        self.canvas.pack(fill=tk.BOTH, expand=True)
        vbar.config(command=self.canvas.yview)

        # Right: controls panel
        right = tb.Frame(main, padding=10, width=200)
        right.pack(side=tk.RIGHT, fill=tk.Y)
        right.pack_propagate(False)

        tb.Label(right, text="CUT LINES", font=("", 10, "bold")).pack(anchor="w", pady=(0, 8))

        # Listbox of cut Y-coordinates
        list_frame = tb.Frame(right)
        list_frame.pack(fill=tk.BOTH, expand=True, pady=(0, 10))

        self.listbox = tk.Listbox(list_frame, font=("", 9), selectmode=tk.SINGLE,
                                  bg="#2b2b2b", fg="#ffffff",
                                  selectbackground="#0c8ce9", selectforeground="#ffffff",
                                  highlightthickness=0, borderwidth=1, relief="flat")
        self.listbox.pack(fill=tk.BOTH, expand=True)
        self.listbox.bind("<<ListboxSelect>>", self._on_listbox_select)

        # Buttons
        btn_frame = tb.Frame(right)
        btn_frame.pack(fill=tk.X, pady=(0, 10))

        self.btn_add = tb.Button(btn_frame, text="Add Cut", command=self._start_add_mode,
                                 bootstyle="primary", width=12)
        self.btn_add.pack(fill=tk.X, pady=2)

        self.btn_remove = tb.Button(btn_frame, text="Remove", command=self._remove_selected,
                                    bootstyle="danger-outline", width=12, state=tk.DISABLED)
        self.btn_remove.pack(fill=tk.X, pady=2)

        self.btn_clear = tb.Button(btn_frame, text="Clear All", command=self._clear_all,
                                   bootstyle="warning-outline", width=12)
        self.btn_clear.pack(fill=tk.X, pady=2)

        # Status label
        self.status_label = tb.Label(right, text="", font=("", 8), bootstyle="secondary",
                                     wraplength=170)
        self.status_label.pack(fill=tk.X, pady=(0, 10))

        # OK / Cancel
        tb.Separator(right, orient="horizontal").pack(fill=tk.X, pady=5)

        action_frame = tb.Frame(right)
        action_frame.pack(fill=tk.X, side=tk.BOTTOM)

        tb.Button(action_frame, text="Cancel", command=self._on_cancel,
                  bootstyle="secondary", width=8).pack(side=tk.RIGHT, padx=(5, 0))
        tb.Button(action_frame, text="OK", command=self._on_ok,
                  bootstyle="primary", width=8).pack(side=tk.RIGHT)

    def _bind_events(self):
        self.canvas.bind("<ButtonPress-1>", self._on_canvas_click)
        self.canvas.bind("<B1-Motion>", self._on_canvas_drag)
        self.canvas.bind("<ButtonRelease-1>", self._on_canvas_release)
        self.canvas.bind("<Motion>", self._on_canvas_motion)
        self.canvas.bind("<Configure>", self._on_canvas_resize)
        self.canvas.bind("<MouseWheel>", self._on_canvas_scroll)
        self.bind("<Escape>", self._on_escape)
        self.bind("<Delete>", lambda e: self._remove_selected())
        self.bind("<BackSpace>", lambda e: self._remove_selected())

    def _on_canvas_scroll(self, event):
        """Handle mousewheel scrolling on the cut editor canvas."""
        # On Windows, event.delta is typically ±120 per notch
        scroll_amount = -1 * (event.delta / 120) * 60  # 60 pixels per notch
        sr = self.canvas.cget("scrollregion")
        if sr:
            parts = sr.split()
            total_h = float(parts[3]) - float(parts[1])
            if total_h > 0:
                frac = scroll_amount / total_h
                current = self.canvas.yview()[0]
                self.canvas.yview_moveto(current + frac)
        return "break"

    # ── Coordinate Helpers ─────────────────────────────────────────────

    def _to_canvas_y(self, img_y: int) -> float:
        return img_y * self.zoom_factor

    def _to_img_y(self, canvas_y: float) -> int:
        return round(canvas_y / self.zoom_factor)

    # ── Rendering ──────────────────────────────────────────────────────

    def _fit_and_render(self):
        vw = self.canvas.winfo_width()
        vh = self.canvas.winfo_height()
        if vw <= 1 or vh <= 1:
            vw, vh = 700, 650

        img_w = self.source_image.width
        img_h = self.source_image.height

        # Fit width to canvas, allow vertical scrolling
        self.zoom_factor = max(0.05, min(1.0, (vw - 20) / img_w))
        self._render()

    def _render(self):
        """Render the image and cut lines on the canvas."""
        img_w = self.source_image.width
        img_h = self.source_image.height

        disp_w = max(1, round(img_w * self.zoom_factor))
        disp_h = max(1, round(img_h * self.zoom_factor))

        resampler = Image.Resampling.BILINEAR if self.zoom_factor > 1.0 else Image.Resampling.LANCZOS
        resized = self.source_image.resize((disp_w, disp_h), resampler)

        self._prev_tk_photo = self.tk_photo
        self.tk_photo = ImageTk.PhotoImage(resized)

        if self.image_item_id is None:
            self.image_item_id = self.canvas.create_image(0, 0, anchor="nw", image=self.tk_photo)
        else:
            self.canvas.itemconfig(self.image_item_id, image=self.tk_photo)
            self.canvas.coords(self.image_item_id, 0, 0)

        self.canvas.config(scrollregion=(0, 0, disp_w, disp_h))
        self._draw_cut_lines()

    def _draw_cut_lines(self):
        """Draw all cut lines on the canvas."""
        self.canvas.delete("cut_line")

        disp_w = max(1, round(self.source_image.width * self.zoom_factor))

        for i, y in enumerate(self.cut_lines):
            cy = self._to_canvas_y(y)
            is_selected = (i == self._selected_index)
            color = "#0c8ce9" if is_selected else "#ff4444"
            width = 3 if is_selected else 2

            self.canvas.create_line(
                0, cy, disp_w, cy,
                fill=color, width=width, dash=(8, 4),
                tags="cut_line"
            )

            # Label showing Y coordinate
            label_text = f"Y={y}"
            self.canvas.create_text(
                disp_w - 5, cy - 8,
                text=label_text, anchor="ne",
                fill=color, font=("Arial", 8, "bold"),
                tags="cut_line"
            )

        # Keep image behind cut lines
        if self.image_item_id is not None:
            self.canvas.tag_lower(self.image_item_id)

    def _refresh_listbox(self):
        """Refresh the listbox to match current cut_lines."""
        self.listbox.delete(0, tk.END)
        for i, y in enumerate(self.cut_lines):
            self.listbox.insert(tk.END, f"Cut {i + 1}:  Y = {y}")

        if 0 <= self._selected_index < len(self.cut_lines):
            self.listbox.selection_set(self._selected_index)
            self.listbox.see(self._selected_index)

        self.btn_remove.config(
            state=tk.NORMAL if 0 <= self._selected_index < len(self.cut_lines) else tk.DISABLED
        )

    # ── Add Mode ───────────────────────────────────────────────────────

    def _start_add_mode(self):
        self._mode = "adding"
        self.canvas.config(cursor="crosshair")
        self.status_label.config(text="Click on the image to place a horizontal cut line. Press Escape to cancel.")
        self.btn_add.config(state=tk.DISABLED)

    def _cancel_add_mode(self):
        self._mode = "idle"
        self.canvas.config(cursor="")
        self.status_label.config(text="")
        self.btn_add.config(state=tk.NORMAL)

    # ── Canvas Events ──────────────────────────────────────────────────

    def _on_canvas_click(self, event):
        cy = self.canvas.canvasy(event.y)
        img_y = self._to_img_y(cy)

        if self._mode == "adding":
            # Place a new cut line
            if self._is_valid_cut_position(img_y):
                self.cut_lines.append(img_y)
                self.cut_lines.sort()
                self._selected_index = self.cut_lines.index(img_y)
                self._cancel_add_mode()
                self._draw_cut_lines()
                self._refresh_listbox()
            return

        # Check if clicking near an existing cut line
        hit_index = self._hit_test_cut(cy)
        if hit_index >= 0:
            self._selected_index = hit_index
            self._mode = "dragging"
            self._drag_index = hit_index
            self._drag_start_y = img_y
            self.canvas.config(cursor="sb_v_double_arrow")
        else:
            self._selected_index = -1

        self._draw_cut_lines()
        self._refresh_listbox()

    def _on_canvas_drag(self, event):
        if self._mode != "dragging" or self._drag_index < 0:
            return

        cy = self.canvas.canvasy(event.y)
        new_y = self._to_img_y(cy)

        # Clamp to image bounds with minimum gap
        new_y = max(MIN_CUT_GAP, min(self.source_image.height - MIN_CUT_GAP, new_y))

        # Ensure minimum gap from neighboring cuts
        lines = list(self.cut_lines)
        lines.pop(self._drag_index)

        # Check against remaining lines
        for other_y in lines:
            if abs(new_y - other_y) < MIN_CUT_GAP:
                # Snap to the minimum gap boundary
                if new_y < other_y:
                    new_y = other_y - MIN_CUT_GAP
                else:
                    new_y = other_y + MIN_CUT_GAP

        new_y = max(MIN_CUT_GAP, min(self.source_image.height - MIN_CUT_GAP, new_y))

        self.cut_lines[self._drag_index] = new_y
        self.cut_lines.sort()
        # Track the moved line's new index
        self._drag_index = self.cut_lines.index(new_y)
        self._selected_index = self._drag_index

        self._draw_cut_lines()
        self._refresh_listbox()

    def _on_canvas_release(self, event):
        if self._mode == "dragging":
            self._mode = "idle"
            self._drag_index = -1
            self.canvas.config(cursor="")

    def _on_canvas_motion(self, event):
        if self._mode == "adding":
            return  # crosshair cursor is already set
        if self._mode == "dragging":
            return  # sb_v_double_arrow is already set

        cy = self.canvas.canvasy(event.y)
        hit = self._hit_test_cut(cy)
        if hit >= 0:
            self.canvas.config(cursor="sb_v_double_arrow")
        else:
            self.canvas.config(cursor="")

    def _on_canvas_resize(self, event):
        self._fit_and_render()

    def _on_escape(self, event):
        if self._mode == "adding":
            self._cancel_add_mode()
        else:
            self._on_cancel()

    # ── Hit Testing ────────────────────────────────────────────────────

    def _hit_test_cut(self, canvas_y: float) -> int:
        """Returns the index of the cut line near canvas_y, or -1."""
        for i, y in enumerate(self.cut_lines):
            cy = self._to_canvas_y(y)
            if abs(canvas_y - cy) <= SNAP_DISTANCE:
                return i
        return -1

    def _is_valid_cut_position(self, img_y: int) -> bool:
        """Check if a cut can be placed at img_y with sufficient gaps."""
        if img_y < MIN_CUT_GAP or img_y > self.source_image.height - MIN_CUT_GAP:
            return False
        for existing_y in self.cut_lines:
            if abs(img_y - existing_y) < MIN_CUT_GAP:
                return False
        return True

    # ── Listbox Events ─────────────────────────────────────────────────

    def _on_listbox_select(self, event):
        sel = self.listbox.curselection()
        if sel:
            self._selected_index = sel[0]
        else:
            self._selected_index = -1
        self._draw_cut_lines()
        self.btn_remove.config(
            state=tk.NORMAL if 0 <= self._selected_index < len(self.cut_lines) else tk.DISABLED
        )

    # ── Button Actions ─────────────────────────────────────────────────

    def _remove_selected(self):
        if 0 <= self._selected_index < len(self.cut_lines):
            self.cut_lines.pop(self._selected_index)
            self._selected_index = min(self._selected_index, len(self.cut_lines) - 1)
            self._draw_cut_lines()
            self._refresh_listbox()

    def _clear_all(self):
        if not self.cut_lines:
            return
        self.cut_lines.clear()
        self._selected_index = -1
        self._draw_cut_lines()
        self._refresh_listbox()

    def _on_ok(self):
        self.result = sorted(self.cut_lines)
        self.grab_release()
        self.destroy()

    def _on_cancel(self):
        self.result = None
        self.grab_release()
        self.destroy()
