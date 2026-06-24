"""Main gesture interpreter coordinating the handlers."""

import time
from typing import Any

from PySide6.QtCore import Qt

from annotator.gui.gestures.draw_handler import DrawHandler
from annotator.gui.gestures.hit_testing import HitTester
from annotator.gui.gestures.pan_handler import PanScrollHandler
from annotator.gui.gestures.select_handler import SelectHandler
from annotator.gui.gestures.state import GestureState
from annotator.gui.gestures.types import GestureEvent
from annotator.gui.transformer import ViewportTransformer


class GestureInterpreter:
    """Top-level dispatcher for gestures."""

    def __init__(self, transformer: ViewportTransformer):
        self.state = GestureState(transformer)
        self.transformer = transformer

    @property
    def has_temp_rect(self) -> bool:
        return self.state.has_temp_rect

    @property
    def is_dragging(self) -> bool:
        return self.state.is_dragging

    @property
    def resize_handle(self) -> str | None:
        return self.state.resize_handle

    @property
    def drag_mouse_start_abs(self) -> tuple[float, float]:
        return self.state.drag_mouse_start_abs

    @drag_mouse_start_abs.setter
    def drag_mouse_start_abs(self, val: tuple[float, float]):
        self.state.drag_mouse_start_abs = val

    @property
    def pan_start_mouse(self) -> tuple[float, float]:
        return self.state.pan_start_mouse

    @pan_start_mouse.setter
    def pan_start_mouse(self, val: tuple[float, float]):
        self.state.pan_start_mouse = val

    @property
    def last_click_time(self) -> float:
        return self.state.last_click_time

    @last_click_time.setter
    def last_click_time(self, val: float):
        self.state.last_click_time = val

    @property
    def last_click_cx(self) -> float:
        return self.state.last_click_cx

    @last_click_cx.setter
    def last_click_cx(self, val: float):
        self.state.last_click_cx = val

    @property
    def last_click_cy(self) -> float:
        return self.state.last_click_cy

    @last_click_cy.setter
    def last_click_cy(self, val: float):
        self.state.last_click_cy = val

    def on_click(self, canvas: Any, event: GestureEvent, cx: float, cy: float):
        if not canvas.full_pil_img:
            return

        if canvas.space_pan_active or canvas.current_mode == "pan":
            PanScrollHandler.start_pan(self.state, canvas, event)
            return

        ctx = canvas.make_viewport_ctx()
        selected_boxes = canvas.get_selected_components()
        active_comps = canvas.get_active_boxes()

        now = time.time()
        is_multi = event.shift or event.ctrl
        hit_boxes_at_click = HitTester.get_hit_boxes(
            cx, cy, active_comps, ctx, self.transformer
        )
        primary_sel = selected_boxes[-1] if selected_boxes else None

        clicked = HitTester.hit_box(
            cx, cy, active_comps, selected_boxes, ctx, self.transformer
        )
        is_selection_click = clicked is not None and clicked not in selected_boxes

        if (
            now - self.state.last_click_time < 0.5
            and abs(cx - self.state.last_click_cx) < 15
            and abs(cy - self.state.last_click_cy) < 15
            and primary_sel
            and primary_sel in hit_boxes_at_click
        ):
            self.state.click_sequence_count += 1
        else:
            self.state.click_sequence_count = 1
            self.state.cycle_components = None

        self.state.last_click_time = 0.0 if is_selection_click else now
        self.state.last_click_cx = cx
        self.state.last_click_cy = cy

        if (
            self.state.click_sequence_count % 2 == 0
            and canvas.current_mode == "select"
            and not is_multi
        ):
            handle = HitTester.hit_handle(cx, cy, selected_boxes, ctx, self.transformer)
            if not handle:
                if self.state.cycle_components is None:
                    hit_boxes = list(hit_boxes_at_click)
                    hit_boxes.reverse()
                    if len(hit_boxes) > 1:
                        self.state.cycle_components = hit_boxes
                        if primary_sel is not None and primary_sel in hit_boxes:
                            self.state.last_cycle_index = hit_boxes.index(primary_sel)
                        else:
                            self.state.last_cycle_index = 0

                if self.state.cycle_components is not None:
                    self.state.last_cycle_index = (
                        self.state.last_cycle_index + 1
                    ) % len(self.state.cycle_components)
                    new_box = self.state.cycle_components[self.state.last_cycle_index]
                    canvas.set_selection([new_box])
                    SelectHandler.initiate_drag(
                        self.state, canvas, cx, cy, ctx, new_box
                    )
                    return

        handle = HitTester.hit_handle(cx, cy, selected_boxes, ctx, self.transformer)
        if handle:
            self.state.resize_handle = handle
            SelectHandler.initiate_drag(
                self.state, canvas, cx, cy, ctx, selected_boxes[0]
            )
            return

        if canvas.current_mode == "select":
            if clicked:
                if is_multi:
                    new_sel = list(selected_boxes)
                    if clicked in new_sel:
                        new_sel.remove(clicked)
                    else:
                        new_sel.append(clicked)
                    canvas.set_selection(new_sel)
                else:
                    canvas.set_selection([clicked])

                SelectHandler.initiate_drag(self.state, canvas, cx, cy, ctx, clicked)
            else:
                if not is_multi:
                    if canvas.is_text_focused():
                        canvas.clear_text_focus()
                    else:
                        canvas.set_selection([])
                DrawHandler.start_draw(self.state, canvas, cx, cy, True)

        elif canvas.current_mode == "draw":
            DrawHandler.start_draw(self.state, canvas, cx, cy, False)

    def on_drag(self, canvas: Any, event: GestureEvent, cx: float, cy: float):
        if not canvas.full_pil_img:
            return

        if self.state.space_panning:
            PanScrollHandler.on_drag(self.state, canvas, event)
            return

        ctx = canvas.make_viewport_ctx()
        boundary = (
            canvas.resolve_boundary()
            if hasattr(canvas, "resolve_boundary")
            else (0.0, 0.0, float("inf"), float("inf"))
        )

        if self.state.has_temp_rect:
            DrawHandler.on_drag(self.state, canvas, cx, cy, ctx, boundary)
            return

        selected_boxes = canvas.get_selected_components()
        SelectHandler.on_drag(self.state, canvas, cx, cy, ctx, boundary, selected_boxes)

    def on_release(self, canvas: Any, event: GestureEvent, cx: float, cy: float):
        if not canvas.full_pil_img:
            return

        if self.state.space_panning:
            PanScrollHandler.on_release(self.state, canvas)
            return

        ctx = canvas.make_viewport_ctx()
        boundary = (
            canvas.resolve_boundary()
            if hasattr(canvas, "resolve_boundary")
            else (0.0, 0.0, float("inf"), float("inf"))
        )
        selected_boxes = canvas.get_selected_components()
        is_select_mode = canvas.current_mode == "select"
        is_multi = event.shift or event.ctrl

        event_generated = False

        if self.state.has_temp_rect:
            event_generated = DrawHandler.on_release(
                self.state,
                canvas,
                cx,
                cy,
                ctx,
                boundary,
                is_select_mode,
                is_multi,
                selected_boxes,
            )
        elif self.state.is_dragging:
            event_generated = SelectHandler.on_release(
                self.state, canvas, selected_boxes
            )

        if not event_generated and self.state.has_temp_rect:
            pass  # Already cleared by DrawHandler.on_release

        self.state.is_dragging = False
        self.state.resize_handle = None

    def on_middle_click(self, canvas: Any, event: GestureEvent):
        PanScrollHandler.start_pan(self.state, canvas, event)

    def on_middle_drag(self, canvas: Any, event: GestureEvent):
        PanScrollHandler.on_drag(self.state, canvas, event)

    def on_middle_release(self, canvas: Any, event: GestureEvent, cx: float, cy: float):
        PanScrollHandler.on_release(self.state, canvas)

    def on_right_click(self, canvas: Any, event: GestureEvent, cx: float, cy: float):
        ctx = canvas.make_viewport_ctx()
        active_comps = canvas.get_active_boxes()
        selected_boxes = canvas.get_selected_components()
        clicked = HitTester.hit_box(
            cx, cy, active_comps, selected_boxes, ctx, self.transformer
        )
        if clicked and clicked not in selected_boxes:
            canvas.set_selection([clicked])
        if canvas.callbacks.on_context_menu_request:
            canvas.callbacks.on_context_menu_request(event.screen_x, event.screen_y)

    def on_control_click(
        self, canvas: Any, event: GestureEvent, cx: float, cy: float
    ) -> bool:
        if canvas.current_mode == "select":
            ctx = canvas.make_viewport_ctx()
            active_comps = canvas.get_active_boxes()
            selected_boxes = canvas.get_selected_components()
            clicked = HitTester.hit_box(
                cx, cy, active_comps, selected_boxes, ctx, self.transformer
            )
            if clicked:
                if canvas.callbacks.on_drill_into:
                    canvas.callbacks.on_drill_into(clicked.id)
                return True
        return False

    def on_mouse_move(self, canvas: Any, event: GestureEvent, cx: float, cy: float):
        pass

    def on_scroll(
        self,
        canvas: Any,
        delta: int,
        mouse_x: float,
        mouse_y: float,
        shift: bool,
        ctrl: bool,
    ):
        self.state.ignore_momentum = False
        PanScrollHandler.on_scroll(canvas, delta, mouse_x, mouse_y, shift, ctrl)

    def on_trackpad_scroll(
        self,
        canvas: Any,
        delta_x: int,
        delta_y: int,
        mouse_x: float,
        mouse_y: float,
        ctrl: bool,
        phase: Qt.ScrollPhase = Qt.ScrollPhase.NoScrollPhase,
    ):
        PanScrollHandler.on_trackpad_scroll(
            self.state, canvas, delta_x, delta_y, mouse_x, mouse_y, ctrl, phase
        )
