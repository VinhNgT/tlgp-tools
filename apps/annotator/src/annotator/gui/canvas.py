"""Annotation canvas view — custom QWidget with QPainter rendering.

Renders the screenshot with annotation overlays using a two-layer pipeline:
- Base pixmap: full-resolution QPixmap rebuilt only on image/cut-line changes
- Paint-time scaling: QPainter handles zoom/pan transforms via hardware-accelerated
  drawPixmap(targetRect, sourcePixmap, sourceRect)

This avoids per-frame PIL resizing during pan/zoom interactions.
"""

import math
import time
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from PIL import Image
from PySide6.QtCore import QEvent, QPointF, QRectF, Qt, QTimer
from PySide6.QtGui import (
    QCursor,
    QMouseEvent,
    QPainter,
    QPalette,
    QPixmap,
    QWheelEvent,
)
from PySide6.QtWidgets import QWidget

from annotator.models import Component, WorkspaceState
from annotator.rendering import (
    composite_gapped_image,
    compute_border_widths,
)

from .callbacks import CanvasCallbacks
from .canvas_renderer import CanvasRenderer, CanvasRenderState
from .gestures import GestureEvent, GestureInterpreter
from .gestures.hit_testing import HitTester
from .image_utils import pil_to_qpixmap
from .transformer import ViewportTransformer
from .viewport_calculator import ViewportCalculator
from .viewport_context import ViewportContext


@dataclass
class TempRect:
    """Temporary rectangle rendered during draw/select gestures."""

    x1: float
    y1: float
    x2: float
    y2: float
    color: str = "#0000FF"
    dash: bool = False
    width: int = 1


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
    "resize_nw": Qt.CursorShape.SizeFDiagCursor,
    "resize_se": Qt.CursorShape.SizeFDiagCursor,
    "resize_ne": Qt.CursorShape.SizeBDiagCursor,
    "resize_sw": Qt.CursorShape.SizeBDiagCursor,
    "resize_n": Qt.CursorShape.SizeVerCursor,
    "resize_s": Qt.CursorShape.SizeVerCursor,
    "resize_w": Qt.CursorShape.SizeHorCursor,
    "resize_e": Qt.CursorShape.SizeHorCursor,
    "move": Qt.CursorShape.SizeAllCursor,
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
        self.setObjectName("AnnotationCanvas")
        self.setFocusPolicy(Qt.FocusPolicy.StrongFocus)
        self.setMouseTracking(True)
        self.setMinimumSize(200, 200)

        self.transformer = transformer or ViewportTransformer()
        self._renderer = CanvasRenderer(self.transformer)
        self.gestures = GestureInterpreter(self.transformer)
        self.callbacks = CanvasCallbacks()

        # ── Mouse deadzone and hold configuration ───────────────
        self.deadzone_radius: float = 5.0
        self.deadzone_enabled: bool = True
        self.hold_timeout_ms: int = 300

        self._press_pos: QPointF | None = None
        self._deadzone_bypassed: bool = False

        self._hold_timer: QTimer = QTimer(self)
        self._hold_timer.setSingleShot(True)
        self._hold_timer.timeout.connect(self._on_hold_timer_timeout)

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
        self.show_labels: bool = False
        self._needs_fit: bool = False

        # ── Callbacks (set by controller) ─────────────────────────
        self.callbacks.on_selection_ids_changed = None
        self.callbacks.on_canvas_mode_change_request = None
        self.callbacks.on_viewport_size_changed = None

        # ── Rendering state ───────────────────────────────────────
        # Full-resolution QPixmap (rebuilt only on image/cut-line changes)
        self._base_pixmap: QPixmap | None = None
        self._base_cache_key: tuple | None = None

        # ── Temporary rect for draw/select gesture ────────────────
        self._temp_rect: TempRect | None = None

        # ── Mouse position tracking ───────────────────────────────
        self._last_mouse_cx: float | None = None
        self._last_mouse_cy: float | None = None

    # ── Public canvas API (called by gestures / controller) ────────────

    def set_background_image(self, pil_img: Image.Image | None):
        """Set the background PIL image (full stitched screenshot)."""
        self.full_pil_img = pil_img
        self._base_cache_key = None
        self._base_pixmap = None
        if pil_img:
            self.transformer.update_image_size(pil_img.width, pil_img.height)
            self._needs_fit = True
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
        return [ws.components[cid] for cid in ws.rootComponents if cid in ws.components]

    def get_selected_components(self) -> list[Component]:
        """Resolve selected component IDs to Component objects."""
        ws = self.workspace_state
        if not ws:
            return []
        return [
            ws.components[uid]
            for uid in self.selected_component_ids
            if uid in ws.components
        ]

    def get_selected_border_width(self, zoom: float) -> int:
        """Returns the border width (lw) for a selected component on the canvas."""
        ws = self.workspace_state
        if not ws:
            return 1
        parent_comp = None
        if self.parent_stack:
            parent_comp = ws.components.get(self.parent_stack[-1])
        full_img_width = self.full_pil_img.width if self.full_pil_img else 1

        abs_box_border, _ = compute_border_widths(parent_comp, full_img_width)
        border_width = max(1, round(abs_box_border * zoom))
        return border_width + 1

    def get_children_bounds_union(
        self, comp: Component
    ) -> tuple[int, int, int, int] | None:
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

    def resolve_boundary(self) -> tuple[float, float, float, float]:
        """Resolves the boundaries for component drawing/movement/resizing."""
        ws = self.workspace_state
        if ws:
            # If we are NOT currently drawing a new box, check the selected component's parent
            if not (hasattr(self, "gestures") and self.gestures.state.has_temp_rect):
                selected = self.get_selected_components()
                if len(selected) == 1:
                    parent_id = selected[0].parentId
                    if parent_id and parent_id in ws.components:
                        p = ws.components[parent_id].bounds
                        return (
                            float(p.left),
                            float(p.top),
                            float(p.right),
                            float(p.bottom),
                        )

            # Fallback to the active parent component boundary if one is entered (in the stack)
            if self.parent_stack:
                active_parent_id = self.parent_stack[-1]
                if active_parent_id in ws.components:
                    p = ws.components[active_parent_id].bounds
                    return float(p.left), float(p.top), float(p.right), float(p.bottom)

        # Fallback to full image boundary if available
        if self.full_pil_img:
            return (
                0.0,
                0.0,
                float(self.full_pil_img.width),
                float(self.full_pil_img.height),
            )

        return 0.0, 0.0, float("inf"), float("inf")

    def set_selection(self, boxes: list[Component]):
        ids = [b.id for b in boxes]
        if ids != self.selected_component_ids:
            self.selected_component_ids = ids
            if self.callbacks.on_selection_ids_changed:
                self.callbacks.on_selection_ids_changed(ids)
            self.update()
            self.update_canvas_cursor()

    def set_workspace_state(
        self, workspace_state: WorkspaceState | None, active_interaction=None
    ):
        """Update workspace state and active interaction from controller."""
        self.workspace_state = workspace_state
        self.active_interaction = active_interaction
        self.schedule_redraw()
        self.update_canvas_cursor()

    def set_selection_state(self, selected_ids: list[UUID], active_interaction=None):
        """Update selection and active interaction from controller."""
        self.selected_component_ids = selected_ids
        self.active_interaction = active_interaction
        self.schedule_redraw()
        self.update_canvas_cursor()

    def set_viewport_state(
        self,
        zoom_factor: float,
        pan_offset: tuple[float, float],
        parent_stack: list[UUID],
        current_mode: str,
        active_interaction=None,
    ):
        """Update viewport parameters from controller."""
        viewport_changed = (zoom_factor != self.zoom_factor) or (
            pan_offset != self.pan_offset
        )
        self.zoom_factor = zoom_factor
        self.pan_offset = pan_offset
        self.parent_stack = parent_stack
        if self.space_pan_active and current_mode != "pan":
            self.mode_before_space = current_mode
        self.current_mode = current_mode
        self.active_interaction = active_interaction
        if viewport_changed and not getattr(self, "_is_fitting", False):
            self._needs_fit = False
        self.schedule_redraw()
        self.update_canvas_cursor()

    def fit_to_screen(self):
        """Adjust zoom and pan to fit the active container (selected box, parent component, or full image) in the viewport."""
        if not self.full_pil_img:
            return
        self.gestures.state.ignore_momentum = True
        self._needs_fit = True
        vw, vh = self.width(), self.height()
        if vw <= 1 or vh <= 1:
            vw, vh = 800, 600

        ws = self.workspace_state
        ctx = self.make_viewport_ctx()
        target_comp = None
        if ws:
            if self.selected_component_ids:
                target_comp = ws.components.get(self.selected_component_ids[-1])
            if not target_comp and self.parent_stack:
                target_comp = ws.components.get(self.parent_stack[-1])

        new_zoom, pad_x, pad_y = ViewportCalculator.calculate_fit(
            vw,
            vh,
            target_comp,
            self.full_pil_img.width,
            self.full_pil_img.height,
            ctx,
            self.transformer,
        )

        self._is_fitting = True
        try:
            if self.callbacks.on_viewport_change_request:
                self.callbacks.on_viewport_change_request(new_zoom, (pad_x, pad_y))
        finally:
            self._is_fitting = False

    def drill_into(self, comp_id: UUID):
        """Drill into a component (delegate to controller via callback)."""
        if self.callbacks.on_drill_into:
            self.callbacks.on_drill_into(comp_id)

    def drill_out(self):
        """Drill out of the current parent (delegate to controller via callback)."""
        if self.callbacks.on_drill_out:
            self.callbacks.on_drill_out()

    def toggle_labels_visibility(self):
        """Toggle rendering of annotation labels."""
        self.show_labels = not self.show_labels
        self.update()

    def set_cursor(self, name: str):
        cursor = _CURSOR_MAP.get(name, Qt.CursorShape.ArrowCursor)
        self.setCursor(QCursor(cursor))

    def update_canvas_cursor(self):
        """Update the widget cursor based on the current mode, hover state, and modifier keys."""
        if not self.full_pil_img:
            self.set_cursor("default")
            return

        if (
            self.space_pan_active
            or self.gestures.state.space_panning
            or self.current_mode == "pan"
        ):
            if self.gestures.state.space_panning or (
                self._press_pos is not None and self._deadzone_bypassed
            ):
                self.set_cursor("pan_active")
            else:
                self.set_cursor("pan_inactive")
            return

        if self.current_mode == "draw":
            self.set_cursor("draw")
            return

        if self.current_mode == "select":
            if self.gestures.state.is_dragging and self.gestures.state.resize_handle:
                cursors = {
                    "nw": "resize_nw",
                    "n": "resize_n",
                    "ne": "resize_ne",
                    "w": "resize_w",
                    "e": "resize_e",
                    "sw": "resize_sw",
                    "s": "resize_s",
                    "se": "resize_se",
                }
                handle = self.gestures.state.resize_handle
                self.set_cursor(cursors.get(handle, "default"))
                return

            if (
                self.gestures.state.is_dragging
                and not self.gestures.state.resize_handle
            ):
                # Dragging components uses the normal pointer (ArrowCursor) per design requirements.
                self.set_cursor("default")
                return

            if self._last_mouse_cx is None or self._last_mouse_cy is None:
                self.set_cursor("default")
                return

            ctx = self.make_viewport_ctx()
            selected_boxes = self.get_selected_components()

            lw = self.get_selected_border_width(ctx.zoom_factor)
            handle = HitTester.hit_handle(
                self._last_mouse_cx,
                self._last_mouse_cy,
                selected_boxes,
                ctx,
                self.transformer,
                border_width=lw,
            )
            if handle:
                cursors = {
                    "nw": "resize_nw",
                    "n": "resize_n",
                    "ne": "resize_ne",
                    "w": "resize_w",
                    "e": "resize_e",
                    "sw": "resize_sw",
                    "s": "resize_s",
                    "se": "resize_se",
                }
                self.set_cursor(cursors.get(handle, "default"))
                return

            active_comps = self.get_active_boxes()
            hovered_box = HitTester.hit_box(
                self._last_mouse_cx,
                self._last_mouse_cy,
                active_comps,
                selected_boxes,
                ctx,
                self.transformer,
            )
            if hovered_box is not None:
                # Hovering over components uses the normal pointer (ArrowCursor) per design requirements.
                self.set_cursor("default")
                return

            self.set_cursor("default")

    def set_temp_rect(
        self,
        x1: float,
        y1: float,
        x2: float,
        y2: float,
        color: str | None = None,
        dash: bool = False,
        width: int = 1,
    ):
        if color is None:
            color = "#0000FF"
        self._temp_rect = TempRect(x1, y1, x2, y2, color, dash, width)
        self.update()

    def update_temp_rect(self, x1: float, y1: float, x2: float, y2: float):
        if self._temp_rect:
            self._temp_rect = TempRect(
                x1,
                y1,
                x2,
                y2,
                self._temp_rect.color,
                self._temp_rect.dash,
                self._temp_rect.width,
            )
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

    def make_viewport_ctx(self) -> ViewportContext:
        ws = self.workspace_state
        cut_lines = ws.cutLines if ws else []
        return ViewportContext(
            zoom_factor=self.zoom_factor,
            parent_stack=tuple(self.parent_stack),
            cut_lines=tuple(cut_lines),
            pan_offset=self.pan_offset,
        )

    def schedule_redraw(self):
        """Schedule a repaint (relying on Qt's native coalescing)."""
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
        self._rebuild_base_pixmap()

        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)

        p.fillRect(self.rect(), self.palette().color(QPalette.ColorRole.Window))

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

        ws = self.workspace_state
        parent_comp = None
        if self.parent_stack and ws:
            parent_comp = ws.components.get(self.parent_stack[-1])

        active_comps = self.get_active_boxes()
        ctx = self.make_viewport_ctx()

        # Build state
        selected_boxes = self.get_selected_components()
        union = None
        if (
            len(selected_boxes) == 1
            and self.gestures.resize_handle
            and self.gestures.is_dragging
        ):
            union = self.get_children_bounds_union(selected_boxes[0])

        render_state = CanvasRenderState(
            viewport_ctx=ctx,
            active_comps=active_comps,
            selected_ids=self.selected_component_ids,
            active_interaction=self.active_interaction,
            is_dragging=self.gestures.is_dragging,
            resize_handle=self.gestures.resize_handle,
            show_labels=self.show_labels,
            temp_rect=self._temp_rect,
            parent_comp=parent_comp,
            full_img_width=self.full_pil_img.width if self.full_pil_img else 1,
            children_bounds_union=union,
        )

        if parent_comp:
            self._renderer.paint_parent_mask(p, render_state, self._base_pixmap)
        else:
            p.drawPixmap(target_rect, self._base_pixmap, source_rect)

        self._renderer.paint_annotations(p, render_state, self.font())
        self._renderer.paint_temp_rect(p, render_state.temp_rect)

        p.end()

    # ── Event Handlers ────────────────────────────────────────────────

    def _make_gesture_event(self, event: QMouseEvent) -> GestureEvent:
        """Convert a QMouseEvent to a framework-agnostic GestureEvent."""
        pos = event.position()
        gpos = event.globalPosition()
        mods = event.modifiers()
        return GestureEvent(
            x=pos.x(),
            y=pos.y(),
            screen_x=int(gpos.x()),
            screen_y=int(gpos.y()),
            shift=bool(mods & Qt.KeyboardModifier.ShiftModifier),
            ctrl=bool(mods & Qt.KeyboardModifier.ControlModifier),
        )

    def reset_mouse_state(self):
        """Cancel the hold timer and reset press states."""
        if hasattr(self, "_hold_timer") and self._hold_timer is not None:
            self._hold_timer.stop()
        self._press_pos = None
        self._deadzone_bypassed = False

    def _on_hold_timer_timeout(self):
        """Timer callback when mouse is held down for long enough to bypass deadzone."""
        self._deadzone_bypassed = True

    def mousePressEvent(self, event: QMouseEvent):
        if not self.full_pil_img:
            return

        ge = self._make_gesture_event(event)
        cx, cy = ge.x, ge.y
        button = event.button()

        if button in (Qt.MouseButton.LeftButton, Qt.MouseButton.MiddleButton):
            self.reset_mouse_state()
            self._press_pos = event.position()
            self._hold_timer.start(self.hold_timeout_ms)

        if button == Qt.MouseButton.LeftButton:
            if ge.ctrl and not ge.shift:
                if not self.gestures.on_control_click(self, ge, cx, cy):
                    self.gestures.on_click(self, ge, cx, cy)
            else:
                self.gestures.on_click(self, ge, cx, cy)
        elif button == Qt.MouseButton.MiddleButton:
            self.gestures.on_middle_click(self, ge)
        elif button == Qt.MouseButton.RightButton:
            self.gestures.on_right_click(self, ge, cx, cy)

        self.update_canvas_cursor()

    def mouseMoveEvent(self, event: QMouseEvent):
        if not self.full_pil_img:
            return

        ge = self._make_gesture_event(event)
        cx, cy = ge.x, ge.y

        self._last_mouse_cx = cx
        self._last_mouse_cy = cy

        if self._press_pos is not None:
            is_drag_allowed = not self.deadzone_enabled or self._deadzone_bypassed
            if not is_drag_allowed:
                dx = event.position().x() - self._press_pos.x()
                dy = event.position().y() - self._press_pos.y()
                dist = math.hypot(dx, dy)
                if dist >= self.deadzone_radius:
                    is_drag_allowed = True
                    self._deadzone_bypassed = True
                    self._hold_timer.stop()

                    # Align pan starting coordinates to ensure smooth panning,
                    # while leaving drag_mouse_start_abs unchanged so the clicked target snaps.
                    self.gestures.pan_start_mouse = (cx, cy)

            if is_drag_allowed:
                if event.buttons() & Qt.MouseButton.LeftButton:
                    self.gestures.on_drag(self, ge, cx, cy)
                elif event.buttons() & Qt.MouseButton.MiddleButton:
                    self.gestures.on_middle_drag(self, ge)
        else:
            self.gestures.on_mouse_move(self, ge, cx, cy)

        self.update_canvas_cursor()

    def mouseReleaseEvent(self, event: QMouseEvent):
        if not self.full_pil_img:
            return

        ge = self._make_gesture_event(event)
        cx, cy = ge.x, ge.y
        button = event.button()

        self.reset_mouse_state()

        if button == Qt.MouseButton.LeftButton:
            self.gestures.on_release(self, ge, cx, cy)
        elif button == Qt.MouseButton.MiddleButton:
            self.gestures.on_middle_release(self, ge, cx, cy)

        self.update_canvas_cursor()

    def event(self, event: QEvent) -> bool:
        if event.type() == QEvent.Type.NativeGesture:
            event_any: Any = event
            if event_any.gestureType() == Qt.NativeGestureType.ZoomNativeGesture:
                self._last_native_gesture_time = time.time()
                old_zoom = self.zoom_factor
                scale = 1.0 + event_any.value()
                new_zoom = max(0.1, min(4.0, old_zoom * scale))
                if new_zoom != old_zoom:
                    local_pos = self.mapFromGlobal(QCursor.pos())
                    mouse_x = local_pos.x()
                    mouse_y = local_pos.y()
                    px, py = self.pan_offset
                    new_pan_x = mouse_x - (mouse_x - px) * (new_zoom / old_zoom)
                    new_pan_y = mouse_y - (mouse_y - py) * (new_zoom / old_zoom)
                    if self.callbacks.on_viewport_change_request:
                        self.callbacks.on_viewport_change_request(
                            new_zoom, (new_pan_x, new_pan_y)
                        )
                        if self.gestures.state.space_panning:
                            self.gestures.state.pan_start_offset = (
                                new_pan_x,
                                new_pan_y,
                            )
                            self.gestures.state.pan_start_mouse = (mouse_x, mouse_y)
                event_any.accept()
                return True
        return super().event(event)

    def wheelEvent(self, event: QWheelEvent):
        if not self.full_pil_img:
            return

        mods = event.modifiers()
        ctrl = bool(mods & Qt.KeyboardModifier.ControlModifier)
        shift = bool(mods & Qt.KeyboardModifier.ShiftModifier)
        pos = event.position()
        phase = event.phase()

        # Ignore wheel events during active native pinch gestures to prevent double-handling
        if ctrl and time.time() - getattr(self, "_last_native_gesture_time", 0.0) < 0.1:
            event.accept()
            return

        pixel_delta = event.pixelDelta()
        is_trackpad = (phase != Qt.ScrollPhase.NoScrollPhase) or (
            not pixel_delta.isNull()
        )

        if is_trackpad:
            # Fall back to angleDelta if pixelDelta is null during active trackpad gestures
            if not pixel_delta.isNull():
                dx = pixel_delta.x()
                dy = pixel_delta.y()
            else:
                angle_delta = event.angleDelta()
                # A standard wheel notch is 120, which maps to ~12 logical pixels of scroll
                dx = int(angle_delta.x() * 0.1)
                dy = int(angle_delta.y() * 0.1)

            self.gestures.on_trackpad_scroll(
                self,
                delta_x=dx,
                delta_y=dy,
                mouse_x=pos.x(),
                mouse_y=pos.y(),
                ctrl=ctrl,
                phase=phase,
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
        if self.callbacks.on_viewport_size_changed:
            self.callbacks.on_viewport_size_changed(self.width(), self.height())
        if self._needs_fit and self.width() > 1 and self.height() > 1:
            self.fit_to_screen()
        self.schedule_redraw()

    def keyPressEvent(self, event):
        if event.key() == Qt.Key.Key_Space and not event.isAutoRepeat():
            if not self.is_text_focused():
                self.space_pan_active = True
                self.mode_before_space = self.current_mode
                self.update_canvas_cursor()
                if self.callbacks.on_canvas_mode_change_request:
                    self.callbacks.on_canvas_mode_change_request("pan")
                event.accept()
                return
        super().keyPressEvent(event)

    def keyReleaseEvent(self, event):
        if event.key() == Qt.Key.Key_Space and not event.isAutoRepeat():
            if not self.is_text_focused():
                self.space_pan_active = False
                mode_to_restore = getattr(self, "mode_before_space", "select")
                if hasattr(self, "mode_before_space"):
                    delattr(self, "mode_before_space")
                self.update_canvas_cursor()
                if self.callbacks.on_canvas_mode_change_request:
                    self.callbacks.on_canvas_mode_change_request(mode_to_restore)
                event.accept()
                return
        super().keyReleaseEvent(event)
