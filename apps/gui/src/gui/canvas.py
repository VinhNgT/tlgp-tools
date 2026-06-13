import sys
import time
import tkinter as tk

from models import Component, WorkspaceState
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

from .api_client import EngineClient

logger = get_logger(__name__)


class AnnotationCanvas(tk.Canvas):
    """
    AnnotationCanvas handles visual rendering of screenshot images and annotation boxes,
    along with zoom, pan, select, resize, and draw interactions.

    Coordinates are stored and manipulated in absolute image space.
    """

    def __init__(self, parent, client: EngineClient, **kwargs):
        kwargs.setdefault("bg", "#121212")
        super().__init__(parent, **kwargs)
        self.client = client

        # Navigation & View States
        self.parent_stack: list[str] = []  # List of UUID strings
        self.zoom_factor: float = 1.0
        self._rendered_zoom_factor: float = 1.0
        self.mode: str = "select"
        self.prev_mode_before_space: str | None = None
        self.selected_boxes: list[Component] = []
        self.show_labels: bool = True

        # Interaction & Drag States
        self._is_dragging: bool = False
        self._drag_mouse_start_abs: tuple[int, int] | None = None
        self._drag_mouse_start_canvas: tuple[int, int] = (0, 0)
        self._drag_orig_coords: dict[str, tuple[Component, int, int, int, int]] = {}
        self._drag_orig_x1: int = 0
        self._drag_orig_y1: int = 0
        self._drag_orig_x2: int = 0
        self._drag_orig_y2: int = 0
        self.resize_handle: str | None = None
        self.temp_rect_id = None
        self.draw_start_x = None
        self.draw_start_y = None

        # Image References & Buffers
        self.full_pil_img: Image.Image | None = None
        self.current_pil_img: Image.Image | None = None
        self.tk_photo = None
        self._prev_tk_photo = None
        self.image_item_id = None

        # Viewport Cropping State
        self._is_active_interaction: bool = False
        self._active_interaction_timer: str | None = None
        self._redraw_pending: bool = False
        self._pending_center_abs: tuple[float, float] | None = None
        self._pending_viewport_pos: tuple[float, float] | None = None
        self.scroll_x: float = 0.0
        self.scroll_y: float = 0.0

        # Hover & Cycle selection trackers
        self._last_click_time = 0.0
        self._last_click_cx = 0.0
        self._last_click_cy = 0.0
        self._cycle_boxes = None
        self._last_cycle_index = -1
        self._click_sequence_count = 0

        # Bindings
        self.bind("<ButtonPress-1>", self.on_click)
        self.bind("<B1-Motion>", self.on_drag)
        self.bind("<ButtonRelease-1>", self.on_release)
        self.bind("<Motion>", self.on_mouse_move)

        # Context Menu
        self.context_menu = tk.Menu(self, tearoff=0)
        self.bind("<Button-3>", self.show_context_menu)

        # Pan with middle mouse button
        self.bind("<ButtonPress-2>", self._start_pan_event)
        self.bind("<B2-Motion>", self._pan_event)
        self.bind("<ButtonRelease-2>", self._stop_pan_event)

        # Arrow key movements
        self.bind("<Up>", lambda e: self._move_box_by_keys(0, -1))
        self.bind("<Down>", lambda e: self._move_box_by_keys(0, 1))
        self.bind("<Left>", lambda e: self._move_box_by_keys(-1, 0))
        self.bind("<Right>", lambda e: self._move_box_by_keys(1, 0))

        self.bind("<Shift-Up>", lambda e: self._move_box_by_keys(0, -10))
        self.bind("<Shift-Down>", lambda e: self._move_box_by_keys(0, 10))
        self.bind("<Shift-Left>", lambda e: self._move_box_by_keys(-10, 0))
        self.bind("<Shift-Right>", lambda e: self._move_box_by_keys(10, 0))

        self.bind("<Configure>", self.on_canvas_resize)
        self.config(takefocus=True, highlightthickness=0, borderwidth=0)

    # ── Image and Viewport Management ───────────────────────────────────

    def set_background_image(self, img: Image.Image):
        self.full_pil_img = img
        self.update_view()

    def render_state(self, state: WorkspaceState):
        """Re-renders canvas components based on server state changes."""
        self.draw_boxes()

    def update_view(
        self,
        center_abs: tuple[float, float] | None = None,
        target_viewport_pos: tuple[float, float] | None = None,
    ):
        if not self.full_pil_img:
            return

        parent_id = self.parent_stack[-1] if self.parent_stack else None
        if parent_id and self.client.state:
            parent = self.client.state.components.get(parent_id)
            if parent:
                # Dim everything outside the current parent box
                b = parent.bounds
                left, top, right, bottom = b.left, b.top, b.right, b.bottom
                mask = Image.new("RGBA", self.full_pil_img.size, (0, 0, 0, 140))
                draw = ImageDraw.Draw(mask)
                draw.rectangle([left, top, right, bottom], fill=(0, 0, 0, 0))
                base = self.full_pil_img.convert("RGBA")
                self.current_pil_img = Image.alpha_composite(base, mask).convert("RGB")
            else:
                self.current_pil_img = self.full_pil_img
        else:
            self.current_pil_img = self.full_pil_img

        vw = self.winfo_width()
        vh = self.winfo_height()
        if vw <= 1 or vh <= 1:
            vw = 1000
            vh = 700

        if center_abs is None:
            self.update_idletasks()
            img_w = self.current_pil_img.width
            img_h = self.current_pil_img.height
            if vw > 40 and vh > 40:
                fit_w = (vw - 40) / img_w
                fit_h = (vh - 40) / img_h
                self.zoom_factor = max(0.1, min(1.0, min(fit_w, fit_h)))

        if center_abs is not None:
            norm_x, norm_y = center_abs
            new_cx = norm_x * self.zoom_factor
            new_cy = norm_y * self.zoom_factor
            tx, ty = (
                target_viewport_pos
                if target_viewport_pos is not None
                else (vw / 2, vh / 2)
            )
            new_left = new_cx - tx
            new_top = new_cy - ty
        else:
            self.update_idletasks()
            center_x = self.current_pil_img.width / 2
            center_y = self.current_pil_img.height / 2
            new_cx = center_x * self.zoom_factor
            new_cy = center_y * self.zoom_factor
            new_left = new_cx - vw / 2
            new_top = new_cy - vh / 2

        img_x1 = new_left / self.zoom_factor
        img_y1 = new_top / self.zoom_factor
        img_x2 = (new_left + vw) / self.zoom_factor
        img_y2 = (new_top + vh) / self.zoom_factor

        buffer_w = 500.0 / self.zoom_factor
        buffer_h = 500.0 / self.zoom_factor

        crop_x1 = max(0, round(img_x1 - buffer_w))
        crop_y1 = max(0, round(img_y1 - buffer_h))
        crop_x2 = min(self.current_pil_img.width, round(img_x2 + buffer_w))
        crop_y2 = min(self.current_pil_img.height, round(img_y2 + buffer_h))

        if crop_x2 <= crop_x1:
            crop_x2 = crop_x1 + 1
        if crop_y2 <= crop_y1:
            crop_y2 = crop_y1 + 1

        new_crop = (crop_x1, crop_y1, crop_x2, crop_y2)

        self._rendered_crop = new_crop
        self._resized_image_zoom_factor = self.zoom_factor
        cropped_img = self.current_pil_img.crop(new_crop)

        img_cx = crop_x1 * self.zoom_factor
        img_cy = crop_y1 * self.zoom_factor

        w_crop = max(1, round((crop_x2 - crop_x1) * self.zoom_factor))
        h_crop = max(1, round((crop_y2 - crop_y1) * self.zoom_factor))

        resampler = (
            Image.Resampling.BILINEAR
            if self.zoom_factor > 1.0
            else Image.Resampling.LANCZOS
        )
        resized = cropped_img.resize((w_crop, h_crop), resampler)
        self._prev_tk_photo = self.tk_photo
        self.tk_photo = ImageTk.PhotoImage(resized)

        if self.image_item_id is None:
            self.image_item_id = self.create_image(
                img_cx, img_cy, anchor="nw", image=self.tk_photo
            )
        else:
            self.itemconfig(self.image_item_id, image=self.tk_photo)
            self.coords(self.image_item_id, img_cx, img_cy)

        margin_x = 2000
        margin_y = 2000
        w = max(1, round(self.current_pil_img.width * self.zoom_factor))
        h = max(1, round(self.current_pil_img.height * self.zoom_factor))
        self.config(scrollregion=(-margin_x, -margin_y, w + margin_x, h + margin_y))

        frac_x = (new_left + margin_x) / (w + 2 * margin_x)
        frac_y = (new_top + margin_y) / (h + 2 * margin_y)

        self.xview_moveto(max(0.0, min(1.0, frac_x)))
        self.yview_moveto(max(0.0, min(1.0, frac_y)))

        self.scroll_x = new_left
        self.scroll_y = new_top
        self._rendered_zoom_factor = self.zoom_factor
        self.draw_boxes()

    def draw_boxes(self):
        self.delete("ann")
        if not self.client.state:
            return

        boxes = self._active_boxes()
        for box in boxes:
            is_sel = box in self.selected_boxes
            color = "#0c8ce9" if is_sel else "#ff4444"

            parent_id = self.parent_stack[-1] if self.parent_stack else None
            parent = self.client.state.components.get(parent_id) if parent_id else None
            full_w = self.full_pil_img.width if self.full_pil_img else 1
            abs_font_size = compute_pill_font_size(parent, full_w)
            abs_box_border, abs_pill_outline = compute_border_widths(parent, full_w)
            font_obj = get_font(abs_font_size)

            base_lw = max(1, round(abs_box_border * self._rendered_zoom_factor))
            lw = base_lw + 1 if is_sel else base_lw

            cx1, cy1 = self.to_canvas(box.bounds.left, box.bounds.top)
            cx2, cy2 = self.to_canvas(box.bounds.right, box.bounds.bottom)

            self.create_rectangle(
                cx1, cy1, cx2, cy2, outline=color, width=lw, tags="ann"
            )

            # Draw Number Pill
            num = str(box.number)
            tw, th, _top = get_text_dimensions(None, num, font_obj)
            pad_x, pad_y = compute_pill_padding(abs_font_size)

            pill_w = max(4, round((tw + pad_x) * self._rendered_zoom_factor))
            pill_h = max(4, round((th + pad_y) * self._rendered_zoom_factor))
            canvas_font_size = max(
                4, min(72, round(abs_font_size * self._rendered_zoom_factor))
            )

            pill_corner = getattr(box.style, "pillCorner", "top_left")
            pill_x, pill_y = get_pill_coords(
                cx1, cy1, cx2, cy2, pill_w, pill_h, pill_corner
            )
            pill_outline_w = max(
                1, round(abs_pill_outline * self._rendered_zoom_factor)
            )

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

            # Draw Label
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

        if len(self.selected_boxes) == 1:
            self._draw_handles(self.selected_boxes[0])

        if self.image_item_id is not None:
            self.tag_lower(self.image_item_id)

    def _draw_handles(self, box: Component):
        cx1, cy1 = self.to_canvas(box.bounds.left, box.bounds.top)
        cx2, cy2 = self.to_canvas(box.bounds.right, box.bounds.bottom)
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

    # ── Geometry and Transformations ───────────────────────────────────

    def to_canvas(self, abs_x: int, abs_y: int) -> tuple[float, float]:
        return (
            abs_x * self._rendered_zoom_factor,
            abs_y * self._rendered_zoom_factor,
        )

    def to_abs(self, cx: float, cy: float) -> tuple[int, int]:
        return (
            round(cx / self._rendered_zoom_factor),
            round(cy / self._rendered_zoom_factor),
        )

    def _boundary(self) -> tuple[int, int, int, int]:
        if self.full_pil_img:
            return 0, 0, self.full_pil_img.width, self.full_pil_img.height
        return 0, 0, 99999, 99999

    def _active_boxes(self) -> list[Component]:
        if not self.client.state:
            return []
        parent_id = self.parent_stack[-1] if self.parent_stack else None
        if parent_id is None:
            return [
                self.client.state.components[rid]
                for rid in self.client.state.rootComponents
                if rid in self.client.state.components
            ]
        else:
            parent = self.client.state.components.get(parent_id)
            if not parent:
                return []
            return [
                self.client.state.components[cid]
                for cid in parent.childrenIds
                if cid in self.client.state.components
            ]

    def _handle_positions(self, box: Component) -> dict[str, tuple[float, float]]:
        cx1, cy1 = self.to_canvas(box.bounds.left, box.bounds.top)
        cx2, cy2 = self.to_canvas(box.bounds.right, box.bounds.bottom)
        mx, my = (cx1 + cx2) / 2, (cy1 + cy2) / 2

        return {
            "tl": (cx1, cy1),
            "tm": (mx, cy1),
            "tr": (cx2, cy1),
            "ml": (cx1, my),
            "mr": (cx2, my),
            "bl": (cx1, cy2),
            "bm": (mx, cy2),
            "br": (cx2, cy2),
        }

    def _hit_handle(self, cx: float, cy: float) -> str | None:
        if len(self.selected_boxes) != 1:
            return None
        box = self.selected_boxes[0]
        for name, (hx, hy) in self._handle_positions(box).items():
            if abs(cx - hx) <= 7 and abs(cy - hy) <= 7:
                return name
        return None

    def _hit_box(self, cx: float, cy: float) -> Component | None:
        for box in reversed(self._active_boxes()):
            bx1, by1 = self.to_canvas(box.bounds.left, box.bounds.top)
            bx2, by2 = self.to_canvas(box.bounds.right, box.bounds.bottom)
            if bx1 <= cx <= bx2 and by1 <= cy <= by2:
                return box
        return None

    def _get_all_hit_boxes(self, cx: float, cy: float) -> list[Component]:
        hits = []
        for box in reversed(self._active_boxes()):
            bx1, by1 = self.to_canvas(box.bounds.left, box.bounds.top)
            bx2, by2 = self.to_canvas(box.bounds.right, box.bounds.bottom)
            if bx1 <= cx <= bx2 and by1 <= cy <= by2:
                hits.append(box)
        return hits

    # ── Interaction Events ──────────────────────────────────────────────

    def on_click(self, event):
        self.focus_set()
        cx = self.canvasx(event.x)
        cy = self.canvasy(event.y)

        if self.mode == "pan":
            self._start_pan_event(event)
            return

        now = time.time()
        is_multi = (event.state & 0x0001) or (event.state & 0x0004)
        hit_boxes = self._get_all_hit_boxes(cx, cy)
        primary_sel = self.selected_boxes[-1] if self.selected_boxes else None

        if (
            now - self._last_click_time < 0.5
            and abs(cx - self._last_click_cx) < 15
            and abs(cy - self._last_click_cy) < 15
            and primary_sel
            and primary_sel in hit_boxes
        ):
            self._click_sequence_count += 1
        else:
            self._click_sequence_count = 1
            self._cycle_boxes = None

        self._last_click_time = now
        self._last_click_cx = cx
        self._last_click_cy = cy

        if (
            (self._click_sequence_count % 2 == 0)
            and self.mode == "select"
            and not is_multi
        ):
            handle = self._hit_handle(cx, cy)
            if not handle:
                if self._cycle_boxes is None:
                    hit = self._get_all_hit_boxes(cx, cy)
                    if len(hit) > 1:
                        self._cycle_boxes = hit
                        self._last_cycle_index = (
                            hit.index(primary_sel) if primary_sel in hit else 0
                        )
                if self._cycle_boxes:
                    self._last_cycle_index = (self._last_cycle_index + 1) % len(
                        self._cycle_boxes
                    )
                    new_box = self._cycle_boxes[self._last_cycle_index]
                    self.set_selection([new_box])
                    self._begin_move(new_box, cx, cy, event)
                    return

        if self._click_sequence_count == 1:
            self._cycle_boxes = None

        if self.mode == "select":
            handle = self._hit_handle(cx, cy)
            if handle and len(self.selected_boxes) == 1:
                self._begin_resize(handle, event)
                return

            clicked = self._hit_box(cx, cy)
            if clicked:
                if is_multi:
                    if clicked in self.selected_boxes:
                        new_sel = [b for b in self.selected_boxes if b is not clicked]
                    else:
                        new_sel = list(self.selected_boxes) + [clicked]
                    self.set_selection(new_sel)
                    if clicked in new_sel:
                        self._begin_move(clicked, cx, cy, event)
                else:
                    self.set_selection([clicked])
                    self._begin_move(clicked, cx, cy, event)
                return

            if not is_multi:
                self.set_selection([])
            self.draw_start_x = cx
            self.draw_start_y = cy
            self.temp_rect_id = self.create_rectangle(
                cx, cy, cx, cy, outline="#0c8ce9", width=1.5, dash=(4, 4)
            )
            return

        if self.mode == "draw":
            self.draw_start_x = cx
            self.draw_start_y = cy
            self.temp_rect_id = self.create_rectangle(
                cx, cy, cx, cy, outline="#0c8ce9", width=2, dash=(4, 4)
            )

    def _begin_resize(self, handle: str, event=None):
        self.resize_handle = handle
        self._is_dragging = True
        box = self.selected_boxes[0]
        self._drag_orig_x1 = box.bounds.left
        self._drag_orig_y1 = box.bounds.top
        self._drag_orig_x2 = box.bounds.right
        self._drag_orig_y2 = box.bounds.bottom
        hx, hy = self._handle_positions(box)[handle]
        self._drag_mouse_start_abs = self.to_abs(hx, hy)

    def _begin_move(self, box: Component, cx: float, cy: float, event=None):
        self.resize_handle = None
        self._is_dragging = True
        self._drag_mouse_start_abs = self.to_abs(cx, cy)

        self._drag_orig_coords = {}
        for b in self.selected_boxes:
            self._drag_orig_coords[str(b.id)] = (
                b,
                b.bounds.left,
                b.bounds.top,
                b.bounds.right,
                b.bounds.bottom,
            )

        primary = self.selected_boxes[-1]
        self._drag_orig_x1 = primary.bounds.left
        self._drag_orig_y1 = primary.bounds.top
        self._drag_orig_x2 = primary.bounds.right
        self._drag_orig_y2 = primary.bounds.bottom
        self.draw_boxes()

    def on_drag(self, event):
        cx = self.canvasx(event.x)
        cy = self.canvasy(event.y)

        if self.mode == "pan":
            self._pan_event(event)
            return

        bx1, by1, bx2, by2 = self._boundary()

        if (self.mode == "draw" or self.mode == "select") and self.temp_rect_id:
            ax, ay = self.to_abs(self.draw_start_x, self.draw_start_y)
            bx, by = self.to_abs(cx, cy)
            ax = max(bx1, min(bx2, ax))
            ay = max(by1, min(by2, ay))
            bx = max(bx1, min(bx2, bx))
            by = max(by1, min(by2, by))
            sx, sy = self.to_canvas(ax, ay)
            ex, ey = self.to_canvas(bx, by)
            self.coords(self.temp_rect_id, sx, sy, ex, ey)
            return

        if self.mode == "select" and self._is_dragging and self.selected_boxes:
            mouse_abs = self.to_abs(cx, cy)
            start_abs = self._drag_mouse_start_abs
            dx = mouse_abs[0] - start_abs[0]
            dy = mouse_abs[1] - start_abs[1]

            if self.resize_handle:
                self._apply_resize(dx, dy, bx1, by1, bx2, by2)
            else:
                self._apply_move_multiple(dx, dy, bx1, by1, bx2, by2)

    def _apply_resize(self, dx: int, dy: int, bx1: int, by1: int, bx2: int, by2: int):
        box = self.selected_boxes[0]
        ox1, oy1 = self._drag_orig_x1, self._drag_orig_y1
        ox2, oy2 = self._drag_orig_x2, self._drag_orig_y2
        h = self.resize_handle

        nx1, ny1, nx2, ny2 = ox1, oy1, ox2, oy2
        if "l" in h:
            nx1 = ox1 + dx
        if "r" in h:
            nx2 = ox2 + dx
        if "t" in h:
            ny1 = oy1 + dy
        if "b" in h:
            ny2 = oy2 + dy

        nx1 = max(bx1, min(bx2, nx1))
        ny1 = max(by1, min(by2, ny1))
        nx2 = max(bx1, min(bx2, nx2))
        ny2 = max(by1, min(by2, ny2))

        # Visual update directly
        box.bounds.x = min(nx1, nx2)
        box.bounds.y = min(ny1, ny2)
        box.bounds.w = abs(nx2 - nx1)
        box.bounds.h = abs(ny2 - ny1)
        self.draw_boxes()

    def _apply_move_multiple(
        self, dx: int, dy: int, bx1: int, by1: int, bx2: int, by2: int
    ):
        for _bid, (box, ox1, oy1, ox2, oy2) in self._drag_orig_coords.items():
            w = ox2 - ox1
            h = oy2 - oy1
            nx1 = ox1 + dx
            ny1 = oy1 + dy

            # Bounds clamping
            nx1 = max(bx1, min(bx2 - w, nx1))
            ny1 = max(by1, min(by2 - h, ny1))

            box.bounds.x = nx1
            box.bounds.y = ny1
            box.bounds.w = w
            box.bounds.h = h
        self.draw_boxes()

    def on_release(self, event):
        if self.mode == "pan":
            self.config(cursor=self._get_pan_cursor(active=False))
            return

        if self.mode == "select":
            if self.temp_rect_id:
                cx = self.canvasx(event.x)
                cy = self.canvasy(event.y)
                self.delete(self.temp_rect_id)
                self.temp_rect_id = None

                bx1, by1, bx2, by2 = self._boundary()
                ax1, ay1 = self.to_abs(self.draw_start_x, self.draw_start_y)
                ax2, ay2 = self.to_abs(cx, cy)

                left = max(bx1, min(bx2, min(ax1, ax2)))
                top = max(by1, min(by2, min(ay1, ay2)))
                right = max(bx1, min(bx2, max(ax1, ax2)))
                bot = max(by1, min(by2, max(ay1, ay2)))

                if (right - left) > 3 or (bot - top) > 3:
                    intersected = []
                    for box in self._active_boxes():
                        if (
                            box.bounds.left < right
                            and box.bounds.right > left
                            and box.bounds.top < bot
                            and box.bounds.bottom > top
                        ):
                            intersected.append(box)

                    is_multi = (event.state & 0x0001) or (event.state & 0x0004)
                    if is_multi:
                        new_sel = list(self.selected_boxes)
                        for box in intersected:
                            if box not in new_sel:
                                new_sel.append(box)
                        self.set_selection(new_sel)
                    else:
                        self.set_selection(intersected)

            elif self._is_dragging:
                # Commit updates to server
                for _bid, (box, ox1, oy1, ox2, oy2) in self._drag_orig_coords.items():
                    if (
                        box.bounds.left != ox1
                        or box.bounds.top != oy1
                        or box.bounds.right != ox2
                        or box.bounds.bottom != oy2
                    ):
                        # Send absolute coordinate update to backend
                        self.client.update_component(
                            str(box.id),
                            bounds={
                                "x": int(box.bounds.x),
                                "y": int(box.bounds.y),
                                "w": int(box.bounds.w),
                                "h": int(box.bounds.h),
                            },
                        )

        elif self.mode == "draw" and self.temp_rect_id:
            cx = self.canvasx(event.x)
            cy = self.canvasy(event.y)
            self.delete(self.temp_rect_id)
            self.temp_rect_id = None

            if abs(cx - self.draw_start_x) > 5 and abs(cy - self.draw_start_y) > 5:
                bx1, by1, bx2, by2 = self._boundary()
                ax1, ay1 = self.to_abs(self.draw_start_x, self.draw_start_y)
                ax2, ay2 = self.to_abs(cx, cy)
                left = max(bx1, min(bx2, min(ax1, ax2)))
                top = max(by1, min(by2, min(ay1, ay2)))
                right = max(bx1, min(bx2, max(ax1, ax2)))
                bot = max(by1, min(by2, max(ay1, ay2)))

                if right - left > 3 and bot - top > 3:
                    active_parent_id = (
                        self.parent_stack[-1] if self.parent_stack else None
                    )
                    self.client.add_component(
                        label="Component",
                        bounds={
                            "x": int(left),
                            "y": int(top),
                            "w": int(right - left),
                            "h": int(bot - top),
                        },
                        parent_id=active_parent_id,
                    )

            self.set_mode("select")

        self._is_dragging = False
        self.resize_handle = None

    def on_mouse_move(self, event):
        if self.mode == "pan":
            is_dragging = (event.state & 0x0700) != 0
            self.config(cursor=self._get_pan_cursor(active=is_dragging))
            return

        cx = self.canvasx(event.x)
        cy = self.canvasy(event.y)

        if (
            self.mode == "select"
            and len(self.selected_boxes) == 1
            and not self._is_dragging
        ):
            handle = self._hit_handle(cx, cy)
            if handle:
                cursors = (
                    {
                        "tl": "resizetopleft",
                        "br": "resizebottomright",
                        "tr": "resizetopright",
                        "bl": "resizebottomleft",
                        "tm": "resizeupdown",
                        "bm": "resizeupdown",
                        "ml": "resizeleftright",
                        "mr": "resizeleftright",
                    }
                    if sys.platform == "darwin"
                    else {
                        "tl": "size_nw_se",
                        "br": "size_nw_se",
                        "tr": "size_ne_sw",
                        "bl": "size_ne_sw",
                        "tm": "size_ns",
                        "bm": "size_ns",
                        "ml": "size_we",
                        "mr": "size_we",
                    }
                )
                self.config(cursor=cursors.get(handle, ""))
                return

        self.config(cursor="crosshair" if self.mode == "draw" else "")

    # ── Panning & Zooming ────────────────────────────────────────────────

    def _start_pan_event(self, event):
        self.config(cursor=self._get_pan_cursor(active=True))
        self.scan_mark(event.x, event.y)

    def _pan_event(self, event):
        self._start_active_interaction()
        self.scan_dragto(event.x, event.y, gain=1)
        self.check_viewport_crop()

    def _stop_pan_event(self, event):
        if self.mode == "pan":
            self.config(cursor=self._get_pan_cursor(active=False))

    def check_viewport_crop(self):
        if not self.full_pil_img or not hasattr(self, "_rendered_crop"):
            return

        cx1 = self.canvasx(0)
        cy1 = self.canvasy(0)
        self.scroll_x = float(cx1)
        self.scroll_y = float(cy1)

        vw = self.winfo_width()
        vh = self.winfo_height()
        if vw <= 1 or vh <= 1:
            return

        cx2 = cx1 + vw
        cy2 = cy1 + vh

        img_x1 = cx1 / self._rendered_zoom_factor
        img_y1 = cy1 / self._rendered_zoom_factor
        img_x2 = cx2 / self._rendered_zoom_factor
        img_y2 = cy2 / self._rendered_zoom_factor

        rc_x1, rc_y1, rc_x2, rc_y2 = self._rendered_crop
        margin = (
            20.0 if self._is_active_interaction else 50.0
        ) / self._rendered_zoom_factor

        out_left = (img_x1 < rc_x1 + margin) and (rc_x1 > 0)
        out_top = (img_y1 < rc_y1 + margin) and (rc_y1 > 0)
        out_right = (img_x2 > rc_x2 - margin) and (rc_x2 < self.current_pil_img.width)
        out_bottom = (img_y2 > rc_y2 - margin) and (rc_y2 < self.current_pil_img.height)

        if out_left or out_top or out_right or out_bottom:
            self.update_view()

    def zoom(self, delta: float, mouse_pos: tuple[int, int] | None = None):
        vw = self.winfo_width()
        vh = self.winfo_height()
        mx, my = mouse_pos if mouse_pos else (vw / 2, vh / 2)

        cx = self.scroll_x + mx
        cy = self.scroll_y + my

        norm_x = cx / self._rendered_zoom_factor
        norm_y = cy / self._rendered_zoom_factor

        if delta > 0:
            factor = 1.1 ** (delta / 0.1)
            self.zoom_factor = min(10.0, self.zoom_factor * factor)
        else:
            factor = 1.1 ** (abs(delta) / 0.1)
            self.zoom_factor = max(0.05, self.zoom_factor / factor)

        new_cx = norm_x * self.zoom_factor
        new_cy = norm_y * self.zoom_factor
        self.scroll_x = new_cx - mx
        self.scroll_y = new_cy - my
        self._rendered_zoom_factor = self.zoom_factor

        self._start_active_interaction()
        self.update_view(center_abs=(norm_x, norm_y), target_viewport_pos=(mx, my))

    def zoom_focus_target(self):
        target_boxes = []
        if self.selected_boxes:
            target_boxes = self.selected_boxes
        elif self.parent_stack:
            parent = self.client.state.components.get(self.parent_stack[-1])
            if parent:
                target_boxes = [parent]

        vw = self.winfo_width()
        vh = self.winfo_height()
        if vw <= 1 or vh <= 1:
            vw, vh = 1000, 700

        if target_boxes:
            left = min(b.bounds.left for b in target_boxes)
            top = min(b.bounds.top for b in target_boxes)
            right = max(b.bounds.right for b in target_boxes)
            bottom = max(b.bounds.bottom for b in target_boxes)

            box_w = max(1, right - left)
            box_h = max(1, bottom - top)

            fit_w = (vw - 120.0) / box_w
            fit_h = (vh - 120.0) / box_h

            self.zoom_factor = max(0.05, min(3.0, min(fit_w, fit_h)))
            self.update_view(center_abs=((left + right) / 2.0, (top + bottom) / 2.0))
        else:
            self.update_view()

    def set_mode(self, mode: str):
        self._is_dragging = False
        self.mode = mode
        if mode == "pan":
            self.config(cursor=self._get_pan_cursor(active=False))
        elif mode == "draw":
            self.config(cursor="crosshair")
        else:
            self.config(cursor="")
        self.draw_boxes()

    def _get_pan_cursor(self, active: bool = False) -> str:
        return (
            "closedhand"
            if active and sys.platform == "darwin"
            else ("openhand" if sys.platform == "darwin" else "fleur")
        )

    def _start_active_interaction(self):
        self._is_active_interaction = True
        if self._active_interaction_timer is not None:
            self.after_cancel(self._active_interaction_timer)
        self._active_interaction_timer = self.after(150, self._stop_active_interaction)

    def _stop_active_interaction(self):
        self._active_interaction_timer = None
        if self._is_active_interaction:
            self._is_active_interaction = False
            self.update_view()

    def start_space_pan(self):
        if self.mode != "pan":
            self.prev_mode_before_space = self.mode
            self.set_mode("pan")

    def stop_space_pan(self):
        if self.mode == "pan" and self.prev_mode_before_space is not None:
            self.set_mode(self.prev_mode_before_space)
            self.prev_mode_before_space = None

    # ── Selection and Event Communication ───────────────────────────────

    def set_selection(self, boxes: list[Component]):
        self.selected_boxes = boxes
        self.draw_boxes()
        # Trigger any GUI callbacks if registered
        parent_app = self.winfo_toplevel()
        if hasattr(parent_app, "on_canvas_select"):
            parent_app.on_canvas_select(boxes[-1] if boxes else None)

    def on_canvas_resize(self, event):
        if self.full_pil_img:
            self.update_view()

    def show_context_menu(self, event):
        cx = self.canvasx(event.x)
        cy = self.canvasy(event.y)
        clicked = self._hit_box(cx, cy)

        self.context_menu.delete(0, tk.END)

        if clicked:
            self.set_selection([clicked])
            self.context_menu.add_command(
                label=f"Drill into Component {clicked.number}",
                command=lambda: self.drill_into(clicked.id),
            )
            self.context_menu.add_separator()

        self.context_menu.add_command(
            label="Focus Target", command=self.zoom_focus_target
        )
        self.context_menu.add_command(
            label="Toggle Labels (T)", command=self.toggle_labels_visibility
        )
        self.context_menu.post(event.x_root, event.y_root)

    def drill_into(self, comp_id):
        self.parent_stack.append(str(comp_id))
        self.set_selection([])
        self.update_view()
        # Notify the parent application to update breadcrumbs & sidebar
        parent_app = self.winfo_toplevel()
        if hasattr(parent_app, "on_navigation_change"):
            parent_app.on_navigation_change()

    def drill_out(self):
        if self.parent_stack:
            self.parent_stack.pop()
            self.set_selection([])
            self.update_view()
            parent_app = self.winfo_toplevel()
            if hasattr(parent_app, "on_navigation_change"):
                parent_app.on_navigation_change()

    def toggle_labels_visibility(self):
        self.show_labels = not self.show_labels
        self.draw_boxes()

    def _move_box_by_keys(self, dx: int, dy: int):
        if not self.selected_boxes:
            return
        for box in self.selected_boxes:
            box.bounds.x = int(box.bounds.x + dx)
            box.bounds.y = int(box.bounds.y + dy)
            self.client.update_component(
                str(box.id),
                bounds={
                    "x": int(box.bounds.x),
                    "y": int(box.bounds.y),
                    "w": int(box.bounds.w),
                    "h": int(box.bounds.h),
                },
            )
        self.draw_boxes()
