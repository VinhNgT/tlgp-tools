"""Event handlers for panning and scrolling."""

from typing import Any

from annotator.gui.gestures.state import GestureState
from annotator.gui.gestures.types import GestureEvent


class PanScrollHandler:
    """Handles workspace panning and scrolling logic."""

    @staticmethod
    def start_pan(state: GestureState, canvas: Any, event: GestureEvent):
        state.space_panning = True
        state.pan_start_mouse = (event.x, event.y)
        state.pan_start_offset = canvas.pan_offset
        canvas.set_cursor("pan_active")

    @staticmethod
    def on_drag(state: GestureState, canvas: Any, event: GestureEvent):
        if not state.space_panning:
            return
        dx = event.x - state.pan_start_mouse[0]
        dy = event.y - state.pan_start_mouse[1]
        new_pan_x = state.pan_start_offset[0] + dx
        new_pan_y = state.pan_start_offset[1] + dy
        if canvas.callbacks.on_viewport_change_request:
            canvas.callbacks.on_viewport_change_request(
                canvas.zoom_factor, (new_pan_x, new_pan_y)
            )

    @staticmethod
    def on_release(state: GestureState, canvas: Any):
        if state.space_panning:
            state.space_panning = False
            canvas.set_cursor("pan_inactive")

    @staticmethod
    def on_scroll(
        canvas: Any,
        delta: int,
        mouse_x: float,
        mouse_y: float,
        shift: bool,
        ctrl: bool,
    ):
        if ctrl:
            # Zoom
            old_zoom = canvas.zoom_factor
            zoom_step = 1.1 if delta > 0 else (1 / 1.1)
            new_zoom = max(0.1, min(4.0, old_zoom * zoom_step))
            if new_zoom != old_zoom:
                px, py = canvas.pan_offset
                new_pan_x = mouse_x - (mouse_x - px) * (new_zoom / old_zoom)
                new_pan_y = mouse_y - (mouse_y - py) * (new_zoom / old_zoom)
                if canvas.callbacks.on_viewport_change_request:
                    canvas.callbacks.on_viewport_change_request(new_zoom, (new_pan_x, new_pan_y))
        else:
            # Pan
            px, py = canvas.pan_offset
            scroll_amount = delta * 0.5
            if shift:
                px += scroll_amount
            else:
                py += scroll_amount
            if canvas.callbacks.on_viewport_change_request:
                canvas.callbacks.on_viewport_change_request(canvas.zoom_factor, (px, py))

    @staticmethod
    def on_trackpad_scroll(
        canvas: Any,
        delta_x: int,
        delta_y: int,
        mouse_x: float,
        mouse_y: float,
        ctrl: bool,
    ):
        if ctrl:
            old_zoom = canvas.zoom_factor
            zoom_step = 1.0 + (delta_y * 0.01)
            if zoom_step <= 0:
                zoom_step = 0.1
            new_zoom = max(0.1, min(4.0, old_zoom * zoom_step))
            if new_zoom != old_zoom:
                px, py = canvas.pan_offset
                new_pan_x = mouse_x - (mouse_x - px) * (new_zoom / old_zoom)
                new_pan_y = mouse_y - (mouse_y - py) * (new_zoom / old_zoom)
                if canvas.callbacks.on_viewport_change_request:
                    canvas.callbacks.on_viewport_change_request(new_zoom, (new_pan_x, new_pan_y))
        else:
            px, py = canvas.pan_offset
            px += delta_x
            py += delta_y
            if canvas.callbacks.on_viewport_change_request:
                canvas.callbacks.on_viewport_change_request(canvas.zoom_factor, (px, py))

