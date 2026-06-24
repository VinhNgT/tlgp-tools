"""Annotation canvas view — custom QWidget with QPainter rendering.

Renders the screenshot with annotation overlays using a two-layer pipeline:
- Base pixmap: full-resolution QPixmap rebuilt only on image/cut-line changes
- Paint-time scaling: QPainter handles zoom/pan transforms via hardware-accelerated
  drawPixmap(targetRect, sourcePixmap, sourceRect)

This avoids per-frame PIL resizing during pan/zoom interactions.
"""

from typing import Any
from uuid import UUID

from PIL import Image
from PySide6.QtCore import QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import (
    QBrush,
    QColor,
    QCursor,
    QFontMetrics,
    QMouseEvent,
    QPainter,
    QPalette,
    QPen,
    QPixmap,
    QWheelEvent,
)
from PySide6.QtWidgets import QWidget

from annotator.models import Component, WorkspaceState
from annotator.rendering import (
    composite_gapped_image,
    compute_border_widths,
    compute_pill_font_size,
    compute_pill_padding,
    get_font,
    get_pill_coords,
    get_text_dimensions,
)

from .design_system import (
    ColorSystem,
    get_body_font,
    get_ui_font,
)
from .gestures import GestureEvent, GestureInterpreter
from .image_utils import pil_to_qpixmap
from .transformer import ViewportTransformer

# We will use the central design system and system palette roles dynamically.

# ── Cursor Mapping ────────────────────────────────────────────────────

_CURSOR_MAP = {
    "default": Qt.CursorShape.ArrowCursor,
    "draw": Qt.CursorShape.CrossCursor,
    "pan_active": Qt.CursorShape.ClosedHandCursor,
    "pan_inactive": Qt.CursorShape.OpenHandCursor,
    "size_nw_se": Qt.CursorShape.SizeFDiagCursor,
    "size_ne_sw": Qt.CursorShape.SizeBDiagCursor,
    "size_ns": Qt.CursorShape.SizeVerCursor,
    "size_we": Qt.CursorShape.SizeHorCursor,
}


class AnnotationCanvasView(QWidget):
    """Custom widget that renders the screenshot with annotation overlays via QPainter.

    Integrates with GestureInterpreter for all mouse interactions and
    ViewportTransformer for coordinate mapping.
    """

    def __init__(
        self,
        parent=None,
        transformer: ViewportTransformer | None = None,
    ):
        super().__init__(parent)
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMouseTracking(True)
        self.setMinimumSize(200, 200)

        self.transformer = transformer or ViewportTransformer()
        self.gestures = GestureInterpreter(self.transformer)

        # ── State (read by gestures via canvas.*) ──────────────────
        self.full_pil_img: Image.Image | None = None
        self.workspace_state: WorkspaceState | None = None
        self.parent_stack: list[UUID] = []
        self.selected_component_ids: list[UUID] = []
        self.zoom_factor: float = 1.0
        self.pan_offset: tuple[float, float] = (0.0, 0.0)
        self.current_mode: str = "select"
        self.active_interaction: dict[UUID, Any] | None = None
        self.space_pan_active: bool = False
        self.show_labels: bool = True

        # ── Callbacks (set by controller) ─────────────────────────
        self.on_viewport_change_request = None
        self.on_active_interaction_changed = None
        self.on_component_moved = None
        self.on_component_resized = None
        self.on_component_created = None
        self.on_selection_ids_changed = None
        self.on_drill_into = None
        self.on_import_zip = None
        self.on_import_image = None
        self.on_drill_out = None
        self.on_request_context_menu = None
        self.on_canvas_mode_change_request = None
        self.on_viewport_size_changed = None

        # ── Rendering state ───────────────────────────────────────
        # Full-resolution QPixmap (rebuilt only on image/cut-line changes)
        self._base_pixmap: QPixmap | None = None
        self._base_cache_key: tuple | None = None
        self._redraw_pending = False

        # ── Temporary rect for draw/select gesture ────────────────
        self._temp_rect: tuple[float, float, float, float, str, bool, int] | None = None

    # ── Public canvas API (called by gestures / controller) ────────────

    def set_background_image(self, pil_img: Image.Image | None):
        """Set the background PIL image (full stitched screenshot)."""
        self.full_pil_img = pil_img
        self._base_cache_key = None
        self._base_pixmap = None
        if pil_img:
            self.transformer.update_image_size(pil_img.width, pil_img.height)
        self.schedule_redraw()

    def get_active_boxes(self) -> list[Component]:
        """Return visible child components at the current hierarchy level."""
        ws = self.workspace_state
        if not ws:
            return []
        if self.parent_stack:
            parent = ws.components.get(self.parent_stack[-1])
            if parent:
                return [
                    ws.components[cid]
                    for cid in parent.childrenIds
                    if cid in ws.components
                ]
        return [
            ws.components[cid]
            for cid in ws.rootComponents
            if cid in ws.components
        ]

    def is_effectively_locked(self, comp: Component) -> bool:
        ws = self.workspace_state
        if not ws:
            return False
        if comp.visibility.locked:
            return True
        for pid in self.parent_stack:
            p = ws.components.get(pid)
            if p and p.visibility.locked:
                return True
        return False

    def is_effectively_visible(self, comp: Component) -> bool:
        if not comp.visibility.visible:
            return False
        ws = self.workspace_state
        if not ws:
            return True
        for pid in self.parent_stack:
            p = ws.components.get(pid)
            if p and not p.visibility.visible:
                return False
        return True

    def get_children_bounds_union(self, comp: Component) -> tuple[int, int, int, int] | None:
        ws = self.workspace_state
        if not ws or not comp.childrenIds:
            return None
        min_x, min_y = float("inf"), float("inf")
        max_x, max_y = float("-inf"), float("-inf")
        for cid in comp.childrenIds:
            child = ws.components.get(cid)
            if child:
                b = child.bounds
                min_x = min(min_x, b.left)
                min_y = min(min_y, b.top)
                max_x = max(max_x, b.right)
                max_y = max(max_y, b.bottom)
        if min_x == float("inf"):
            return None
        return int(min_x), int(min_y), int(max_x), int(max_y)

    def set_selection(self, boxes: list[Component]):
        ids = [b.id for b in boxes]
        if ids != self.selected_component_ids:
            self.selected_component_ids = ids
            if self.on_selection_ids_changed:
                self.on_selection_ids_changed(ids)
            self.update()

    def set_workspace_state(
        self, workspace_state: WorkspaceState | None, active_interaction=None
    ):
        """Update workspace state and active interaction from controller."""
        self.workspace_state = workspace_state
        self.active_interaction = active_interaction
        self.schedule_redraw()

    def set_selection_state(self, selected_ids: list[UUID], active_interaction=None):
        """Update selection and active interaction from controller."""
        self.selected_component_ids = selected_ids
        self.active_interaction = active_interaction
        self.schedule_redraw()

    def set_viewport_state(
        self,
        zoom_factor: float,
        pan_offset: tuple[float, float],
        parent_stack: list[UUID],
        current_mode: str,
        active_interaction=None,
    ):
        """Update viewport parameters from controller."""
        self.zoom_factor = zoom_factor
        self.pan_offset = pan_offset
        self.parent_stack = parent_stack
        self.current_mode = current_mode
        self.active_interaction = active_interaction
        self.schedule_redraw()

    def fit_to_screen(self):
        """Adjust zoom and pan to fit the full image in the viewport."""
        if not self.full_pil_img:
            return
        vw, vh = self.width(), self.height()
        if vw <= 1 or vh <= 1:
            vw, vh = 800, 600
        img_w, img_h = self.full_pil_img.width, self.full_pil_img.height
        zoom_x = (vw - 40) / img_w
        zoom_y = (vh - 40) / img_h
        new_zoom = max(0.1, min(1.0, min(zoom_x, zoom_y)))
        pad_x = (vw - img_w * new_zoom) / 2
        pad_y = (vh - img_h * new_zoom) / 2
        if self.on_viewport_change_request:
            self.on_viewport_change_request(new_zoom, (pad_x, pad_y))

    def drill_into(self, comp_id: UUID):
        """Drill into a component (delegate to controller via callback)."""
        if self.on_drill_into:
            self.on_drill_into(comp_id)

    def drill_out(self):
        """Drill out of the current parent (delegate to controller via callback)."""
        if self.on_drill_out:
            self.on_drill_out()

    def zoom_focus_target(self):
        """Zoom and pan to focus on the selected component."""
        ws = self.workspace_state
        if not ws or not self.selected_component_ids:
            self.fit_to_screen()
            return
        comp = ws.components.get(self.selected_component_ids[-1])
        if not comp:
            self.fit_to_screen()
            return
        vw, vh = self.width(), self.height()
        bw = comp.bounds.w
        bh = comp.bounds.h
        zoom_x = (vw - 40) / bw if bw > 0 else 1.0
        zoom_y = (vh - 40) / bh if bh > 0 else 1.0
        new_zoom = max(0.1, min(4.0, min(zoom_x, zoom_y)))
        pad_x = (vw / 2) - (comp.bounds.left + bw / 2) * new_zoom
        pad_y = (vh / 2) - (comp.bounds.top + bh / 2) * new_zoom
        if self.on_viewport_change_request:
            self.on_viewport_change_request(new_zoom, (pad_x, pad_y))

    def toggle_labels_visibility(self):
        """Toggle rendering of annotation labels."""
        self.show_labels = not self.show_labels
        self.update()

    def set_cursor(self, name: str):
        cursor = _CURSOR_MAP.get(name, Qt.CursorShape.ArrowCursor)
        self.setCursor(QCursor(cursor))

    def set_temp_rect(
        self,
        x1: float, y1: float, x2: float, y2: float,
        color: str | None = None, dash: bool = False, width: int = 1,
    ):
        if color is None:
            color = ColorSystem.get_box_active()
        self._temp_rect = (x1, y1, x2, y2, color, dash, width)
        self.update()

    def update_temp_rect(self, x1: float, y1: float, x2: float, y2: float):
        if self._temp_rect:
            _, _, _, _, color, dash, width = self._temp_rect
            self._temp_rect = (x1, y1, x2, y2, color, dash, width)
            self.update()

    def clear_temp_rect(self):
        self._temp_rect = None
        self.update()

    def is_text_focused(self) -> bool:
        """Check if a text widget in the main window currently has focus."""
        main_win = self.window()
        if hasattr(main_win, "is_text_focused"):
            return main_win.is_text_focused()
        return False

    def clear_text_focus(self):
        """Clear text focus by moving focus to this canvas."""
        self.setFocus()



    def schedule_redraw(self):
        """Schedule a deferred repaint (coalesces rapid updates)."""
        if not self._redraw_pending:
            self._redraw_pending = True
            QTimer.singleShot(16, self._execute_redraw)

    def _execute_redraw(self):
        self._redraw_pending = False
        self._rebuild_base_pixmap()
        self.update()

    # ── Rendering Pipeline ────────────────────────────────────────────

    def _rebuild_base_pixmap(self):
        """Rebuild the full-resolution base pixmap from the PIL image.

        Only rebuilds when cut-lines or parent-stack change — NOT on
        zoom/pan/selection changes. Paint-time scaling handles those.
        """
        if not self.full_pil_img:
            self._base_pixmap = None
            return

        ws = self.workspace_state
        cut_lines = ws.cutLines if ws else []

        self.transformer.rebuild_segments(cut_lines)

        cache_key = (
            id(self.full_pil_img),
            tuple(cut_lines),
            tuple(self.parent_stack),
        )
        if cache_key == self._base_cache_key and self._base_pixmap is not None:
            return
        self._base_cache_key = cache_key

        # Composite with cut-line gaps
        segments = self.transformer.segments
        if segments and len(segments) > 1:
            composited = composite_gapped_image(
                self.full_pil_img, segments, self.transformer.cut_gap_px
            )
        else:
            composited = self.full_pil_img

        self._base_pixmap = pil_to_qpixmap(composited)

    def paintEvent(self, event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        p.fillRect(self.rect(), QColor(ColorSystem.get_canvas_bg()))

        if not self.full_pil_img or not self._base_pixmap:
            p.end()
            return

        pan_x, pan_y = self.pan_offset
        zoom = self.zoom_factor
        src_w = self._base_pixmap.width()
        src_h = self._base_pixmap.height()

        # Paint-time scaling — QPainter handles the zoom transform
        target_rect = QRectF(pan_x, pan_y, src_w * zoom, src_h * zoom)
        source_rect = QRectF(0, 0, src_w, src_h)

        # Parent mask overlay — painted via QPainter, not PIL
        ws = self.workspace_state
        cut_lines = ws.cutLines if ws else []
        parent_comp = None
        if self.parent_stack and ws:
            parent_comp = ws.components.get(self.parent_stack[-1])

        if parent_comp:
            # Draw the full image darkened
            p.setOpacity(0.4)
            p.drawPixmap(target_rect, self._base_pixmap, source_rect)
            p.setOpacity(1.0)

            # Compute parent region in canvas coordinates
            gap = (
                self.transformer.gap_offset_for_y(parent_comp.bounds.top)
                if self.transformer.has_active_cuts(self.parent_stack, cut_lines)
                else 0
            )
            px1 = parent_comp.bounds.left
            py1 = parent_comp.bounds.top + gap
            px2 = parent_comp.bounds.right
            py2 = parent_comp.bounds.bottom + gap

            # Redraw the parent region at full brightness (clip restore)
            parent_target = QRectF(
                pan_x + px1 * zoom,
                pan_y + py1 * zoom,
                (px2 - px1) * zoom,
                (py2 - py1) * zoom,
            )
            parent_source = QRectF(px1, py1, px2 - px1, py2 - py1)
            p.drawPixmap(parent_target, self._base_pixmap, parent_source)
        else:
            p.drawPixmap(target_rect, self._base_pixmap, source_rect)

        # Draw annotations
        self._paint_annotations(p)

        # Draw temporary rect (selection / draw)
        if self._temp_rect:
            self._paint_temp_rect(p)

        p.end()

    def _paint_annotations(self, p: QPainter):
        """Paint annotation boxes and number pills for active components."""
        ws = self.workspace_state
        if not ws:
            return

        active_comps = self.get_active_boxes()
        if not active_comps:
            return

        cut_lines = ws.cutLines if ws else []
        zoom = self.zoom_factor

        # Compute rendering params (constant for all components at this level)
        parent_comp = (
            ws.components.get(self.parent_stack[-1]) if self.parent_stack else None
        )
        full_img_width = self.full_pil_img.width if self.full_pil_img else 1
        font_size = compute_pill_font_size(parent_comp, full_img_width)
        abs_box_border, abs_pill_outline = compute_border_widths(parent_comp, full_img_width)
        pad_x, pad_y = compute_pill_padding(font_size)

        # PIL font for text measurement
        pil_font = get_font(font_size)

        # QFont + metrics created once for the entire level (not per component)
        pill_font_size = max(4, min(72, round(font_size * zoom)))
        qfont = get_ui_font(size=pill_font_size, bold=True)
        pill_ascent = QFontMetrics(qfont).ascent()

        border_width = max(1, round(abs_box_border * zoom))
        pill_outline_width = max(1, round(abs_pill_outline * zoom))
        inactive_color = QColor(ColorSystem.get_box_inactive())
        box_pen = QPen(inactive_color, border_width)
        pill_outline_pen = QPen(inactive_color, pill_outline_width)
        pill_text_pen = QPen(inactive_color)

        non_selected = [comp for comp in active_comps if comp.id not in self.selected_component_ids]
        selected = [comp for comp in active_comps if comp.id in self.selected_component_ids]
        ordered_comps = non_selected + selected

        if len(selected) == 1 and self.gestures.resize_handle and self.gestures.is_dragging:
            comp = selected[0]
            union = self.get_children_bounds_union(comp)
            if union:
                cx1, cy1, cx2, cy2 = union
                gcx1, gcy1 = self.transformer.to_canvas(
                    cx1, cy1, zoom, self.parent_stack, cut_lines,
                    pan_offset=self.pan_offset,
                )
                gcx2, gcy2 = self.transformer.to_canvas(
                    cx2, cy2, zoom, self.parent_stack, cut_lines,
                    pan_offset=self.pan_offset,
                )
                overlay_color = QColor(ColorSystem.get_child_bounds_overlay())
                dash_pen = QPen(overlay_color, 2)
                dash_pen.setStyle(Qt.PenStyle.DashLine)
                p.setPen(dash_pen)
                p.setBrush(Qt.BrushStyle.NoBrush)
                p.drawRect(QRectF(gcx1, gcy1, gcx2 - gcx1, gcy2 - gcy1))

                font = get_body_font()
                font.setBold(True)
                font.setItalic(True)
                p.setFont(font)
                p.setPen(QPen(overlay_color))
                p.drawText(QPointF(gcx1 + 4, gcy1 + 13), "Child Bounds")

        for comp in ordered_comps:
            is_selected = comp.id in self.selected_component_ids
            is_visible = comp.visibility.visible
            is_locked = comp.visibility.locked

            if is_visible:
                color_hex = ColorSystem.get_box_active() if is_selected else ColorSystem.get_box_inactive()
                pill_fill_col = QColor(ColorSystem.get_pill_bg_visible())
            else:
                color_hex = ColorSystem.get_box_active_hidden() if is_selected else ColorSystem.get_box_inactive_hidden()
                pill_fill_col = QColor(ColorSystem.get_pill_bg_hidden())

            comp_color = QColor(color_hex)
            lw = border_width + 1 if is_selected else border_width
            box_pen.setColor(comp_color)
            box_pen.setWidth(lw)
            if is_locked:
                box_pen.setStyle(Qt.PenStyle.DashLine)
            else:
                box_pen.setStyle(Qt.PenStyle.SolidLine)

            pill_outline_pen.setColor(comp_color)
            pill_text_pen.setColor(comp_color)

            bounds = comp.bounds
            if self.active_interaction and comp.id in self.active_interaction:
                bounds = self.active_interaction[comp.id]

            cx1, cy1 = self.transformer.to_canvas(
                bounds.left, bounds.top, zoom, self.parent_stack, cut_lines,
                pan_offset=self.pan_offset,
            )
            cx2, cy2 = self.transformer.to_canvas(
                bounds.right, bounds.bottom, zoom, self.parent_stack, cut_lines,
                pan_offset=self.pan_offset,
            )

            # Box border
            p.setPen(box_pen)
            p.setBrush(Qt.BrushStyle.NoBrush)
            p.drawRect(QRectF(cx1, cy1, cx2 - cx1, cy2 - cy1))

            # Number pill
            num_str = comp.number
            tw, th, _top_offset = get_text_dimensions(None, num_str, pil_font)

            scaled_tw = tw * zoom
            scaled_th = th * zoom
            scaled_pad_x = pad_x * zoom
            scaled_pad_y = pad_y * zoom

            pill_w = scaled_tw + scaled_pad_x
            pill_h = scaled_th + scaled_pad_y

            pill_corner = comp.style.pillCorner
            pill_x, pill_y = get_pill_coords(
                cx1, cy1, cx2, cy2, pill_w, pill_h, pill_corner
            )

            p.setPen(pill_outline_pen)
            p.setBrush(QBrush(pill_fill_col))
            p.drawRect(QRectF(pill_x, pill_y, pill_w, pill_h))

            # Pill text
            p.setFont(qfont)
            p.setPen(pill_text_pen)
            text_x = pill_x + scaled_pad_x / 2
            text_y = pill_y + scaled_pad_y / 2 + pill_ascent
            p.drawText(QPointF(text_x, text_y), num_str)

            if self.show_labels and comp.label:
                font = get_body_font()
                p.setFont(font)
                p.setPen(pill_text_pen)
                p.drawText(QPointF(cx1, cy2 + 13), comp.label)

            # Selection handles
            if is_selected and not is_locked:
                self._paint_handles(p, cx1, cy1, cx2, cy2)

    def _paint_handles(self, p: QPainter, cx1: float, cy1: float, cx2: float, cy2: float):
        """Paint resize handles around a selected component."""
        mx = (cx1 + cx2) / 2
        my = (cy1 + cy2) / 2
        hs = 4

        handles = [
            (cx1, cy1), (mx, cy1), (cx2, cy1),
            (cx1, my),             (cx2, my),
            (cx1, cy2), (mx, cy2), (cx2, cy2),
        ]

        palette = self.palette()
        p.setPen(QPen(palette.color(QPalette.ColorRole.Highlight), 1))
        p.setBrush(QBrush(palette.color(QPalette.ColorRole.Base)))
        for hx, hy in handles:
            p.drawRect(QRectF(hx - hs, hy - hs, hs * 2, hs * 2))

    def _paint_temp_rect(self, p: QPainter):
        """Paint the temporary selection/drawing rectangle."""
        if not self._temp_rect:
            return
        x1, y1, x2, y2, color, dash, width = self._temp_rect
        pen = QPen(QColor(color), width)
        if dash:
            pen.setStyle(Qt.PenStyle.DashLine)
        p.setPen(pen)
        p.setBrush(Qt.BrushStyle.NoBrush)
        p.drawRect(QRectF(x1, y1, x2 - x1, y2 - y1))

    # ── Event Handlers ────────────────────────────────────────────────

    def _make_gesture_event(self, event: QMouseEvent) -> GestureEvent:
        """Convert a QMouseEvent to a framework-agnostic GestureEvent."""
        pos = event.position()
        gpos = event.globalPosition()
        mods = event.modifiers()
        return GestureEvent(
            x=pos.x(),
            y=pos.y(),
            x_root=int(gpos.x()),
            y_root=int(gpos.y()),
            shift=bool(mods & Qt.KeyboardModifier.ShiftModifier),
            ctrl=bool(mods & Qt.KeyboardModifier.ControlModifier),
        )



    def mousePressEvent(self, event: QMouseEvent):
        if not self.full_pil_img:
            return

        ge = self._make_gesture_event(event)
        cx, cy = ge.x, ge.y

        if event.button() == Qt.MouseButton.LeftButton:
            if ge.ctrl and not ge.shift:
                self.gestures.on_control_click(self, ge, cx, cy)
            else:
                self.gestures.on_click(self, ge, cx, cy)
        elif event.button() == Qt.MouseButton.MiddleButton:
            self.gestures.on_middle_click(self, ge)
        elif event.button() == Qt.MouseButton.RightButton:
            self.gestures.on_right_click(self, ge, cx, cy)

    def mouseMoveEvent(self, event: QMouseEvent):
        if not self.full_pil_img:
            return

        ge = self._make_gesture_event(event)
        cx, cy = ge.x, ge.y

        if event.buttons() & Qt.MouseButton.LeftButton:
            self.gestures.on_drag(self, ge, cx, cy)
        elif event.buttons() & Qt.MouseButton.MiddleButton:
            self.gestures.on_middle_drag(self, ge)
        else:
            self.gestures.on_mouse_move(self, ge, cx, cy)

    def mouseReleaseEvent(self, event: QMouseEvent):
        if not self.full_pil_img:
            return

        ge = self._make_gesture_event(event)
        cx, cy = ge.x, ge.y

        if event.button() == Qt.MouseButton.LeftButton:
            self.gestures.on_release(self, ge, cx, cy)
        elif event.button() == Qt.MouseButton.MiddleButton:
            self.gestures.on_middle_release(self, ge, cx, cy)

    def wheelEvent(self, event: QWheelEvent):
        if not self.full_pil_img:
            return

        mods = event.modifiers()
        ctrl = bool(mods & Qt.KeyboardModifier.ControlModifier)
        shift = bool(mods & Qt.KeyboardModifier.ShiftModifier)
        pos = event.position()

        pixel_delta = event.pixelDelta()
        if not pixel_delta.isNull():
            self.gestures.on_trackpad_scroll(
                self,
                delta_x=pixel_delta.x(),
                delta_y=pixel_delta.y(),
                mouse_x=pos.x(),
                mouse_y=pos.y(),
                ctrl=ctrl,
            )
        else:
            angle = event.angleDelta()
            delta = angle.y() if angle.y() != 0 else angle.x()
            self.gestures.on_scroll(
                self,
                delta=delta,
                mouse_x=pos.x(),
                mouse_y=pos.y(),
                shift=shift,
                ctrl=ctrl,
            )

        event.accept()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.on_viewport_size_changed:
            self.on_viewport_size_changed(self.width(), self.height())
        self.schedule_redraw()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Space and not event.isAutoRepeat():
            self.space_pan_active = True
            self.set_cursor("pan_inactive")
            event.accept()
            return
        super().keyPressEvent(event)

    def keyReleaseEvent(self, event):
        if event.key() == Qt.Key.Key_Space and not event.isAutoRepeat():
            self.space_pan_active = False
            self.set_cursor("default")
            event.accept()
            return
        super().keyReleaseEvent(event)
