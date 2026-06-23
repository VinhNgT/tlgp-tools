import sys
import tkinter as tk
from tkinter import ttk
from typing import Any, Protocol
from uuid import UUID

from annotator.models import Component
from annotator.rendering import (
    composite_gapped_image,
    compute_border_widths,
    compute_pill_font_size,
    compute_pill_padding,
    get_font,
    get_pill_coords,
    get_text_dimensions,
)
from PIL import Image, ImageDraw, ImageTk
from tlgp_logger import get_logger

from .transformer import CUT_GAP_PX, ViewportTransformer

logger = get_logger(__name__)


class GestureHandler(Protocol):
    """Protocol defining the interface that canvas expects from the gestures interpreter."""

    @property
    def resize_handle(self) -> str | None: ...

    @property
    def is_dragging(self) -> bool: ...

    @property
    def space_panning(self) -> bool: ...

    @space_panning.setter
    def space_panning(self, val: bool) -> None: ...

    def on_click(self, canvas: Any, event: Any, cx: float, cy: float) -> None: ...

    def on_drag(self, canvas: Any, event: Any, cx: float, cy: float) -> None: ...

    def on_release(self, canvas: Any, event: Any, cx: float, cy: float) -> None: ...

    def on_mouse_move(self, canvas: Any, event: Any, cx: float, cy: float) -> None: ...

    def on_right_click(self, canvas: Any, event: Any, cx: float, cy: float) -> None: ...

    def on_middle_click(self, canvas: Any, event: Any) -> None: ...

    def on_middle_drag(self, canvas: Any, event: Any) -> None: ...

    def on_middle_release(self, canvas: Any, event: Any, cx: float, cy: float) -> None: ...

    def on_control_click(
        self, canvas: Any, event: Any, cx: float, cy: float
    ) -> None: ...

    def on_scroll(self, canvas: Any, event: Any) -> None: ...

    def on_touchpad_scroll(self, canvas: Any, event: Any) -> Any: ...

    def zoom(
        self, canvas: Any, delta: float, mouse_pos: tuple[float, float]
    ) -> None: ...


class WelcomeScreen(ttk.Frame):
    def __init__(self, parent_canvas, on_import_zip, on_import_image, unreachable: bool = False, **kwargs):
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
        style.configure(
            "WelcomeError.TLabel",
            font=("", 10, "bold"),
            foreground="#e74c3c",
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

        btn_state = tk.DISABLED if unreachable else tk.NORMAL

        self.btn_zip = ttk.Button(
            btn_frame,
            text="Import Zip Project",
            style="WelcomeButton.TButton",
            command=on_import_zip,
            state=btn_state,
        )
        self.btn_zip.pack(side=tk.LEFT, padx=10)

        self.btn_img = ttk.Button(
            btn_frame,
            text="Import Screenshot",
            style="WelcomeButton.TButton",
            command=on_import_image,
            state=btn_state,
        )
        self.btn_img.pack(side=tk.LEFT, padx=10)

        self.lbl_status = ttk.Label(
            self,
            text="⚠️ Engine unreachable. Make sure the engine is running." if unreachable else "",
            style="WelcomeError.TLabel" if unreachable else "WelcomeDesc.TLabel",
            anchor="center",
        )
        self.lbl_status.pack(pady=(15, 0))

    def set_interactive(self, enabled: bool, unreachable: bool = False):
        btn_state = tk.NORMAL if enabled else tk.DISABLED
        self.btn_zip.config(state=btn_state)
        self.btn_img.config(state=btn_state)
        if unreachable:
            self.lbl_status.config(
                text="⚠️ Engine unreachable. Make sure the engine is running.",
                style="WelcomeError.TLabel",
            )
        else:
            self.lbl_status.config(
                text="",
                style="WelcomeDesc.TLabel",
            )


class AnnotationCanvasView(tk.Canvas):
    """Passive canvas rendering viewport widget. Exposes event delegate callbacks to the controller."""

    def __init__(
        self,
        parent,
        transformer: ViewportTransformer,
        gestures: GestureHandler,
        **kwargs,
    ):
        super().__init__(parent, highlightthickness=0, bg="#121212", **kwargs)
        self.transformer = transformer
        self.gestures = gestures

        self.full_pil_img = None
        self.current_pil_img = None
        self.image_item_id = None
        self.welcome_screen = None
        self.show_labels = True

        # Decoupled local state copies of store state variables
        self.zoom_factor = 1.0
        self.pan_offset = (0.0, 0.0)
        self.parent_stack = []
        self.selected_component_ids = []
        self.active_interaction = None
        self.workspace_state = None
        self.current_mode = "select"

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
        self.on_component_moved = None
        self.on_component_resized = None
        self.on_component_created = None
        self.on_request_context_menu = None

        # Callbacks to notify store updates via controller
        self.on_viewport_change_request = None
        self.on_active_interaction_changed = None
        self.on_selection_ids_changed = None
        self.on_viewport_size_changed = None
        self.on_mode_change_request = None

        self.bind("<Button-1>", self.on_click)
        self.bind("<B1-Motion>", self.on_drag)
        self.bind("<ButtonRelease-1>", self.on_release)
        self.bind("<Motion>", self.on_mouse_move)
        self.bind("<Configure>", self.on_canvas_resize)

        if self.tk.call("tk", "windowingsystem") == "aqua":
            self.bind("<Button-2>", self.on_right_click)
            self.bind("<Button-3>", self.on_middle_click)
            self.bind("<B3-Motion>", self.on_middle_drag)
            self.bind("<ButtonRelease-3>", self.on_middle_release)
        else:
            self.bind("<Button-3>", self.on_right_click)
            self.bind("<Button-2>", self.on_middle_click)
            self.bind("<B2-Motion>", self.on_middle_drag)
            self.bind("<ButtonRelease-2>", self.on_middle_release)

        self.bind("<Control-Button-1>", self._on_control_click)
        self.bind("<MouseWheel>", self._on_scroll)
        self.bind("<Button-4>", self._on_scroll)
        self.bind("<Button-5>", self._on_scroll)

        if sys.platform == "darwin":
            self.bind_all("<TouchpadScroll>", self._on_canvas_touchpad_scroll)

        self.space_pan_active = False

    def set_viewport_state(
        self,
        zoom_factor: float,
        pan_offset: tuple[float, float],
        parent_stack: list[UUID],
        current_mode: str,
        active_interaction: dict | None,
    ):
        if self.parent_stack != parent_stack:
            self._mask_cached_img = None
            self._mask_cached_key = None
            self._last_pil_img = None

        self.zoom_factor = zoom_factor
        self.pan_offset = pan_offset
        self.parent_stack = parent_stack
        self.current_mode = current_mode
        self.active_interaction = active_interaction
        self.queue_update_view()

    def set_workspace_state(
        self,
        workspace_state,
        active_interaction: dict | None = None,
    ):
        self.workspace_state = workspace_state
        self.active_interaction = active_interaction
        self.queue_update_view()

    def set_selection_state(
        self,
        selected_component_ids: list[UUID],
        active_interaction: dict | None = None,
    ):
        self.selected_component_ids = selected_component_ids
        self.active_interaction = active_interaction
        self.draw_boxes()

    def set_background_image(self, img: Image.Image | None, unreachable: bool = False):
        if img is None:
            self.full_pil_img = None
            self.current_pil_img = None
            if self.image_item_id is not None:
                self.delete(self.image_item_id)
                self.image_item_id = None
            self.show_welcome_screen(unreachable=unreachable)
            return

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

    def show_welcome_screen(self, unreachable: bool = False):
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
            unreachable=unreachable,
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

    def set_interactive(self, enabled: bool, unreachable: bool = False):
        if self.welcome_screen:
            self.welcome_screen.set_interactive(enabled, unreachable=unreachable)

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

        cut_lines = self.workspace_state.cutLines if self.workspace_state else []
        parent_stack = self.parent_stack
        if self.transformer.has_active_cuts(parent_stack, cut_lines):
            self.transformer.rebuild_segments(cut_lines)
            img_h += len(cut_lines) * CUT_GAP_PX

        ratio_w = cw / img_w
        ratio_h = ch / img_h
        fit_zoom = min(ratio_w, ratio_h) * 0.95

        zoom_factor = max(0.1, min(4.0, fit_zoom))
        pan_x = (cw - img_w * zoom_factor) / 2
        pan_y = (ch - img_h * zoom_factor) / 2
        if self.on_viewport_change_request:
            self.on_viewport_change_request(zoom_factor, (pan_x, pan_y))

    def queue_update_view(self):
        if not self._redraw_pending:
            self._redraw_pending = True
            self.after(16, self._execute_redraw)

    def _execute_redraw(self):
        self._redraw_pending = False
        self.update_view()

    def is_effectively_locked(self, box) -> bool:
        if getattr(box.visibility, "locked", False):
            return True
        if self.workspace_state and box.parentId:
            parent = self.workspace_state.components.get(box.parentId)
            if parent:
                return self.is_effectively_locked(parent)
        return False

    def is_effectively_visible(self, box) -> bool:
        if not getattr(box.visibility, "visible", True):
            return False
        if self.workspace_state and box.parentId:
            parent = self.workspace_state.components.get(box.parentId)
            if parent:
                return self.is_effectively_visible(parent)
        return True

    def update_view(self):
        if not self.full_pil_img:
            return

        cw = self.winfo_width()
        ch = self.winfo_height()
        if cw <= 1 or ch <= 1:
            return

        cut_lines = self.workspace_state.cutLines if self.workspace_state else []
        parent_stack = self.parent_stack
        cut_lines_tuple = tuple(cut_lines) if cut_lines else ()

        if self.transformer.has_active_cuts(parent_stack, cut_lines):
            self.transformer.rebuild_segments(cut_lines)
            if (
                self._last_pil_img is not self.full_pil_img
                or getattr(self, "_last_cut_lines", None) != cut_lines_tuple
            ):
                self.current_pil_img = composite_gapped_image(
                    self.full_pil_img,
                    self.transformer.segments,
                    self.transformer.cut_gap_px,
                )
                self._last_pil_img = self.full_pil_img
                self._last_cut_lines = cut_lines_tuple
        else:
            self.current_pil_img = self.full_pil_img
            self._last_pil_img = self.full_pil_img
            self._last_cut_lines = ()

        zoom_factor = self.zoom_factor
        pan_x, pan_y = self.pan_offset

        workspace_state = self.workspace_state
        state_revision = workspace_state.revision if workspace_state else 0
        workspace_changed = state_revision != getattr(
            self, "_last_workspace_revision", None
        )
        self._last_workspace_revision = state_revision

        parent_stack_tuple = tuple(parent_stack) if parent_stack else ()

        # Hybrid rendering decision: crop first when zoomed in to avoid resizing huge images,
        # otherwise resize the full background once and translate using canvas.coords.
        use_crop = zoom_factor > 1.1

        image_rebuilt = False
        disp_x, disp_y = 0.0, 0.0

        if use_crop:
            left_abs = -pan_x / zoom_factor
            top_abs = -pan_y / zoom_factor
            right_abs = (cw - pan_x) / zoom_factor
            bottom_abs = (ch - pan_y) / zoom_factor

            # Check if we are still within the previously rendered crop region (with margin)
            margin_abs = 50.0 / zoom_factor
            rebuild_crop = True

            last_crop = getattr(self, "_last_crop_box", None)
            if last_crop is not None:
                cl, ct, cr, cb = last_crop
                out_left = (left_abs < cl + margin_abs) and (cl > 0)
                out_top = (top_abs < ct + margin_abs) and (ct > 0)
                out_right = (right_abs > cr - margin_abs) and (
                    cr < self.current_pil_img.width
                )
                out_bottom = (bottom_abs > cb - margin_abs) and (
                    cb < self.current_pil_img.height
                )

                if not (out_left or out_top or out_right or out_bottom):
                    rebuild_crop = False

            state_key = (
                zoom_factor,
                id(self.current_pil_img),
                parent_stack_tuple,
                cut_lines_tuple,
            )

            if (
                state_key != getattr(self, "_zoom_cached_key", None)
                or self.image_item_id is None
                or rebuild_crop
            ):
                self._zoom_cached_key = state_key
                image_rebuilt = True

                # Compute new crop box with a 300px canvas-space buffer on each side
                buffer_abs = 300.0 / zoom_factor
                crop_left = int(max(0, left_abs - buffer_abs))
                crop_top = int(max(0, top_abs - buffer_abs))
                crop_right = int(
                    min(self.current_pil_img.width, right_abs + buffer_abs)
                )
                crop_bottom = int(
                    min(self.current_pil_img.height, bottom_abs + buffer_abs)
                )

                if crop_right <= crop_left:
                    crop_right = crop_left + 1
                if crop_bottom <= crop_top:
                    crop_bottom = crop_top + 1

                crop_box = (crop_left, crop_top, crop_right, crop_bottom)
                self._last_crop_box = crop_box

                cropped = self.current_pil_img.crop(crop_box)
                cropped = self._apply_cropped_parent_mask(
                    cropped, crop_left, crop_top, crop_right, crop_bottom
                )

                scaled_w = round((crop_right - crop_left) * zoom_factor)
                scaled_h = round((crop_bottom - crop_top) * zoom_factor)
                if scaled_w > 0 and scaled_h > 0:
                    resized = cropped.resize(
                        (scaled_w, scaled_h), Image.Resampling.BILINEAR
                    )
                    self._zoom_cached_photo = ImageTk.PhotoImage(resized)

                    if self.image_item_id is not None:
                        self.delete(self.image_item_id)

                    disp_x = crop_left * zoom_factor + pan_x
                    disp_y = crop_top * zoom_factor + pan_y

                    self.image_item_id = self.create_image(
                        disp_x, disp_y, image=self._zoom_cached_photo, anchor="nw"
                    )
                    self.tag_lower(self.image_item_id)

                self._last_pan_offset = (pan_x, pan_y)
            else:
                cl, ct, _, _ = self._last_crop_box
                disp_x = cl * zoom_factor + pan_x
                disp_y = ct * zoom_factor + pan_y
        else:
            state_key = (
                zoom_factor,
                id(self.current_pil_img),
                parent_stack_tuple,
                cut_lines_tuple,
            )

            if (
                state_key != getattr(self, "_zoom_cached_key", None)
                or self.image_item_id is None
            ):
                self._zoom_cached_key = state_key
                image_rebuilt = True
                self._last_crop_box = None

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
            target_bg_x = disp_x if use_crop else pan_x
            target_bg_y = disp_y if use_crop else pan_y
            dx = pan_x - self._last_pan_offset[0]
            dy = pan_y - self._last_pan_offset[1]
            if dx != 0 or dy != 0:
                if self.image_item_id is not None:
                    self.coords(self.image_item_id, target_bg_x, target_bg_y)
                self.move("ann", dx, dy)
                self._last_pan_offset = (pan_x, pan_y)

    def _get_or_create_full_parent_mask(self) -> Image.Image | None:
        state = self.workspace_state
        parent_stack = self.parent_stack
        if not parent_stack or not state:
            return None
        parent_id = parent_stack[-1]
        parent = state.components.get(parent_id)
        if not parent:
            return None

        img_w = self.current_pil_img.width
        img_h = self.current_pil_img.height
        cut_lines = state.cutLines if state else []
        cut_lines_tuple = tuple(cut_lines) if cut_lines else ()
        mask_key = (parent_id, img_w, img_h, cut_lines_tuple)

        if (
            mask_key != getattr(self, "_mask_cached_key", None)
            or self._mask_cached_img is None
        ):
            mask = Image.new("L", (img_w, img_h), 80)
            draw = ImageDraw.Draw(mask)
            b = parent.bounds

            # Map parent boundaries to the gap-shifted canvas coordinate system
            has_cuts = self.transformer.has_active_cuts(parent_stack, cut_lines)
            gap_top = self.transformer.gap_offset_for_y(b.top) if has_cuts else 0
            gap_bottom = self.transformer.gap_offset_for_y(b.bottom) if has_cuts else 0

            draw.rectangle([b.left, b.top + gap_top, b.right, b.bottom + gap_bottom], fill=255)
            self._mask_cached_img = mask
            self._mask_cached_key = mask_key

        return self._mask_cached_img


    def _apply_full_parent_mask(self, base_img: Image.Image) -> Image.Image:
        mask = self._get_or_create_full_parent_mask()
        if mask is None:
            return base_img
        bg = Image.new("RGB", base_img.size, (18, 18, 18))
        return Image.composite(base_img, bg, mask)

    def _apply_cropped_parent_mask(
        self, cropped: Image.Image, left: int, top: int, right: int, bottom: int
    ) -> Image.Image:
        mask = self._get_or_create_full_parent_mask()
        if mask is None:
            return cropped
        crop_mask = mask.crop((left, top, right, bottom))
        bg = Image.new("RGB", cropped.size, (18, 18, 18))
        return Image.composite(cropped, bg, crop_mask)

    def draw_boxes(self):
        self.delete("ann")
        state = self.workspace_state
        if not state:
            return

        zoom_factor = self.zoom_factor
        pan_offset = self.pan_offset
        parent_stack = self.parent_stack
        cut_lines = state.cutLines
        selected_boxes = [
            state.components[uid]
            for uid in self.selected_component_ids
            if uid in state.components
        ]

        active_int = self.active_interaction

        if (
            self.gestures.resize_handle
            and self.gestures.is_dragging
            and len(selected_boxes) == 1
        ):
            active_box = selected_boxes[0]
            union = self.get_children_bounds_union(active_box)
            if union:
                cx1, cy1, cx2, cy2 = union
                gcx1, gcy1 = self.transformer.to_canvas(
                    cx1,
                    cy1,
                    zoom_factor,
                    parent_stack,
                    cut_lines,
                    pan_offset=pan_offset,
                )
                gcx2, gcy2 = self.transformer.to_canvas(
                    cx2,
                    cy2,
                    zoom_factor,
                    parent_stack,
                    cut_lines,
                    pan_offset=pan_offset,
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

        boxes = self.get_active_boxes()
        non_selected = [b for b in boxes if b not in selected_boxes]
        selected = [b for b in boxes if b in selected_boxes]
        ordered_boxes = non_selected + selected

        for box in ordered_boxes:
            is_visible = self.is_effectively_visible(box)
            is_sel = box in selected_boxes

            if is_visible:
                color = "#0c8ce9" if is_sel else "#ff4444"
                pill_fill = "white"
            else:
                color = "#88bbee" if is_sel else "#aaaaaa"
                pill_fill = "#f0f0f0"

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
            if self.is_effectively_locked(box):
                rect_kwargs["dash"] = (4, 4)
            self.create_rectangle(cx1, cy1, cx2, cy2, **rect_kwargs)

            num = str(box.number)
            if num:
                tw, th, _top = get_text_dimensions(None, num, font_obj)
                pad_x, pad_y = compute_pill_padding(abs_font_size)

                pill_w = max(4, round((tw + pad_x) * zoom_factor))
                pill_h = max(4, round((th + pad_y) * zoom_factor))
                canvas_font_size = max(4, min(72, round(abs_font_size * zoom_factor)))

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
                    fill=pill_fill,
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

        if len(selected) == 1:
            selected_box = selected[0]
            if not self.is_effectively_locked(selected_box):
                self._draw_handles(selected_box)

        if self.image_item_id is not None:
            self.tag_lower(self.image_item_id)

    def _draw_handles(self, box: Component):
        if box not in self.get_active_boxes():
            return
        zoom_factor = self.zoom_factor
        pan_offset = self.pan_offset
        parent_stack = self.parent_stack
        cut_lines = self.workspace_state.cutLines if self.workspace_state else []
        active_int = self.active_interaction
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

    def get_active_boxes(self) -> list[Component]:
        state = self.workspace_state
        if not state:
            return []
        parent_stack = self.parent_stack
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

    def get_children_bounds_union(
        self, box: Component
    ) -> tuple[int, int, int, int] | None:
        state = self.workspace_state
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
        self.focus_set()
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
        self.focus_set()
        cx = self.canvasx(event.x)
        cy = self.canvasy(event.y)
        self.gestures.on_right_click(self, event, cx, cy)

    def on_middle_click(self, event):
        self.focus_set()
        self.gestures.on_middle_click(self, event)

    def on_middle_drag(self, event):
        self.gestures.on_middle_drag(self, event)

    def on_middle_release(self, event):
        cx = self.canvasx(event.x)
        cy = self.canvasy(event.y)
        self.gestures.on_middle_release(self, event, cx, cy)

    def _on_control_click(self, event):
        cx = self.canvasx(event.x)
        cy = self.canvasy(event.y)
        self.gestures.on_control_click(self, event, cx, cy)

    def _on_scroll(self, event):
        self.gestures.on_scroll(self, event)
        return "break"

    def _on_canvas_touchpad_scroll(self, event):
        return self.gestures.on_touchpad_scroll(self, event)

    def PreciseScrollDeltas(self, delta: Any) -> tuple[float, float]:
        """Resolves Tcl/Tk precise scroll deltas on macOS."""
        res = self.tk.call("tk::PreciseScrollDeltas", delta)
        deltas = self.tk.splitlist(res)
        return float(deltas[0]), float(deltas[1])

    def zoom(self, delta: float, mouse_pos: tuple[int, int] | None = None):
        self.gestures.zoom(self, delta, mouse_pos)

    def zoom_focus_target(self):
        state = self.workspace_state
        selected_boxes = [
            state.components[uid]
            for uid in self.selected_component_ids
            if uid in state.components
        ]

        target_boxes = []
        if selected_boxes:
            target_boxes = selected_boxes
        elif self.parent_stack and state:
            pid = self.parent_stack[-1]
            if pid in state.components:
                target_boxes = [state.components[pid]]

        if not target_boxes:
            self.fit_to_screen()
            return

        cw = self.winfo_width()
        ch = self.winfo_height()
        if cw <= 1 or ch <= 1:
            cw, ch = 800, 600

        parent_stack = self.parent_stack
        cut_lines = state.cutLines if state else []

        cx1, cy1 = self.transformer.to_canvas(
            min(b.bounds.left for b in target_boxes),
            min(b.bounds.top for b in target_boxes),
            1.0,
            parent_stack,
            cut_lines,
        )
        cx2, cy2 = self.transformer.to_canvas(
            max(b.bounds.right for b in target_boxes),
            max(b.bounds.bottom for b in target_boxes),
            1.0,
            parent_stack,
            cut_lines,
        )

        box_w = max(1.0, cx2 - cx1)
        box_h = max(1.0, cy2 - cy1)

        pad = 80.0
        fit_w = (cw - pad) / box_w
        fit_h = (ch - pad) / box_h

        zoom_factor = max(0.1, min(3.0, min(fit_w, fit_h)))

        cx = (cx1 + cx2) / 2.0
        cy = (cy1 + cy2) / 2.0

        scroll_x = (cw / 2) - cx * zoom_factor
        scroll_y = (ch / 2) - cy * zoom_factor

        if self.on_viewport_change_request:
            self.on_viewport_change_request(zoom_factor, (scroll_x, scroll_y))

    def set_mode(self, mode: str):
        self.current_mode = mode
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
        self.space_pan_active = True
        self.config(cursor=self._get_pan_cursor(active=False))

    def stop_space_pan(self):
        self.space_pan_active = False
        self.gestures.space_panning = False
        mode = self.current_mode
        if mode == "draw":
            self.config(cursor="crosshair")
        else:
            self.config(cursor="")

    def set_selection(self, boxes: list[Component]):
        ids = [b.id for b in boxes]
        if self.on_selection_ids_changed:
            self.on_selection_ids_changed(ids)
        if self.on_selection_changed:
            self.on_selection_changed(boxes)

    def drill_into(self, comp_id: UUID):
        if self.on_drill_into:
            self.on_drill_into(comp_id)

    def drill_out(self):
        if self.on_drill_out:
            self.on_drill_out()

    def trigger_request_context_menu(self, event, clicked):
        if self.on_request_context_menu:
            self.on_request_context_menu(event, clicked)

    def nudge_selection(self, dx: int, dy: int):
        state = self.workspace_state
        selected_boxes = [
            state.components[uid]
            for uid in self.selected_component_ids
            if uid in state.components
        ]
        if not selected_boxes:
            return

        moved_any = False
        for box in selected_boxes:
            if self.is_effectively_locked(box):
                continue
            box.bounds.x = int(box.bounds.x + dx)
            box.bounds.y = int(box.bounds.y + dy)
            if self.on_component_moved:
                self.on_component_moved(
                    str(box.id), int(box.bounds.x), int(box.bounds.y)
                )
            moved_any = True
        if moved_any:
            self.draw_boxes()

    def set_cursor(self, cursor_type: str) -> None:
        if cursor_type == "pan_active":
            cursor = self._get_pan_cursor(active=True)
        elif cursor_type == "pan_inactive":
            cursor = self._get_pan_cursor(active=False)
        elif cursor_type == "draw":
            cursor = "crosshair"
        elif cursor_type == "default":
            cursor = ""
        else:
            cursor = cursor_type
        try:
            self.config(cursor=cursor)
        except tk.TclError:
            pass

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

        if self.on_viewport_size_changed:
            self.on_viewport_size_changed(cw, ch)
