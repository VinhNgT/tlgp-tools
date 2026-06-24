"""Event handler for drawing interactions (marquee, bounding box creation)."""

from typing import Any

from annotator.gui.gestures.state import GestureState
from annotator.gui.viewport_context import ViewportContext
from annotator.workspace.validation import BoundsValidator


class DrawHandler:
    """Handles temporary rectangle drawing and new component creation."""

    @staticmethod
    def start_draw(
        state: GestureState, canvas: Any, cx: float, cy: float, is_select_mode: bool
    ):
        state.draw_start_x = cx
        state.draw_start_y = cy
        color = "#0c8ce9" if is_select_mode else "#ff4444"
        width = 1 if is_select_mode else 2
        dash = is_select_mode
        canvas.set_temp_rect(cx, cy, cx, cy, color=color, dash=dash, width=width)
        state.has_temp_rect = True

    @staticmethod
    def on_drag(
        state: GestureState,
        canvas: Any,
        cx: float,
        cy: float,
        ctx: ViewportContext,
        boundary: tuple[float, float, float, float],
    ):
        if not state.has_temp_rect:
            return

        ax1, ay1 = state.transformer.to_abs_ctx(
            state.draw_start_x, state.draw_start_y, ctx
        )
        ax2, ay2 = state.transformer.to_abs_ctx(cx, cy, ctx)

        bx1, by1, bx2, by2 = boundary

        if state.transformer.has_active_cuts_ctx(ctx):
            seg_top, seg_bot = state.transformer.get_segment_y_bounds_ctx(
                ay1, ctx, boundary
            )
            by1 = max(by1, seg_top)
            by2 = min(by2, seg_bot)

        c_ax1 = BoundsValidator.clamp_val(ax1, bx1, bx2)
        c_ay1 = BoundsValidator.clamp_val(ay1, by1, by2)
        c_ax2 = BoundsValidator.clamp_val(ax2, bx1, bx2)
        c_ay2 = BoundsValidator.clamp_val(ay2, by1, by2)

        gcx1, gcy1 = state.transformer.to_canvas_ctx(c_ax1, c_ay1, ctx)
        gcx2, gcy2 = state.transformer.to_canvas_ctx(c_ax2, c_ay2, ctx)

        canvas.update_temp_rect(gcx1, gcy1, gcx2, gcy2)

    @staticmethod
    def on_release(
        state: GestureState,
        canvas: Any,
        cx: float,
        cy: float,
        ctx: ViewportContext,
        boundary: tuple[float, float, float, float],
        is_select_mode: bool,
        is_multi: bool,
        selected_boxes: list,
    ):
        if not state.has_temp_rect:
            return

        canvas.clear_temp_rect()
        state.has_temp_rect = False

        bx1, by1, bx2, by2 = boundary
        ax1, ay1 = state.transformer.to_abs_ctx(
            state.draw_start_x, state.draw_start_y, ctx
        )
        ax2, ay2 = state.transformer.to_abs_ctx(cx, cy, ctx)

        if state.transformer.has_active_cuts_ctx(ctx):
            seg_top, seg_bot = state.transformer.get_segment_y_bounds_ctx(
                ay1, ctx, boundary
            )
            by1 = max(by1, seg_top)
            by2 = min(by2, seg_bot)

        left = max(bx1, min(bx2, min(ax1, ax2)))
        top = max(by1, min(by2, min(ay1, ay2)))
        right = max(bx1, min(bx2, max(ax1, ax2)))
        bot = max(by1, min(by2, max(ay1, ay2)))

        if (right - left) > 3 or (bot - top) > 3:
            if is_select_mode:
                intersected = []
                for box in canvas.get_active_boxes():
                    if (
                        box.bounds.left < right
                        and box.bounds.right > left
                        and box.bounds.top < bot
                        and box.bounds.bottom > top
                    ):
                        intersected.append(box)

                if is_multi:
                    new_sel = list(selected_boxes)
                    for box in intersected:
                        if box not in new_sel:
                            new_sel.append(box)
                    canvas.set_selection(new_sel)
                else:
                    canvas.set_selection(intersected)
            else:
                if canvas.callbacks.on_component_created:
                    canvas.callbacks.on_component_created(
                        {
                            "x": left,
                            "y": top,
                            "w": right - left,
                            "h": bot - top,
                        }
                    )
                return True
        return False
