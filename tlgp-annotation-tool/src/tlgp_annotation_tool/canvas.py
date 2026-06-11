import tkinter as tk
from PIL import Image, ImageTk, ImageDraw

from typing import List, Optional, Tuple, Dict
from tlgp_annotation_tool.models import AnnotationBox, ScreenSession
from tlgp_annotation_tool.controller import SessionController, NavigationContext
from tlgp_annotation_tool.annotation_renderer import (
    compute_pill_font_size, compute_pill_padding, compute_border_widths,
    get_font, get_text_dimensions, get_pill_coords,
)

# Visual gap (in image-space pixels) inserted between cut segments on the canvas.
CUT_GAP_PX = 20


class AnnotationCanvas(tk.Canvas):
    """
    AnnotationCanvas handles visual rendering of screenshot images and annotation boxes,
    along with three mouse/keyboard interaction modes:

    1. Select Mode ('select') - Default:
       - Pointer cursor.
       - Hovering over a selected box's handle shows a resize cursor.
       - Left-click selects a box. Shift/Ctrl + Click toggles multi-selection.
       - Dragging selected boxes moves them collectively within boundary clamps.
       - Click-dragging empty space draws a dashed marquee rectangle. On release,
         all boxes enclosed by or intersecting the marquee are selected.
       - Arrow keys move selected boxes. Double-click cycles overlapping boxes selection.

    2. Draw Mode ('draw'):
       - Crosshair cursor.
       - Click-dragging anywhere draws a new box.
       - On release, the box is added, selection shifts to it, and mode automatically
         reverts back to Select Mode.

    3. Pan Mode ('pan'):
       - Hand cursor.
       - Dragging anywhere pans the viewport.
    """
    def __init__(self, parent, controller: SessionController, on_select_callback, **kwargs):
        kwargs.setdefault("bg", "#121212")
        super().__init__(parent, **kwargs)
        self.controller = controller
        self.session = controller.session
        self.on_select = on_select_callback

        # State
        self.zoom_factor: float = 1.0
        self._rendered_zoom_factor: float = 1.0
        self.mode: str = "select"
        self.prev_mode_before_space: Optional[str] = None
        self.selected_boxes: List[AnnotationBox] = []
        self.show_labels: bool = True

        # Drag state
        self._drag_mouse_start_abs: Optional[Tuple[int, int]] = None
        self._drag_start_time: float = 0.0
        self._deadzone_active: bool = False
        self._drag_mouse_start_canvas: Tuple[int, int] = (0, 0)
        self._drag_orig_coords: Dict[int, Tuple[AnnotationBox, int, int, int, int]] = {}
        self._drag_orig_x1: int = 0
        self._drag_orig_y1: int = 0
        self._drag_orig_x2: int = 0
        self._drag_orig_y2: int = 0
        self.resize_handle: Optional[str] = None
        self._is_dragging: bool = False

        # Image refs
        self.full_pil_img: Optional[Image.Image] = None
        self.current_pil_img: Optional[Image.Image] = None
        self.tk_photo = None
        self._prev_tk_photo = None
        self.image_item_id = None

        # Last rendering states
        self._last_nav_key: Optional[tuple] = None
        self._last_pil_img: Optional[Image.Image] = None

        # Drill-in mask cache
        self._mask_cached_img: Optional[Image.Image] = None
        self._mask_cached_key: Optional[Tuple] = None

        # Cut segments cache: list of (src_y_start, src_y_end, display_y_offset)
        self._segments: List[Tuple[int, int, int]] = []
        self._gapped_img: Optional[Image.Image] = None
        self._gapped_img_key: Optional[Tuple] = None

        # Overlapping boxes list
        self.overlapping_boxes = []

        # Temp drawing rectangle
        self.temp_rect_id = None
        self.draw_start_x = None
        self.draw_start_y = None

        # Resizing tracking
        self._last_vw = None
        self._last_vh = None
        self._resize_anchor = None
        self._last_resize_time = 0.0

        # Performance & Redraw Queue state
        self._is_active_interaction: bool = False
        self._active_interaction_timer: Optional[str] = None
        self._redraw_pending: bool = False
        self._pending_center_abs: Optional[Tuple[float, float]] = None
        self._pending_viewport_pos: Optional[Tuple[float, float]] = None
        self.scroll_x: float = 0.0
        self.scroll_y: float = 0.0

        # Bindings
        self.bind("<ButtonPress-1>", self.on_click)
        self.bind("<B1-Motion>", self.on_drag)
        self.bind("<ButtonRelease-1>", self.on_release)
        self.bind("<Motion>", self.on_mouse_move)

        # Overlapping selection cycle tracking
        self._last_click_time = 0.0
        self._last_click_cx = 0.0
        self._last_click_cy = 0.0
        self._cycle_boxes = None
        self._last_cycle_index = -1
        self._click_sequence_count = 0
        self._collapse_selection_on_release = None

        # Context menu
        self.context_menu = tk.Menu(self, tearoff=0)
        self.bind("<Button-3>", self.show_context_menu)

        # Panning with middle mouse (Button 2)
        self.bind("<ButtonPress-2>", self._start_pan_event)
        self.bind("<B2-Motion>", self._pan_event)
        self.bind("<ButtonRelease-2>", self._stop_pan_event)

        self.bind("<Configure>", self.on_resize)

        self.config(takefocus=True, highlightthickness=0, borderwidth=0)

        # Arrow keys for moving boxes
        self.bind("<Up>", lambda e: self._move_box_by_keys(0, -1))
        self.bind("<Down>", lambda e: self._move_box_by_keys(0, 1))
        self.bind("<Left>", lambda e: self._move_box_by_keys(-1, 0))
        self.bind("<Right>", lambda e: self._move_box_by_keys(1, 0))

        self.bind("<Shift-Up>", lambda e: self._move_box_by_keys(0, -10))
        self.bind("<Shift-Down>", lambda e: self._move_box_by_keys(0, 10))
        self.bind("<Shift-Left>", lambda e: self._move_box_by_keys(-10, 0))
        self.bind("<Shift-Right>", lambda e: self._move_box_by_keys(10, 0))

        # Subscribe to controller events
        self.controller.subscribe("undo_redo", self._on_undo_redo)
        self.controller.subscribe("rename", lambda box: self.draw_boxes())
        self.controller.subscribe("renumber", lambda box: self.draw_boxes())
        self.controller.subscribe("update_coords", lambda box: self.draw_boxes())
        self.controller.subscribe("selection_change", self._on_selection_change)
        self.controller.subscribe("navigation_change", self._on_navigation_change)
        self.controller.subscribe("mode_change", self.set_mode)
        self.controller.subscribe("cuts_change", self._on_cuts_change)

    # ── Navigation helpers ─────────────────────────────────────────────

    def _nav_key(self) -> tuple:
        """A hashable key representing the current navigation state."""
        parent = self.controller.nav.current_parent
        return (self.controller.nav.depth, id(parent) if parent else None)

    # ── Image & View ───────────────────────────────────────────────────

    def load_image(self, stitched_img: Image.Image):
        self.full_pil_img = None
        self.current_pil_img = None
        self.tk_photo = None
        self._prev_tk_photo = None
        self._mask_cached_img = None
        self._mask_cached_key = None
        self._gapped_img = None
        self._gapped_img_key = None
        self._segments = []

        self.full_pil_img = stitched_img
        self.update_view()

    def _composite_gapped_image(
        self, src_img: Image.Image, segments: List[Tuple[int, int, int]]
    ) -> Image.Image:
        """Create a composite image with gap strips between cut segments.

        The gap strips are filled with a dark separator pattern to visually
        indicate the cut boundaries.
        """
        if not segments:
            return src_img

        img_w = src_img.width
        total_gap = segments[-1][2]  # last segment's display_y_offset
        total_h = src_img.height + total_gap

        composite = Image.new("RGB", (img_w, total_h), (30, 30, 30))

        for src_start, src_end, display_offset in segments:
            seg_h = src_end - src_start
            if seg_h <= 0:
                continue
            seg_strip = src_img.crop((0, src_start, img_w, src_end))
            dest_y = src_start + display_offset
            composite.paste(seg_strip, (0, dest_y))

        # Draw dashed separator lines in the gap areas
        draw = ImageDraw.Draw(composite)
        for i in range(1, len(segments)):
            _, prev_end, _ = segments[i - 1]
            _, _, curr_offset = segments[i]
            gap_start_y = prev_end + segments[i - 1][2]
            gap_mid_y = gap_start_y + CUT_GAP_PX // 2

            # Draw a dashed line in the middle of the gap
            dash_len = 12
            gap_len = 8
            x = 0
            while x < img_w:
                x_end = min(x + dash_len, img_w)
                draw.line([(x, gap_mid_y), (x_end, gap_mid_y)],
                          fill=(100, 100, 100), width=2)
                x += dash_len + gap_len

        return composite

    def _get_pan_cursor(self, active: bool = False) -> str:
        import sys
        if sys.platform == "darwin":
            return "closedhand" if active else "openhand"
        return "fleur"

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

    def zoom(self, delta: float, mouse_pos: Optional[Tuple[int, int]] = None):
        vw = self.winfo_width()
        vh = self.winfo_height()

        if mouse_pos is not None:
            mx, my = mouse_pos
        else:
            mx, my = vw / 2, vh / 2

        actual_sx = self.canvasx(0)
        actual_sy = self.canvasy(0)
        is_zooming = self._redraw_pending or self._is_active_interaction
        if not is_zooming:
            if (not hasattr(self, "scroll_x") or not hasattr(self, "scroll_y") or
                abs(self.scroll_x - actual_sx) > 1.0 or abs(self.scroll_y - actual_sy) > 1.0):
                self.scroll_x = float(actual_sx)
                self.scroll_y = float(actual_sy)

        cx = self.scroll_x + mx
        cy = self.scroll_y + my

        px, py = self._parent_offset()
        norm_x = (cx / self._rendered_zoom_factor) + px
        norm_y = (cy / self._rendered_zoom_factor) + py

        if delta > 0:
            factor = 1.1 ** (delta / 0.1)
            self.zoom_factor = min(10.0, self.zoom_factor * factor)
        else:
            factor = 1.1 ** (abs(delta) / 0.1)
            self.zoom_factor = max(0.05, self.zoom_factor / factor)

        new_cx = (norm_x - px) * self.zoom_factor
        new_cy = (norm_y - py) * self.zoom_factor
        new_left = new_cx - mx
        new_top = new_cy - my

        self.scroll_x = new_left
        self.scroll_y = new_top
        self._rendered_zoom_factor = self.zoom_factor

        self._start_active_interaction()
        self.queue_update_view(center_abs=(norm_x, norm_y), target_viewport_pos=(mx, my))

    def queue_update_view(self, center_abs: Optional[Tuple[float, float]] = None, target_viewport_pos: Optional[Tuple[float, float]] = None):
        if center_abs is not None:
            self._pending_center_abs = center_abs
        if target_viewport_pos is not None:
            self._pending_viewport_pos = target_viewport_pos

        if self._redraw_pending:
            return

        self._redraw_pending = True
        self.after(30, self._execute_redraw)

    def _execute_redraw(self):
        if not self._redraw_pending:
            return
        self._redraw_pending = False
        center = self._pending_center_abs
        viewport = self._pending_viewport_pos
        self._pending_center_abs = None
        self._pending_viewport_pos = None
        self.update_view(center_abs=center, target_viewport_pos=viewport)

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

    def _get_viewport_center_abs(self) -> Optional[Tuple[float, float]]:
        vw = self.winfo_width()
        vh = self.winfo_height()
        if vw <= 1 or vh <= 1:
            return None

        actual_sx = self.canvasx(0)
        actual_sy = self.canvasy(0)
        if (hasattr(self, "scroll_x") and hasattr(self, "scroll_y") and
            abs(self.scroll_x - actual_sx) <= 1.0 and abs(self.scroll_y - actual_sy) <= 1.0):
            cx = self.scroll_x + vw / 2
            cy = self.scroll_y + vh / 2
        else:
            cx = actual_sx + vw / 2
            cy = actual_sy + vh / 2

        px, py = self._parent_offset()
        return (cx / self._rendered_zoom_factor) + px, (cy / self._rendered_zoom_factor) + py

    def update_view(self, center_abs: Optional[Tuple[float, float]] = None, target_viewport_pos: Optional[Tuple[float, float]] = None):
        if not self.full_pil_img:
            return

        if center_abs is None:
            self._resize_anchor = None

        nav_key = self._nav_key()
        structure_changed = (
            nav_key != self._last_nav_key or
            self.full_pil_img != self._last_pil_img
        )

        # Preserve the current zoom and viewport center if we are navigating within the same image
        if center_abs is None and self._last_nav_key is not None and self.full_pil_img == self._last_pil_img:
            center_abs = self._get_viewport_center_abs()

        self._last_nav_key = nav_key
        self._last_pil_img = self.full_pil_img

        parent = self.controller.nav.current_parent
        if parent:
            # Dim everything outside the current parent box
            left, top, right, bottom = parent.bounds_tuple
            cache_key = (id(parent), left, top, right, bottom, id(self.full_pil_img))

            if self._mask_cached_key != cache_key:
                mask = Image.new("RGBA", self.full_pil_img.size, (0, 0, 0, 140))
                draw = ImageDraw.Draw(mask)
                draw.rectangle([left, top, right, bottom], fill=(0, 0, 0, 0))
                base = self.full_pil_img.convert("RGBA")
                self._mask_cached_img = Image.alpha_composite(base, mask).convert("RGB")
                self._mask_cached_key = cache_key

            self.current_pil_img = self._mask_cached_img
        else:
            self.current_pil_img = self.full_pil_img

        # Build segments and create gapped composite image when cuts are active
        self._segments = self._build_segments()
        if self._has_active_cuts() and len(self._segments) > 1:
            cuts_key = (tuple(self.controller.session.cut_lines), id(self.current_pil_img))
            if self._gapped_img_key != cuts_key:
                self._gapped_img = self._composite_gapped_image(self.current_pil_img, self._segments)
                self._gapped_img_key = cuts_key
            display_img = self._gapped_img
        else:
            display_img = self.current_pil_img

        vw = self.winfo_width()
        vh = self.winfo_height()
        if vw <= 1 or vh <= 1:
            vw = 1200
            vh = 800

        if center_abs is None:
            self.update_idletasks()
            img_w = display_img.width
            img_h = display_img.height
            if vw > 40 and vh > 40:
                fit_w = (vw - 40) / img_w
                fit_h = (vh - 40) / img_h
                self.zoom_factor = max(0.1, min(1.0, min(fit_w, fit_h)))

        px, py = self._parent_offset()

        if center_abs is not None:
            norm_x, norm_y = center_abs
            new_cx = (norm_x - px) * self.zoom_factor
            new_cy = (norm_y - py) * self.zoom_factor

            tx, ty = target_viewport_pos if target_viewport_pos is not None else (vw / 2, vh / 2)
            new_left = new_cx - tx
            new_top = new_cy - ty
        else:
            self.update_idletasks()
            center_x = px + display_img.width / 2
            center_y = py + display_img.height / 2

            new_cx = (center_x - px) * self.zoom_factor
            new_cy = (center_y - py) * self.zoom_factor

            new_left = new_cx - vw / 2
            new_top = new_cy - vh / 2

        img_x1 = new_left / self.zoom_factor + px
        img_y1 = new_top / self.zoom_factor + py
        img_x2 = (new_left + vw) / self.zoom_factor + px
        img_y2 = (new_top + vh) / self.zoom_factor + py

        buffer_w_canvas = 500.0
        buffer_h_canvas = 500.0

        buffer_w = buffer_w_canvas / self.zoom_factor
        buffer_h = buffer_h_canvas / self.zoom_factor

        crop_x1 = max(0, round(img_x1 - buffer_w))
        crop_y1 = max(0, round(img_y1 - buffer_h))
        crop_x2 = min(display_img.width, round(img_x2 + buffer_w))
        crop_y2 = min(display_img.height, round(img_y2 + buffer_h))

        if crop_x2 <= crop_x1:
            crop_x2 = crop_x1 + 1
        if crop_y2 <= crop_y1:
            crop_y2 = crop_y1 + 1

        new_crop = (crop_x1, crop_y1, crop_x2, crop_y2)

        if (hasattr(self, "_rendered_crop") and self._rendered_crop == new_crop and
            hasattr(self, "_resized_image_zoom_factor") and self._resized_image_zoom_factor == self.zoom_factor and
            self.tk_photo is not None and not structure_changed):
            img_cx = (crop_x1 - px) * self.zoom_factor
            img_cy = (crop_y1 - py) * self.zoom_factor
        else:
            self._rendered_crop = new_crop
            self._resized_image_zoom_factor = self.zoom_factor
            cropped_img = display_img.crop(new_crop)

            img_cx = (crop_x1 - px) * self.zoom_factor
            img_cy = (crop_y1 - py) * self.zoom_factor

            w_crop = max(1, round((crop_x2 - crop_x1) * self.zoom_factor))
            h_crop = max(1, round((crop_y2 - crop_y1) * self.zoom_factor))

            resampler = Image.Resampling.BILINEAR if self.zoom_factor > 1.0 else Image.Resampling.LANCZOS
            resized = cropped_img.resize((w_crop, h_crop), resampler)
            self._prev_tk_photo = self.tk_photo
            self.tk_photo = ImageTk.PhotoImage(resized)

        if self.image_item_id is None:
            self.image_item_id = self.create_image(img_cx, img_cy, anchor="nw", image=self.tk_photo)
        else:
            self.itemconfig(self.image_item_id, image=self.tk_photo)
            self.coords(self.image_item_id, img_cx, img_cy)

        margin_x = 2000
        margin_y = 2000
        w = max(1, round(display_img.width * self.zoom_factor))
        h = max(1, round(display_img.height * self.zoom_factor))
        self.config(scrollregion=(-margin_x, -margin_y, w + margin_x, h + margin_y))

        total_w = w + 2 * margin_x
        total_h = h + 2 * margin_y

        frac_x = (new_left + margin_x) / total_w
        frac_y = (new_top + margin_y) / total_h

        self.xview_moveto(max(0.0, min(1.0, frac_x)))
        self.yview_moveto(max(0.0, min(1.0, frac_y)))

        self.scroll_x = new_left
        self.scroll_y = new_top
        self._rendered_zoom_factor = self.zoom_factor
        self.draw_boxes()
        self.controller._notify("zoom_change", self.zoom_factor)
        self._last_vw = self.winfo_width()
        self._last_vh = self.winfo_height()

    def get_center_abs_for_size(self, vw: float, vh: float) -> Optional[Tuple[float, float]]:
        if not self.full_pil_img:
            return None
        if vw <= 1 or vh <= 1:
            return None

        cx = self.canvasx(vw / 2)
        cy = self.canvasy(vh / 2)

        px, py = self._parent_offset()
        norm_x = (cx / self._rendered_zoom_factor) + px
        norm_y = (cy / self._rendered_zoom_factor) + py
        return (norm_x, norm_y)

    def on_resize(self, event):
        if not self.full_pil_img:
            return

        new_vw = event.width
        new_vh = event.height

        if self._last_vw and self._last_vh and (self._last_vw != new_vw or self._last_vh != new_vh):
            import time
            now = time.time()

            if not self._resize_anchor or (now - self._last_resize_time > 0.5):
                self._resize_anchor = self.get_center_abs_for_size(self._last_vw, self._last_vh)

            self._last_resize_time = now

            if self._resize_anchor:
                self.update_view(center_abs=self._resize_anchor)

        self._last_vw = new_vw
        self._last_vh = new_vh

    # ── Coordinate Helpers ─────────────────────────────────────────────

    def _parent_offset(self) -> Tuple[int, int]:
        return 0, 0

    def _boundary(self) -> Tuple[int, int, int, int]:
        if self.full_pil_img:
            return self.controller.get_boundary(self.full_pil_img.width, self.full_pil_img.height)
        return 0, 0, 99999, 99999

    def _has_active_cuts(self) -> bool:
        """Returns True if there are cut lines."""
        return len(self.controller.session.cut_lines) > 0

    def _build_segments(self) -> List[Tuple[int, int, int]]:
        """Build segment list: [(src_y_start, src_y_end, display_y_offset), ...].

        Each segment's display_y_offset is the cumulative gap pixels above it.
        Segment 0 has offset 0, segment 1 has offset CUT_GAP_PX, etc.
        """
        if not self.full_pil_img:
            return []

        img_h = self.full_pil_img.height
        cuts = self.controller.session.cut_lines

        if not cuts:
            return [(0, img_h, 0)]

        segments = []
        prev_y = 0
        for i, cut_y in enumerate(sorted(cuts)):
            clamped = max(0, min(img_h, cut_y))
            if clamped > prev_y:
                segments.append((prev_y, clamped, i * CUT_GAP_PX))
            prev_y = clamped

        if prev_y < img_h:
            segments.append((prev_y, img_h, len(cuts) * CUT_GAP_PX))

        return segments

    def _gap_offset_for_y(self, abs_y: int) -> int:
        """Returns the cumulative gap offset for a given absolute Y.

        If abs_y is inside a gap region (shouldn't happen in normal use),
        returns the offset for the nearest segment.
        """
        if not self._segments or len(self._segments) <= 1:
            return 0
        for src_start, src_end, offset in self._segments:
            if abs_y < src_end:
                return offset
        # Past the last segment — use last offset
        return self._segments[-1][2]

    def _gap_offset_inverse(self, display_y: int) -> int:
        """Inverse of gap offset: given a display Y (with gaps), return absolute image Y."""
        if not self._segments or len(self._segments) <= 1:
            return display_y
        for src_start, src_end, offset in self._segments:
            disp_start = src_start + offset
            disp_end = src_end + offset
            if display_y < disp_end:
                return display_y - offset
        # Past all segments — use last offset
        return display_y - self._segments[-1][2]

    def to_canvas(self, abs_x: int, abs_y: int) -> Tuple[float, float]:
        """Converts absolute image coordinates to canvas coordinates.

        When cuts are active at root depth, the Y coordinate is shifted
        by the cumulative gap offset for the segment containing abs_y.
        """
        px, py = self._parent_offset()
        gap_y = self._gap_offset_for_y(abs_y) if self._has_active_cuts() else 0
        return ((abs_x - px) * self._rendered_zoom_factor,
                (abs_y + gap_y - py) * self._rendered_zoom_factor)

    def to_abs(self, cx: float, cy: float) -> Tuple[int, int]:
        """Converts canvas coordinates to absolute image coordinates.

        When cuts are active at root depth, the Y coordinate is unshifted
        by subtracting the gap offset.
        """
        px, py = self._parent_offset()
        raw_x = round(cx / self._rendered_zoom_factor) + px
        raw_y = round(cy / self._rendered_zoom_factor) + py
        if self._has_active_cuts():
            raw_y = self._gap_offset_inverse(raw_y)
        return raw_x, raw_y

    def _clamp(self, v: int, lo: int, hi: int) -> int:
        return max(lo, min(hi, v))

    def _get_segment_y_bounds(self, abs_y: int) -> Tuple[int, int]:
        """Returns (seg_top, seg_bottom) for the segment containing abs_y.

        Only meaningful at root depth when cuts are active. If no cuts,
        returns the full image Y range from _boundary().

        For non-last segments the bottom bound is exclusive (cut_y - 1)
        so box edges cannot sit exactly on the cut line.
        """
        if not self._has_active_cuts() or not self._segments:
            _, by1, _, by2 = self._boundary()
            return by1, by2

        last_idx = len(self._segments) - 1
        for i, (src_start, src_end, _) in enumerate(self._segments):
            if abs_y < src_end:
                # Last segment keeps the original bound (image edge),
                # other segments use src_end - 1 so boxes don't touch the cut line.
                bound = src_end if i == last_idx else src_end - 1
                return src_start, bound
        # Past last segment — use last segment bounds
        last = self._segments[-1]
        return last[0], last[1]

    # ── Box Accessors ──────────────────────────────────────────────────

    def _active_boxes(self) -> List[AnnotationBox]:
        return self.controller.active_list()

    def set_overlapping_boxes(self, boxes: list):
        self.overlapping_boxes = boxes
        self.draw_boxes()

    # ── Drawing ────────────────────────────────────────────────────────

    def draw_boxes(self):
        self.delete("ann")

        boxes = self._active_boxes()
        for box in boxes:
            is_sel = box in self.selected_boxes
            is_overlap = box in self.overlapping_boxes

            if is_sel:
                color = "#0c8ce9"
            elif is_overlap:
                color = "#e28743"
            else:
                color = "#ff4444"

            # Compute uniform font size and border widths for this nesting level
            parent = self.controller.nav.current_parent
            full_w = self.full_pil_img.width if self.full_pil_img else 1
            abs_font_size = compute_pill_font_size(parent, full_w)
            abs_box_border, abs_pill_outline = compute_border_widths(parent, full_w)
            font_obj = get_font(abs_font_size)

            # Box border — scaled by level + zoom. Selected/overlap get +1 for UI distinction.
            base_lw = max(1, round(abs_box_border * self._rendered_zoom_factor))
            if is_sel:
                lw = base_lw + 1
            elif is_overlap:
                lw = base_lw + 1
            else:
                lw = base_lw

            cx1, cy1 = self.to_canvas(box.left, box.top)
            cx2, cy2 = self.to_canvas(box.right, box.bottom)

            self.create_rectangle(cx1, cy1, cx2, cy2, outline=color, width=lw, tags="ann")

            # Number pill — uses the shared annotation_renderer for sizing so that
            # the canvas preview matches the exported images exactly.
            num = str(box.id)
            if is_overlap:
                num = "⚠️ " + num

            # Measure text in absolute image coordinates
            tw, th, _top = get_text_dimensions(None, num, font_obj)
            pad_x, pad_y = compute_pill_padding(abs_font_size)

            # Scale the absolute pill dimensions by the canvas zoom factor for display
            pill_w = max(4, round((tw + pad_x) * self._rendered_zoom_factor))
            pill_h = max(4, round((th + pad_y) * self._rendered_zoom_factor))
            canvas_font_size = max(4, min(72, round(abs_font_size * self._rendered_zoom_factor)))

            pill_corner = getattr(box, "pill_corner", "top_left")
            pill_x, pill_y = get_pill_coords(cx1, cy1, cx2, cy2, pill_w, pill_h, pill_corner)
            pill_outline_w = max(1, round(abs_pill_outline * self._rendered_zoom_factor))
            self.create_rectangle(pill_x, pill_y, pill_x + pill_w, pill_y + pill_h,
                                  fill="white", outline=color, width=pill_outline_w, tags="ann")
            self.create_text(pill_x + (pill_w / 2), pill_y + (pill_h / 2), text=num, fill=color,
                             font=("Arial", canvas_font_size, "bold"), tags="ann")

            # Box text label below the box (toggled by 'T' key)
            if self.show_labels and box.label:
                self.create_text(cx1, cy2 + 4, text=box.label, anchor="nw",
                                 fill=color, font=("", 9), tags="ann")

        if len(self.selected_boxes) == 1:
            self._draw_handles(self.selected_boxes[0])
        if self.image_item_id is not None:
            self.tag_lower(self.image_item_id)

    def _draw_handles(self, box: AnnotationBox):
        cx1, cy1 = self.to_canvas(box.left, box.top)
        cx2, cy2 = self.to_canvas(box.right, box.bottom)
        mx, my = (cx1 + cx2) / 2, (cy1 + cy2) / 2
        hs = 5

        for hx, hy in [(cx1, cy1), (mx, cy1), (cx2, cy1),
                        (cx1, my),             (cx2, my),
                        (cx1, cy2), (mx, cy2), (cx2, cy2)]:
            self.create_rectangle(hx - hs, hy - hs, hx + hs, hy + hs,
                                  fill="white", outline="#0c8ce9", width=1.5, tags="ann")

    def _handle_positions(self, box: AnnotationBox) -> Dict[str, Tuple[float, float]]:
        cx1, cy1 = self.to_canvas(box.left, box.top)
        cx2, cy2 = self.to_canvas(box.right, box.bottom)
        mx, my = (cx1 + cx2) / 2, (cy1 + cy2) / 2

        return {
            "tl": (cx1, cy1), "tm": (mx, cy1), "tr": (cx2, cy1),
            "ml": (cx1, my),                    "mr": (cx2, my),
            "bl": (cx1, cy2), "bm": (mx, cy2), "br": (cx2, cy2),
        }

    def _hit_handle(self, cx: float, cy: float) -> Optional[str]:
        if len(self.selected_boxes) != 1:
            return None
        box = self.selected_boxes[0]
        for name, (hx, hy) in self._handle_positions(box).items():
            if abs(cx - hx) <= 7 and abs(cy - hy) <= 7:
                return name
        return None

    def _hit_box(self, cx: float, cy: float) -> Optional[AnnotationBox]:
        for box in reversed(self._active_boxes()):
            bx1, by1 = self.to_canvas(box.left, box.top)
            bx2, by2 = self.to_canvas(box.right, box.bottom)
            if bx1 <= cx <= bx2 and by1 <= cy <= by2:
                return box
        return None

    def _get_all_hit_boxes(self, cx: float, cy: float) -> List[AnnotationBox]:
        hits = []
        for box in reversed(self._active_boxes()):
            bx1, by1 = self.to_canvas(box.left, box.top)
            bx2, by2 = self.to_canvas(box.right, box.bottom)
            if bx1 <= cx <= bx2 and by1 <= cy <= by2:
                hits.append(box)
        return hits

    # ── Event Handlers ─────────────────────────────────────────────────

    def on_click(self, event):
        self._collapse_selection_on_release = None
        self.focus_set()
        cx = self.canvasx(event.x)
        cy = self.canvasy(event.y)

        if self.mode == "pan":
            self._start_pan_event(event)
            return

        import time
        now = time.time()

        is_multi = (event.state & 0x0001) or (event.state & 0x0004)

        hit_boxes_at_click = self._get_all_hit_boxes(cx, cy)
        primary_sel = self.selected_boxes[-1] if self.selected_boxes else None

        if (now - self._last_click_time < 0.5 and
            abs(cx - self._last_click_cx) < 15 and
            abs(cy - self._last_click_cy) < 15 and
            primary_sel and primary_sel in hit_boxes_at_click):
            self._click_sequence_count += 1
        else:
            self._click_sequence_count = 1
            self._cycle_boxes = None

        self._last_click_time = now
        self._last_click_cx = cx
        self._last_click_cy = cy

        if (self._click_sequence_count % 2 == 0) and self.mode == "select" and not is_multi:
            handle = self._hit_handle(cx, cy)
            if not handle:
                if self._cycle_boxes is None:
                    hit_boxes = self._get_all_hit_boxes(cx, cy)
                    if len(hit_boxes) > 1:
                        self._cycle_boxes = hit_boxes
                        if primary_sel in hit_boxes:
                            self._last_cycle_index = hit_boxes.index(primary_sel)
                        else:
                            self._last_cycle_index = 0

                if self._cycle_boxes is not None:
                    self._last_cycle_index = (self._last_cycle_index + 1) % len(self._cycle_boxes)
                    new_box = self._cycle_boxes[self._last_cycle_index]
                    self.controller.set_selection([new_box])
                    self._begin_move(new_box, cx, cy, event)
                    self.controller.bring_to_front(new_box, save_history=False)
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
                    self.controller.set_selection(new_sel)
                    if clicked in new_sel:
                        self._begin_move(clicked, cx, cy, event)
                else:
                    if clicked in self.selected_boxes:
                        if len(self.selected_boxes) > 1:
                            self._collapse_selection_on_release = clicked
                        self._begin_move(clicked, cx, cy, event)
                    else:
                        self.controller.set_selection([clicked])
                        self._begin_move(clicked, cx, cy, event)
                return

            if not is_multi:
                self.controller.set_selection([])
            self.draw_start_x = cx
            self.draw_start_y = cy
            self.temp_rect_id = self.create_rectangle(cx, cy, cx, cy,
                                                       outline="#0c8ce9", width=1.5, dash=(4, 4))
            return

        if self.mode == "draw":
            self.draw_start_x = cx
            self.draw_start_y = cy
            self.temp_rect_id = self.create_rectangle(cx, cy, cx, cy,
                                                       outline="#0c8ce9", width=2, dash=(4, 4))

    def _begin_resize(self, handle: str, event=None):
        self.resize_handle = handle
        self._is_dragging = True
        box = self.selected_boxes[0]
        self._drag_orig_x1 = box.left
        self._drag_orig_y1 = box.top
        self._drag_orig_x2 = box.right
        self._drag_orig_y2 = box.bottom
        hx, hy = self._handle_positions(box)[handle]
        self._drag_mouse_start_abs = self.to_abs(hx, hy)
        if event:
            import time
            self._drag_start_time = time.time()
            self._deadzone_active = False
            self._drag_mouse_start_canvas = (event.x, event.y)

    def _begin_move(self, box: AnnotationBox, cx: float, cy: float, event=None):
        self.resize_handle = None
        self._is_dragging = True
        self._drag_mouse_start_abs = self.to_abs(cx, cy)

        self._drag_orig_coords = {}
        for b in self.selected_boxes:
            self._drag_orig_coords[id(b)] = (b, b.x1, b.y1, b.x2, b.y2)

        primary = self.selected_boxes[-1]
        self._drag_orig_x1 = primary.x1
        self._drag_orig_y1 = primary.y1
        self._drag_orig_x2 = primary.x2
        self._drag_orig_y2 = primary.y2

        if event:
            import time
            self._drag_start_time = time.time()
            self._deadzone_active = True
            self._drag_mouse_start_canvas = (event.x, event.y)

        self.draw_boxes()
        self.on_select(primary)

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
            ax = self._clamp(ax, bx1, bx2)
            ay = self._clamp(ay, by1, by2)
            bx = self._clamp(bx, bx1, bx2)
            by = self._clamp(by, by1, by2)
            # Clamp to cut segment boundary based on the draw start position
            seg_top, seg_bot = self._get_segment_y_bounds(ay)
            ay = self._clamp(ay, seg_top, seg_bot)
            by = self._clamp(by, seg_top, seg_bot)
            sx, sy = self.to_canvas(ax, ay)
            ex, ey = self.to_canvas(bx, by)
            self.coords(self.temp_rect_id, sx, sy, ex, ey)
            return

        if self.mode == "select" and self._is_dragging and self.selected_boxes:
            if self._deadzone_active:
                import time
                elapsed = time.time() - self._drag_start_time
                dx = event.x - self._drag_mouse_start_canvas[0]
                dy = event.y - self._drag_mouse_start_canvas[1]
                distance = (dx * dx + dy * dy) ** 0.5
                if elapsed > 0.200 or distance > 5.0:
                    self._deadzone_active = False

            if self._deadzone_active:
                return

            mouse_abs = self.to_abs(cx, cy)
            start_abs = self._drag_mouse_start_abs
            total_dx = mouse_abs[0] - start_abs[0]
            total_dy = mouse_abs[1] - start_abs[1]

            if total_dx != 0 or total_dy != 0:
                self._collapse_selection_on_release = None

            if self.resize_handle:
                self._apply_resize(total_dx, total_dy, bx1, by1, bx2, by2)
            else:
                self._apply_move_multiple(total_dx, total_dy, bx1, by1, bx2, by2)

    def _apply_resize(self, dx: int, dy: int, bx1: int, by1: int, bx2: int, by2: int):
        box = self.selected_boxes[0]
        ox1, oy1 = self._drag_orig_x1, self._drag_orig_y1
        ox2, oy2 = self._drag_orig_x2, self._drag_orig_y2
        h = self.resize_handle

        nx1, ny1, nx2, ny2 = ox1, oy1, ox2, oy2
        if "l" in h: nx1 = ox1 + dx
        if "r" in h: nx2 = ox2 + dx
        if "t" in h: ny1 = oy1 + dy
        if "b" in h: ny2 = oy2 + dy

        nx1 = self._clamp(nx1, bx1, bx2)
        ny1 = self._clamp(ny1, by1, by2)
        nx2 = self._clamp(nx2, bx1, bx2)
        ny2 = self._clamp(ny2, by1, by2)

        # Clamp to cut segment boundary
        seg_top, seg_bot = self._get_segment_y_bounds(oy1)
        ny1 = self._clamp(ny1, seg_top, seg_bot)
        ny2 = self._clamp(ny2, seg_top, seg_bot)

        self.controller.update_box_coords(
            box,
            min(nx1, nx2), min(ny1, ny2),
            max(nx1, nx2), max(ny1, ny2)
        )

    def _apply_move_multiple(self, dx: int, dy: int, bx1: int, by1: int, bx2: int, by2: int):
        coords_list = []
        for bid, (box, ox1, oy1, ox2, oy2) in self._drag_orig_coords.items():
            w = ox2 - ox1
            h = oy2 - oy1

            nx1 = ox1 + dx
            ny1 = oy1 + dy
            nx2 = nx1 + w
            ny2 = ny1 + h

            left, right = min(nx1, nx2), max(nx1, nx2)
            top, bottom = min(ny1, ny2), max(ny1, ny2)

            if left < bx1:
                shift = bx1 - left
                nx1 += shift; nx2 += shift
            elif right > bx2:
                shift = bx2 - right
                nx1 += shift; nx2 += shift
            if top < by1:
                shift = by1 - top
                ny1 += shift; ny2 += shift
            elif bottom > by2:
                shift = by2 - bottom
                ny1 += shift; ny2 += shift

            # Clamp to cut segment boundary (based on original position)
            seg_top, seg_bot = self._get_segment_y_bounds(oy1)
            top2, bottom2 = min(ny1, ny2), max(ny1, ny2)
            if top2 < seg_top:
                shift = seg_top - top2
                ny1 += shift; ny2 += shift
            elif bottom2 > seg_bot:
                shift = seg_bot - bottom2
                ny1 += shift; ny2 += shift

            coords_list.append((box, (nx1, ny1, nx2, ny2)))

        self.controller.update_boxes_coords(coords_list)

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

                left = self._clamp(min(ax1, ax2), bx1, bx2)
                top_ = self._clamp(min(ay1, ay2), by1, by2)
                right = self._clamp(max(ax1, ax2), bx1, bx2)
                bot = self._clamp(max(ay1, ay2), by1, by2)

                if (right - left) > 3 or (bot - top_) > 3:
                    intersected = []
                    for box in self._active_boxes():
                        if (box.left < right and box.right > left and
                            box.top < bot and box.bottom > top_):
                            intersected.append(box)

                    is_multi = (event.state & 0x0001) or (event.state & 0x0004)
                    if is_multi:
                        new_sel = list(self.selected_boxes)
                        for box in intersected:
                            if box not in new_sel:
                                new_sel.append(box)
                        self.controller.set_selection(new_sel)
                    else:
                        self.controller.set_selection(intersected)

            elif self._is_dragging:
                coords_changed = False
                for box in self.selected_boxes:
                    if id(box) in self._drag_orig_coords:
                        _, ox1, oy1, ox2, oy2 = self._drag_orig_coords[id(box)]
                        if (box.x1 != ox1 or box.y1 != oy1 or
                            box.x2 != ox2 or box.y2 != oy2):
                            coords_changed = True
                            break

                for box in list(self.selected_boxes):
                    self.controller.bring_to_front(box, save_history=False)

                if coords_changed:
                    self.controller.commit_coords_change()

        elif self.mode == "draw" and self.temp_rect_id:
            cx = self.canvasx(event.x)
            cy = self.canvasy(event.y)
            self.delete(self.temp_rect_id)
            self.temp_rect_id = None

            if abs(cx - self.draw_start_x) > 5 and abs(cy - self.draw_start_y) > 5:
                bx1, by1, bx2, by2 = self._boundary()
                ax1, ay1 = self.to_abs(self.draw_start_x, self.draw_start_y)
                ax2, ay2 = self.to_abs(cx, cy)
                left = self._clamp(min(ax1, ax2), bx1, bx2)
                top_ = self._clamp(min(ay1, ay2), by1, by2)
                right = self._clamp(max(ax1, ax2), bx1, bx2)
                bot = self._clamp(max(ay1, ay2), by1, by2)

                # Clamp to cut segment boundary based on draw start
                seg_top, seg_bot = self._get_segment_y_bounds(ay1)
                top_ = self._clamp(top_, seg_top, seg_bot)
                bot = self._clamp(bot, seg_top, seg_bot)

                if right - left > 3 and bot - top_ > 3:
                    boxes = self._active_boxes()
                    new_id = len(boxes) + 1
                    depth = self.controller.nav.depth
                    if depth == 0:
                        default_label = f"Component {new_id}"
                    elif depth == 1:
                        default_label = f"Sub-component {new_id}"
                    else:
                        default_label = f"Item {new_id}"
                    new_box = AnnotationBox(
                        id=new_id,
                        label=default_label,
                        x1=left, y1=top_, x2=right, y2=bot
                    )
                    self.controller.add_box(new_box)

            self.controller.set_mode("select")

        self._is_dragging = False
        self.resize_handle = None

        if getattr(self, "_collapse_selection_on_release", None) is not None:
            self.controller.set_selection([self._collapse_selection_on_release])
            self._collapse_selection_on_release = None

    def on_mouse_move(self, event):
        if self.mode == "pan":
            is_dragging = (event.state & 0x0700) != 0
            self.config(cursor=self._get_pan_cursor(active=is_dragging))
            return

        cx = self.canvasx(event.x)
        cy = self.canvasy(event.y)

        if self.mode == "select" and len(self.selected_boxes) == 1 and not self._is_dragging:
            handle = self._hit_handle(cx, cy)
            if handle:
                import sys
                if sys.platform == "darwin":
                    cursors = {
                        "tl": "resizetopleft",     "br": "resizebottomright",
                        "tr": "resizetopright",    "bl": "resizebottomleft",
                        "tm": "resizeupdown",      "bm": "resizeupdown",
                        "ml": "resizeleftright",   "mr": "resizeleftright",
                    }
                else:
                    cursors = {
                        "tl": "size_nw_se", "br": "size_nw_se",
                        "tr": "size_ne_sw", "bl": "size_ne_sw",
                        "tm": "size_ns",    "bm": "size_ns",
                        "ml": "size_we",    "mr": "size_we",
                    }
                self.config(cursor=cursors.get(handle, ""))
                return

        if self.mode == "draw":
            self.config(cursor="crosshair")
            return

        self.config(cursor="")

    # ── Panning ────────────────────────────────────────────────────────

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

        px, py = self._parent_offset()
        img_x1 = (cx1 / self._rendered_zoom_factor) + px
        img_y1 = (cy1 / self._rendered_zoom_factor) + py
        img_x2 = (cx2 / self._rendered_zoom_factor) + px
        img_y2 = (cy2 / self._rendered_zoom_factor) + py

        rc_x1, rc_y1, rc_x2, rc_y2 = self._rendered_crop

        if self._is_active_interaction:
            margin = 20.0 / self._rendered_zoom_factor
        else:
            margin = 50.0 / self._rendered_zoom_factor

        out_left = (img_x1 < rc_x1 + margin) and (rc_x1 > 0)
        out_top = (img_y1 < rc_y1 + margin) and (rc_y1 > 0)
        disp_img = self._gapped_img if self._gapped_img else self.current_pil_img
        out_right = (img_x2 > rc_x2 - margin) and (rc_x2 < disp_img.width)
        out_bottom = (img_y2 > rc_y2 - margin) and (rc_y2 < disp_img.height)

        if out_left or out_top or out_right or out_bottom:
            self.queue_update_view()

    def start_space_pan(self):
        if self.mode != "pan":
            self.prev_mode_before_space = self.mode
            self.mode = "pan"
            self.controller.mode = "pan"
            self.config(cursor=self._get_pan_cursor(active=False))

    def stop_space_pan(self):
        if self.mode == "pan" and self.prev_mode_before_space is not None:
            self.mode = self.prev_mode_before_space
            self.controller.mode = self.mode
            self.prev_mode_before_space = None
            if self.mode == "draw":
                self.config(cursor="crosshair")
            else:
                self.config(cursor="")

    # ── Controller Events ──────────────────────────────────────────────

    def _on_undo_redo(self, arg):
        self._is_dragging = False
        self._cycle_boxes = None
        self._invalidate_gapped_cache()
        self.update_view()

    def _on_selection_change(self, nav: 'NavigationContext', boxes: List[AnnotationBox]):
        self.selected_boxes = boxes
        self.draw_boxes()

    def _on_navigation_change(self):
        self._mask_cached_key = None
        self._invalidate_gapped_cache()
        self.selected_boxes = self.controller.selected_boxes
        self.update_view()

    def _on_cuts_change(self, arg):
        """Called when cut lines are modified via the cut editor."""
        self._invalidate_gapped_cache()
        self.update_view()

    def _invalidate_gapped_cache(self):
        """Clear the gapped image cache so it is rebuilt on next render."""
        self._gapped_img = None
        self._gapped_img_key = None
        self._segments = []

    def _move_box_by_keys(self, dx: int, dy: int):
        if self.mode != "select" or not self.selected_boxes:
            return

        bx1, by1, bx2, by2 = self._boundary()
        coords_list = []
        for box in self.selected_boxes:
            ox1, oy1 = box.x1, box.y1
            ox2, oy2 = box.x2, box.y2

            nx1 = ox1 + dx
            ny1 = oy1 + dy
            nx2 = ox2 + dx
            ny2 = oy2 + dy

            left, right = min(nx1, nx2), max(nx1, nx2)
            top, bottom = min(ny1, ny2), max(ny1, ny2)

            shift_x = 0
            if left < bx1:
                shift_x = bx1 - left
            elif right > bx2:
                shift_x = bx2 - right

            shift_y = 0
            if top < by1:
                shift_y = by1 - top
            elif bottom > by2:
                shift_y = by2 - bottom

            nx1 += shift_x; nx2 += shift_x
            ny1 += shift_y; ny2 += shift_y

            # Clamp to cut segment boundary
            seg_top, seg_bot = self._get_segment_y_bounds(oy1)
            top2, bottom2 = min(ny1, ny2), max(ny1, ny2)
            if top2 < seg_top:
                shift = seg_top - top2
                ny1 += shift; ny2 += shift
            elif bottom2 > seg_bot:
                shift = seg_bot - bottom2
                ny1 += shift; ny2 += shift

            coords_list.append((box, (nx1, ny1, nx2, ny2)))

        self.controller.update_boxes_coords(coords_list)
        self.controller.commit_coords_change()

    def show_context_menu(self, event):
        self.context_menu.delete(0, tk.END)

        cx = self.canvasx(event.x)
        cy = self.canvasy(event.y)
        clicked = self._hit_box(cx, cy)

        if clicked:
            self.context_menu.add_command(
                label=f"Drill Into '{clicked.label}'",
                command=lambda: self.controller.drill_into(clicked)
            )
            self.context_menu.add_separator()

        if self.controller.nav.depth > 0:
            self.context_menu.add_command(
                label="Drill Out (Go Back)",
                command=self.controller.drill_out
            )
            self.context_menu.add_separator()

        self.context_menu.add_command(
            label="Focus Target",
            command=self.zoom_focus_target
        )
        self.context_menu.add_command(
            label="Toggle Labels (T)",
            command=self.toggle_labels_visibility
        )

        self.context_menu.post(event.x_root, event.y_root)

    def zoom_focus_target(self):
        self._last_nav_key = None

        target_boxes = []
        if self.selected_boxes:
            target_boxes = self.selected_boxes
        elif self.controller.nav.current_parent:
            target_boxes = [self.controller.nav.current_parent]

        vw = self.winfo_width()
        vh = self.winfo_height()
        if vw <= 1 or vh <= 1:
            vw = 1200
            vh = 800

        if target_boxes:
            left = min(b.left for b in target_boxes)
            top = min(b.top for b in target_boxes)
            right = max(b.right for b in target_boxes)
            bottom = max(b.bottom for b in target_boxes)

            box_w = max(1, right - left)
            box_h = max(1, bottom - top)

            pad = 120.0
            fit_w = (vw - pad) / box_w
            fit_h = (vh - pad) / box_h

            self.zoom_factor = max(0.05, min(3.0, min(fit_w, fit_h)))

            center_x = (left + right) / 2.0
            center_y = (top + bottom) / 2.0

            self.update_view(center_abs=(center_x, center_y))
        else:
            # Root level, fit full image
            self.update_view()

    def toggle_labels_visibility(self):
        self.show_labels = not self.show_labels
        self.draw_boxes()
