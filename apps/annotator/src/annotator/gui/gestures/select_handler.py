"""Event handler for component selection, movement, and resizing."""

from typing import Any
from uuid import UUID

from annotator.gui.gestures.state import GestureState
from annotator.gui.validation import BoundsValidator
from annotator.gui.viewport_context import ViewportContext
from annotator.models import Bounds


class SelectHandler:
    """Handles logic for selecting, moving, and resizing components."""

    @staticmethod
    def initiate_drag(
        state: GestureState,
        canvas: Any,
        cx: float,
        cy: float,
        ctx: ViewportContext,
        box: Any
    ):
        state.is_dragging = True
        state.drag_mouse_start_abs = state.transformer.to_abs_ctx(cx, cy, ctx)
        state.drag_orig_bounds = (
            box.bounds.left,
            box.bounds.top,
            box.bounds.right,
            box.bounds.bottom,
        )
        state.drag_orig_descendants = {}

        workspace = canvas.workspace_state
        def cache_descendants(c_id: UUID):
            comp = workspace.components.get(c_id)
            if comp:
                state.drag_orig_descendants[c_id] = (
                    comp.bounds.left,
                    comp.bounds.top,
                    comp.bounds.right,
                    comp.bounds.bottom,
                )
                for child_id in comp.childrenIds:
                    cache_descendants(child_id)

        for child_id in box.childrenIds:
            cache_descendants(child_id)

    @staticmethod
    def on_drag(
        state: GestureState,
        canvas: Any,
        cx: float,
        cy: float,
        ctx: ViewportContext,
        boundary: tuple[float, float, float, float],
        selected_boxes: list
    ):
        if not state.is_dragging or len(selected_boxes) != 1:
            return

        box = selected_boxes[0]
        mx, my = state.transformer.to_abs_ctx(cx, cy, ctx)
        orig_mx, orig_my = state.drag_mouse_start_abs

        dx = mx - orig_mx
        dy = my - orig_my

        bx1, by1, bx2, by2 = boundary

        if state.transformer.has_active_cuts_ctx(ctx):
            seg_top, seg_bot = state.transformer.get_segment_y_bounds_ctx(state.drag_orig_bounds[1], ctx, boundary)
            by1 = max(by1, seg_top)
            by2 = min(by2, seg_bot)

        if state.resize_handle:
            ox1, oy1, ox2, oy2 = state.drag_orig_bounds
            union = canvas.get_children_bounds_union(box)
            rx1, ry1, rx2, ry2 = BoundsValidator.clamp_resize(
                ox1, oy1, ox2, oy2, dx, dy, state.resize_handle, bx1, by1, bx2, by2, min_size=4, children_union=union
            )
            bounds = Bounds(x=rx1, y=ry1, w=rx2 - rx1, h=ry2 - ry1)
            active_int = dict(canvas.active_interaction) if canvas.active_interaction else {}
            active_int[box.id] = bounds
            if canvas.callbacks.on_active_interaction_changed:
                canvas.callbacks.on_active_interaction_changed(active_int)
        else:
            ox1, oy1, ox2, oy2 = state.drag_orig_bounds
            w, h = ox2 - ox1, oy2 - oy1
            rx1, ry1 = BoundsValidator.clamp_box_position(
                ox1, oy1, w, h, dx, dy, bx1, by1, bx2, by2
            )
            ddx = rx1 - ox1
            ddy = ry1 - oy1

            active_int = dict(canvas.active_interaction) if canvas.active_interaction else {}
            active_int[box.id] = Bounds(x=rx1, y=ry1, w=w, h=h)

            workspace = canvas.workspace_state
            def shift_descendants_transient(c_id: UUID):
                comp = workspace.components.get(c_id)
                if comp and c_id in state.drag_orig_descendants:
                    d_ox1, d_oy1, d_ox2, d_oy2 = state.drag_orig_descendants[c_id]
                    d_w = d_ox2 - d_ox1
                    d_h = d_oy2 - d_oy1
                    active_int[c_id] = Bounds(x=d_ox1 + ddx, y=d_oy1 + ddy, w=d_w, h=d_h)
                    for child_id in comp.childrenIds:
                        shift_descendants_transient(child_id)

            for child_id in box.childrenIds:
                shift_descendants_transient(child_id)

            if canvas.callbacks.on_active_interaction_changed:
                canvas.callbacks.on_active_interaction_changed(active_int)

        canvas.schedule_redraw()

    @staticmethod
    def on_release(state: GestureState, canvas: Any, selected_boxes: list) -> bool:
        if not state.is_dragging or len(selected_boxes) != 1:
            state.is_dragging = False
            state.resize_handle = None
            return False

        box = selected_boxes[0]
        is_resize = state.resize_handle is not None
        active_int = canvas.active_interaction
        transient_bounds = active_int.get(box.id) if active_int else None

        ox1, oy1, ox2, oy2 = state.drag_orig_bounds
        event_generated = False

        if transient_bounds and (
            transient_bounds.left != ox1
            or transient_bounds.top != oy1
            or transient_bounds.right != ox2
            or transient_bounds.bottom != oy2
        ):
            if is_resize:
                if canvas.callbacks.on_component_resized:
                    canvas.callbacks.on_component_resized(
                        str(box.id),
                        {
                            "x": int(transient_bounds.x),
                            "y": int(transient_bounds.y),
                            "w": int(transient_bounds.w),
                            "h": int(transient_bounds.h),
                        },
                    )
                event_generated = True
            else:
                if canvas.callbacks.on_component_moved:
                    canvas.callbacks.on_component_moved(
                        str(box.id),
                        int(transient_bounds.x),
                        int(transient_bounds.y),
                    )
                event_generated = True

        state.is_dragging = False
        state.resize_handle = None

        if not event_generated:
            # Revert interaction state if no event fired
            active_int = canvas.active_interaction
            if active_int:
                active_dict = dict(active_int)
                active_dict.pop(box.id, None)
                workspace = canvas.workspace_state
                def remove_descendants(c_id: UUID):
                    comp = workspace.components.get(c_id)
                    if comp:
                        active_dict.pop(c_id, None)
                        for child_id in comp.childrenIds:
                            remove_descendants(child_id)

                for child_id in box.childrenIds:
                    remove_descendants(child_id)

                if canvas.callbacks.on_active_interaction_changed:
                    canvas.callbacks.on_active_interaction_changed(active_dict)
                canvas.schedule_redraw()

        return event_generated

