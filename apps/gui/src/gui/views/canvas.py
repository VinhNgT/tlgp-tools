import sys
import time
import tkinter as tk
from tkinter import ttk
from uuid import UUID

from models import Component
from PIL import Image, ImageDraw, ImageTk
from rendering.renderer import (
    compute_border_widths,
    compute_pill_font_size,
    compute_pill_padding,
    get_font,
    get_pill_coords,
    get_text_dimensions,
)
from tlgp_logger import get_logger

from ..state import UIStateStore
from .gestures import GestureInterpreter
from .transformer import CUT_GAP_PX, ViewportTransformer

logger = get_logger(__name__)


class WelcomeScreen(ttk.Frame):
    def __init__(self, parent_canvas, on_import_zip, on_import_image, **kwargs):
        super().__init__(parent_canvas, padding=30, style="Card.TFrame", **kwargs)
        style = ttk.Style()
        style.configure(
            "Card.TFrame", background="#1e1e1e", relief="solid", borderwidth=1
        )
        style.configure("WelcomeContainer.TFrame", background="#1e1e1e")
        style.configure(
            "WelcomeTitle.TLabel",
            font=("", 16, "bold"),
            foreground="#ffffff",
            background="#1e1e1e",
        )
        style.configure(
            "WelcomeDesc.TLabel",
            font=("", 10),
            foreground="#888888",
            background="#1e1e1e",
        )
        style.configure("WelcomeButton.TButton", font=("", 10, "bold"))

        lbl_title = ttk.Label(
            self,
            text="Welcome to TLGP Tools",
            style="WelcomeTitle.TLabel",
            anchor="center",
        )
        lbl_title.pack(pady=(0, 10))

        lbl_desc = ttk.Label(
            self,
            text="Get started by importing a project workspace or a raw screenshot image.",
            style="WelcomeDesc.TLabel",
            anchor="center",
        )
        lbl_desc.pack(pady=(0, 25))

        btn_frame = ttk.Frame(self, style="WelcomeContainer.TFrame")
        btn_frame.pack()

        btn_zip = ttk.Button(
            btn_frame,
            text="Import Zip Project",
            style="WelcomeButton.TButton",
            command=on_import_zip,
        )
        btn_zip.pack(side=tk.LEFT, padx=10)

        btn_img = ttk.Button(
            btn_frame,
            text="Import Screenshot",
            style="WelcomeButton.TButton",
            command=on_import_image,
        )
        btn_img.pack(side=tk.LEFT, padx=10)


class AnnotationCanvasView(tk.Canvas):
    """Passive canvas rendering viewport widget. Exposes event delegate callbacks to the controller."""

    def __init__(
        self,
        parent,
        store: UIStateStore,
        transformer: ViewportTransformer,
        gestures: GestureInterpreter,
        **kwargs,
    ):
        super().__init__(parent, highlightthickness=0, bg="#121212", **kwargs)
        self.store = store
        self.transformer = transformer
        self.gestures = gestures

        self.full_pil_img = None
        self.current_pil_img = None
        self.image_item_id = None
        self.welcome_screen = None
        self.show_labels = True

        self._mask_cached_img = None
        self._mask_cached_key = None
        self._last_pil_img = None
        self._last_crop_box = None
        self._zoom_cached_photo = None
        self._zoom_cached_key = None
        self._last_pan_offset = (0.0, 0.0)
        self._last_workspace_revision = None
        self._redraw_pending = False

        self.on_import_zip = None
        self.on_import_image = None
        self.on_selection_changed = None
        self.on_drill_into = None
        self.on_drill_out = None
        self.last_moved_component = None
        self.last_resized_component = None
        self.last_created_component = None
        self.on_request_context_menu = None

        self.bind("<Button-1>", self.on_click)
        self.bind("<B1-Motion>", self.on_drag)
        self.bind("<ButtonRelease-1>", self.on_release)
        self.bind("<Motion>", self.on_mouse_move)
        self.bind("<Configure>", self.on_canvas_resize)

        self.bind("<Button-2>", self.on_right_click)
        self.bind("<Button-3>", self.on_right_click)

        self.bind("<Control-Button-1>", self._on_control_click)
        self.bind("<MouseWheel>", self._on_scroll)
        self.bind("<Button-4>", self._on_scroll)
        self.bind("<Button-5>", self._on_scroll)

        if sys.platform == "darwin":
            self.bind_all("<TouchpadScroll>", self._on_canvas_touchpad_scroll)

        self._space_pan_active = False

        # Subscribe reactively to store state changes
        self.store.subscribe("viewport", self.queue_update_view)
        self.store.subscribe("workspace", self.queue_update_view)
        self.store.subscribe("selection", self.draw_boxes)

    def set_background_image(self, img: Image.Image):
        self.hide_welcome_screen()
        self.full_pil_img = img
        self.transformer.update_image_size(img.width, img.height)
        self._mask_cached_img = None
        self._mask_cached_key = None
        self._last_pil_img = None
        self._last_crop_box = None
        self._zoom_cached_photo = None
        self._zoom_cached_key = None
        self._last_pan_offset = (0.0, 0.0)
        self._last_workspace_revision = None

    def show_welcome_screen(self):
        self.delete("all")
        if self.welcome_screen:
            self.welcome_screen.destroy()
            self.welcome_screen = None
        self.welcome_screen = WelcomeScreen(
            self,
            on_import_zip=lambda: self.on_import_zip() if self.on_import_zip else None,
            on_import_image=lambda: (
                self.on_import_image() if self.on_import_image else None
            ),
        )
        self.create_window(
            0, 0, window=self.welcome_screen, anchor="center", tags="welcome"
        )
        self.on_canvas_resize(None)

    def hide_welcome_screen(self):
        if self.welcome_screen:
            self.welcome_screen.destroy()
            self.welcome_screen = None
        self.delete("welcome")

    def fit_to_screen(self):
        if not self.full_pil_img:
            return
        self.update_idletasks()
        cw = self.winfo_width()
        ch = self.winfo_height()
        if cw <= 1 or ch <= 1:
            cw, ch = 800, 600

        img_w = self.full_pil_img.width
        img_h = self.full_pil_img.height

        cut_lines = (
            self.store.state.workspace_state.cutLines
            if self.store.state.workspace_state
            else []
        )
        parent_stack = self.store.state.parent_stack
        if self.transformer.has_active_cuts(parent_stack, cut_lines):
            self.transformer.rebuild_segments(cut_lines)
            img_h += len(cut_lines) * CUT_GAP_PX

        ratio_w = cw / img_w
        ratio_h = ch / img_h
        fit_zoom = min(ratio_w, ratio_h) * 0.95

        zoom_factor = max(0.1, min(4.0, fit_zoom))
        pan_x = (cw - img_w * zoom_factor) / 2
        pan_y = (ch - img_h * zoom_factor) / 2
        self.store.update_state("viewport", zoom_factor=zoom_factor, pan_offset=(pan_x, pan_y))

    def queue_update_view(self):
        if not self._redraw_pending:
            self._redraw_pending = True
            self.after(16, self._execute_redraw)

    def _execute_redraw(self):
        self._redraw_pending = False
        self.update_view()

    def update_view(self):
        if not self.full_pil_img:
            return

        cw = self.winfo_width()
        ch = self.winfo_height()
        if cw <= 1 or ch <= 1:
            return

        cut_lines = (
            self.store.state.workspace_state.cutLines
            if self.store.state.workspace_state
            else []
        )
        parent_stack = self.store.state.parent_stack
        cut_lines_tuple = tuple(cut_lines) if cut_lines else ()

        if self.transformer.has_active_cuts(parent_stack, cut_lines):
            self.transformer.rebuild_segments(cut_lines)
            if (self._last_pil_img is not self.full_pil_img 
                    or getattr(self, "_last_cut_lines", None) != cut_lines_tuple):
                self.current_pil_img = self.transformer.composite_gapped_image(
                    self.full_pil_img
                )
                self._last_pil_img = self.full_pil_img
                self._last_cut_lines = cut_lines_tuple
        else:
            self.current_pil_img = self.full_pil_img
            self._last_pil_img = self.full_pil_img
            self._last_cut_lines = ()

        zoom_factor = self.store.state.zoom_factor
        pan_x, pan_y = self.store.state.pan_offset

        workspace_state = self.store.state.workspace_state
        state_revision = workspace_state.revision if workspace_state else 0
        workspace_changed = (state_revision != getattr(self, "_last_workspace_revision", None))
        self._last_workspace_revision = state_revision

        parent_stack_tuple = tuple(parent_stack) if parent_stack else ()
        state_key = (zoom_factor, id(self.current_pil_img), parent_stack_tuple, cut_lines_tuple)

        image_rebuilt = False
        if state_key != getattr(self, "_zoom_cached_key", None) or self.image_item_id is None:
            self._zoom_cached_key = state_key
            image_rebuilt = True

            masked = self._apply_full_parent_mask(self.current_pil_img)

            scaled_w = round(masked.width * zoom_factor)
            scaled_h = round(masked.height * zoom_factor)
            if scaled_w > 0 and scaled_h > 0:
                resized = masked.resize(
                    (scaled_w, scaled_h), Image.Resampling.BILINEAR
                )
                self._zoom_cached_photo = ImageTk.PhotoImage(resized)

                if self.image_item_id is not None:
                    self.delete(self.image_item_id)

                self.image_item_id = self.create_image(
                    pan_x, pan_y, image=self._zoom_cached_photo, anchor="nw"
                )
                self.tag_lower(self.image_item_id)

            self._last_pan_offset = (pan_x, pan_y)

        if image_rebuilt or workspace_changed:
            self.draw_boxes()
        else:
            dx = pan_x - self._last_pan_offset[0]
            dy = pan_y - self._last_pan_offset[1]
            if dx != 0 or dy != 0:
                if self.image_item_id is not None:
                    self.coords(self.image_item_id, pan_x, pan_y)
                self.move("ann", dx, dy)
                self._last_pan_offset = (pan_x, pan_y)

    def _apply_full_parent_mask(self, base_img: Image.Image) -> Image.Image:
        state = self.store.state.workspace_state
        parent_stack = self.store.state.parent_stack
        if not parent_stack or not state:
            return base_img
        parent_id = parent_stack[-1]
        parent = state.components.get(parent_id)
        if not parent:
            return base_img

        img_w = base_img.width
        img_h = base_img.height
        mask_key = (parent_id, img_w, img_h)

        if self._mask_cached_key != mask_key or self._mask_cached_img is None:
            mask = Image.new("L", (img_w, img_h), 80)
            draw = ImageDraw.Draw(mask)
            b = parent.bounds
            draw.rectangle([b.left, b.top, b.right, b.bottom], fill=255)
            self._mask_cached_img = mask
            self._mask_cached_key = mask_key

        bg = Image.new("RGB", base_img.size, (18, 18, 18))
        return Image.composite(base_img, bg, self._mask_cached_img)

    def draw_boxes(self):
        self.delete("ann")
        state = self.store.state.workspace_state
        if not state:
            return

        zoom_factor = self.store.state.zoom_factor
        pan_offset = self.store.state.pan_offset
        parent_stack = self.store.state.parent_stack
        cut_lines = state.cutLines
        selected_boxes = [
            state.components[uid]
            for uid in self.store.state.selected_component_ids
            if uid in state.components
        ]

        active_int = self.store.state.active_interaction

        if (
            self.gestures.resize_handle
            and self.gestures.is_dragging
            and len(selected_boxes) == 1
        ):
            active_box = selected_boxes[0]
            union = self._get_children_bounds_union(active_box)
            if union:
                cx1, cy1, cx2, cy2 = union
                gcx1, gcy1 = self.transformer.to_canvas(
                    cx1, cy1, zoom_factor, parent_stack, cut_lines, pan_offset=pan_offset
                )
                gcx2, gcy2 = self.transformer.to_canvas(
                    cx2, cy2, zoom_factor, parent_stack, cut_lines, pan_offset=pan_offset
                )
                self.create_rectangle(
                    gcx1,
                    gcy1,
                    gcx2,
                    gcy2,
                    outline="#888888",
                    width=2,
                    dash=(4, 4),
                    tags="ann",
                )
                self.create_text(
                    gcx1 + 4,
                    gcy1 + 4,
                    text="Child Bounds",
                    fill="#888888",
                    anchor="nw",
                    font=("Arial", 9, "italic"),
                    tags="ann",
                )

        boxes = self._active_boxes()
        non_selected = [b for b in boxes if b not in selected_boxes]
        selected = [b for b in boxes if b in selected_boxes]
        ordered_boxes = non_selected + selected

        for box in ordered_boxes:
            if not getattr(box.visibility, "visible", True):
                continue

            is_sel = box in selected_boxes
            color = "#0c8ce9" if is_sel else "#ff4444"

            parent_id = parent_stack[-1] if parent_stack else None
            parent = state.components.get(parent_id) if parent_id else None
            full_w = self.full_pil_img.width if self.full_pil_img else 1
            abs_font_size = compute_pill_font_size(parent, full_w)
            abs_box_border, abs_pill_outline = compute_border_widths(parent, full_w)
            font_obj = get_font(abs_font_size)

            base_lw = max(1, round(abs_box_border * zoom_factor))
            lw = base_lw + 1 if is_sel else base_lw

            bounds = active_int.get(box.id) if active_int else None
            if bounds is None:
                bounds = box.bounds

            cx1, cy1 = self.transformer.to_canvas(
                bounds.left,
                bounds.top,
                zoom_factor,
                parent_stack,
                cut_lines,
                pan_offset=pan_offset,
            )
            cx2, cy2 = self.transformer.to_canvas(
                bounds.right,
                bounds.bottom,
                zoom_factor,
                parent_stack,
                cut_lines,
                pan_offset=pan_offset,
            )

            rect_kwargs = {"outline": color, "width": lw, "tags": "ann"}
            if getattr(box.visibility, "locked", False):
                rect_kwargs["dash"] = (4, 4)
            self.create_rectangle(cx1, cy1, cx2, cy2, **rect_kwargs)

            num = str(box.number)
            if num:
                tw, th, _top = get_text_dimensions(None, num, font_obj)
                pad_x, pad_y = compute_pill_padding(abs_font_size)

                pill_w = max(4, round((tw + pad_x) * zoom_factor))
                pill_h = max(4, round((th + pad_y) * zoom_factor))
                canvas_font_size = max(
                    4, min(72, round(abs_font_size * zoom_factor))
                )

                pill_corner = getattr(box.style, "pillCorner", "top_left")
                pill_x, pill_y = get_pill_coords(
                    cx1, cy1, cx2, cy2, pill_w, pill_h, pill_corner
                )
                pill_outline_w = max(1, round(abs_pill_outline * zoom_factor))

                self.create_rectangle(
                    pill_x,
                    pill_y,
                    pill_x + pill_w,
                    pill_y + pill_h,
                    fill="white",
                    outline=color,
                    width=pill_outline_w,
                    tags="ann",
                )
                self.create_text(
                    pill_x + (pill_w / 2),
                    pill_y + (pill_h / 2),
                    text=num,
                    fill=color,
                    font=("Arial", canvas_font_size, "bold"),
                    tags="ann",
                )

            if self.show_labels and box.label:
                self.create_text(
                    cx1,
                    cy2 + 4,
                    text=box.label,
                    anchor="nw",
                    fill=color,
                    font=("", 9),
                    tags="ann",
                )

        if len(selected_boxes) == 1:
            selected_box = selected_boxes[0]
            if getattr(selected_box.visibility, "visible", True) and not getattr(
                selected_box.visibility, "locked", False
            ):
                self._draw_handles(selected_box)

        if self.image_item_id is not None:
            self.tag_lower(self.image_item_id)

    def _draw_handles(self, box: Component):
        zoom_factor = self.store.state.zoom_factor
        pan_offset = self.store.state.pan_offset
        parent_stack = self.store.state.parent_stack
        cut_lines = (
            self.store.state.workspace_state.cutLines
            if self.store.state.workspace_state
            else []
        )
        active_int = self.store.state.active_interaction
        bounds = active_int.get(box.id) if active_int else None
        if bounds is None:
            bounds = box.bounds

        cx1, cy1 = self.transformer.to_canvas(
            bounds.left, bounds.top, zoom_factor, parent_stack, cut_lines, pan_offset=pan_offset
        )
        cx2, cy2 = self.transformer.to_canvas(
            bounds.right,
            bounds.bottom,
            zoom_factor,
            parent_stack,
            cut_lines,
            pan_offset=pan_offset
        )
        mx, my = (cx1 + cx2) / 2, (cy1 + cy2) / 2
        hs = 5

        for hx, hy in [
            (cx1, cy1),
            (mx, cy1),
            (cx2, cy1),
            (cx1, my),
            (cx2, my),
            (cx1, cy2),
            (mx, cy2),
            (cx2, cy2),
        ]:
            self.create_rectangle(
                hx - hs,
                hy - hs,
                hx + hs,
                hy + hs,
                fill="white",
                outline="#0c8ce9",
                width=1.5,
                tags="ann",
            )

    def _active_boxes(self) -> list[Component]:
        state = self.store.state.workspace_state
        if not state:
            return []
        parent_stack = self.store.state.parent_stack
        if parent_stack:
            pid = parent_stack[-1]
            parent = state.components.get(pid)
            if parent:
                return [
                    state.components[cid]
                    for cid in parent.childrenIds
                    if cid in state.components
                ]
        return [
            state.components[rid]
            for rid in state.rootComponents
            if rid in state.components
        ]

    def _get_children_bounds_union(
        self, box: Component
    ) -> tuple[int, int, int, int] | None:
        state = self.store.state.workspace_state
        if not state or not box.childrenIds:
            return None
        valid_children = [
            state.components[cid] for cid in box.childrenIds if cid in state.components
        ]
        if not valid_children:
            return None
        left = min(c.bounds.left for c in valid_children)
        top = min(c.bounds.top for c in valid_children)
        right = max(c.bounds.right for c in valid_children)
        bottom = max(c.bounds.bottom for c in valid_children)
        return left, top, right, bottom

    def on_click(self, event):
        cx = self.canvasx(event.x)
        cy = self.canvasy(event.y)
        self.gestures.on_click(self, event, cx, cy)

    def on_drag(self, event):
        cx = self.canvasx(event.x)
        cy = self.canvasy(event.y)
        self.gestures.on_drag(self, event, cx, cy)

    def on_release(self, event):
        cx = self.canvasx(event.x)
        cy = self.canvasy(event.y)
        self.gestures.on_release(self, event, cx, cy)

    def on_mouse_move(self, event):
        cx = self.canvasx(event.x)
        cy = self.canvasy(event.y)
        self.gestures.on_mouse_move(self, event, cx, cy)

    def on_right_click(self, event):
        cx = self.canvasx(event.x)
        cy = self.canvasy(event.y)
        self.gestures.on_right_click(self, event, cx, cy)

    def _on_control_click(self, event):
        cx = self.canvasx(event.x)
        cy = self.canvasy(event.y)
        self.gestures.on_control_click(self, event, cx, cy)

    def _on_scroll(self, event):
        self.gestures.on_scroll(self, event)
        return "break"

    def _on_canvas_touchpad_scroll(self, event):
        return self.gestures.on_touchpad_scroll(self, event)

    def zoom(self, delta: float, mouse_pos: tuple[int, int] | None = None):
        self.gestures.zoom(self, delta, mouse_pos)

    def zoom_focus_target(self):
        state = self.store.state.workspace_state
        selected_boxes = [
            state.components[uid]
            for uid in self.store.state.selected_component_ids
            if uid in state.components
        ]
        if len(selected_boxes) != 1:
            return
        box = selected_boxes[0]

        cw = self.winfo_width()
        ch = self.winfo_height()
        parent_stack = self.store.state.parent_stack
        cut_lines = state.cutLines if state else []

        cx, cy = self.transformer.to_canvas(
            (box.bounds.left + box.bounds.right) / 2,
            (box.bounds.top + box.bounds.bottom) / 2,
            1.0,
            parent_stack,
            cut_lines,
        )

        zoom_factor = 2.0
        scroll_x = (cw / 2) - cx * zoom_factor
        scroll_y = (ch / 2) - cy * zoom_factor
        self.store.update_state("viewport", zoom_factor=zoom_factor, pan_offset=(scroll_x, scroll_y))

    def set_mode(self, mode: str):
        self.store.update_state("viewport", current_mode=mode)
        if mode == "pan":
            self.config(cursor=self._get_pan_cursor(active=False))
        elif mode == "draw":
            self.config(cursor="crosshair")
        else:
            self.config(cursor="")

    def _get_pan_cursor(self, active: bool = False) -> str:
        if sys.platform == "darwin":
            return "closedhand" if active else "openhand"
        return "fleur" if active else "hand2"

    def start_space_pan(self):
        self._space_pan_active = True
        self.config(cursor=self._get_pan_cursor(active=False))

    def stop_space_pan(self):
        self._space_pan_active = False
        self.gestures.space_panning = False
        mode = self.store.state.current_mode
        if mode == "draw":
            self.config(cursor="crosshair")
        else:
            self.config(cursor="")

    def set_selection(self, boxes: list[Component]):
        ids = [b.id for b in boxes]
        self.store.update_state("selection", selected_component_ids=ids)
        if self.on_selection_changed:
            self.on_selection_changed(boxes)

    def drill_into(self, comp_id: UUID):
        stack = list(self.store.state.parent_stack)
        stack.append(comp_id)
        self.store.update_state(
            "viewport", parent_stack=stack, selected_component_ids=[], active_interaction=None
        )
        self._mask_cached_img = None
        self._mask_cached_key = None
        self._last_pil_img = None
        if self.on_drill_into:
            self.on_drill_into(comp_id)

    def drill_out(self):
        stack = list(self.store.state.parent_stack)
        if stack:
            popped = stack.pop()
            self.store.update_state(
                "viewport", parent_stack=stack, selected_component_ids=[popped], active_interaction=None
            )
            self._mask_cached_img = None
            self._mask_cached_key = None
            self._last_pil_img = None
            if self.on_drill_out:
                self.on_drill_out()

    def nudge_selection(self, dx: int, dy: int):
        state = self.store.state.workspace_state
        selected_boxes = [
            state.components[uid]
            for uid in self.store.state.selected_component_ids
            if uid in state.components
        ]
        if not selected_boxes:
            return

        moved_any = False
        for box in selected_boxes:
            if getattr(box.visibility, "locked", False):
                continue
            box.bounds.x = int(box.bounds.x + dx)
            box.bounds.y = int(box.bounds.y + dy)
            self.last_moved_component = (box, int(box.bounds.x), int(box.bounds.y))
            self.event_generate("<<ComponentMoved>>")
            moved_any = True
        if moved_any:
            self.draw_boxes()

    def toggle_labels_visibility(self):
        self.show_labels = not self.show_labels
        self.draw_boxes()

    def on_canvas_resize(self, event):
        cw = self.winfo_width()
        ch = self.winfo_height()
        if self.welcome_screen:
            self.coords("welcome", cw / 2, ch / 2)
            return

        if not self.full_pil_img:
            return

        self.store.update_state("viewport", viewport_size=(cw, ch))
