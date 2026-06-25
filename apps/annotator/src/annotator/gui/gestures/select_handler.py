"""Event handler for component selection, movement, and resizing."""

from typing import Any
from uuid import UUID

from annotator.gui.gestures.state import GestureState
from annotator.gui.viewport_context import ViewportContext
from annotator.models import Bounds
from annotator.workspace.validation import BoundsValidator


class SelectHandler:
    """Handles logic for selecting, moving, and resizing components."""

    @staticmethod
    def initiate_drag(
        state: GestureState,
        canvas: Any,
        cx: float,
        cy: float,
        ctx: ViewportContext,
        box: Any,
    ):
        state.is_dragging = True
        state.drag_mouse_start_abs = state.transformer.to_abs_ctx(cx, cy, ctx)

        workspace = canvas.workspace_state
        selected_boxes = canvas.get_selected_components()
        selected_ids = {b.id for b in selected_boxes}
        if box and box.id not in selected_ids:
            selected_boxes = [*selected_boxes, box]
            selected_ids.add(box.id)

        top_level_selected_boxes = []
        for b in selected_boxes:
            has_selected_ancestor = False
            curr = b
            while curr.parentId:
                if curr.parentId in selected_ids:
                    has_selected_ancestor = True
                    break
                parent_comp = workspace.components.get(curr.parentId)
                if not parent_comp:
                    break
                curr = parent_comp
            if not has_selected_ancestor:
                top_level_selected_boxes.append(b)

        # Cache original bounds for each top level selected box
        state.drag_orig_boxes = {}
        for b in top_level_selected_boxes:
            state.drag_orig_boxes[b.id] = (
                b.bounds.left,
                b.bounds.top,
                b.bounds.right,
                b.bounds.bottom,
            )

        if top_level_selected_boxes:
            first_box = top_level_selected_boxes[0]
            state.drag_orig_bounds = (
                first_box.bounds.left,
                first_box.bounds.top,
                first_box.bounds.right,
                first_box.bounds.bottom,
            )
        elif box:
            state.drag_orig_bounds = (
                box.bounds.left,
                box.bounds.top,
                box.bounds.right,
                box.bounds.bottom,
            )
        else:
            state.drag_orig_bounds = (0.0, 0.0, 0.0, 0.0)

        # Cache descendants of all top level selected boxes
        state.drag_orig_descendants = {}

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

        for b in top_level_selected_boxes:
            for child_id in b.childrenIds:
                cache_descendants(child_id)

    @staticmethod
    def on_drag(
        state: GestureState,
        canvas: Any,
        cx: float,
        cy: float,
        ctx: ViewportContext,
        boundary: tuple[float, float, float, float],
        selected_boxes: list,
    ):
        if not state.is_dragging or len(selected_boxes) == 0:
            return

        mx, my = state.transformer.to_abs_ctx(cx, cy, ctx)
        orig_mx, orig_my = state.drag_mouse_start_abs

        dx = mx - orig_mx
        dy = my - orig_my

        bx1, by1, bx2, by2 = boundary

        if state.resize_handle:
            if len(selected_boxes) != 1:
                return
            box = selected_boxes[0]
            if state.transformer.has_active_cuts_ctx(ctx):
                seg_top, seg_bot = state.transformer.get_segment_y_bounds_ctx(
                    state.drag_orig_bounds[1], ctx, boundary
                )
                by1 = max(by1, seg_top)
                by2 = min(by2, seg_bot)

            ox1, oy1, ox2, oy2 = state.drag_orig_bounds
            union = canvas.get_children_bounds_union(box)
            rx1, ry1, rx2, ry2 = BoundsValidator.clamp_resize(
                ox1,
                oy1,
                ox2,
                oy2,
                dx,
                dy,
                state.resize_handle,
                bx1,
                by1,
                bx2,
                by2,
                min_size=4,
                children_union=union,
            )
            bounds = Bounds(x=rx1, y=ry1, w=rx2 - rx1, h=ry2 - ry1)
            active_int = (
                dict(canvas.active_interaction) if canvas.active_interaction else {}
            )
            active_int[box.id] = bounds
            if canvas.callbacks.on_active_interaction_changed:
                canvas.callbacks.on_active_interaction_changed(active_int)
        else:
            # Translation / Dragging (possibly multiple boxes)
            drag_orig_boxes = getattr(state, "drag_orig_boxes", None)
            if not drag_orig_boxes:
                drag_orig_boxes = {selected_boxes[0].id: state.drag_orig_bounds}

            min_dx = float("-inf")
            max_dx = float("inf")
            min_dy = float("-inf")
            max_dy = float("inf")

            for _, orig_b in drag_orig_boxes.items():
                ox1, oy1, ox2, oy2 = orig_b
                w, h = ox2 - ox1, oy2 - oy1

                by1_i, by2_i = by1, by2
                if state.transformer.has_active_cuts_ctx(ctx):
                    seg_top, seg_bot = state.transformer.get_segment_y_bounds_ctx(
                        oy1, ctx, boundary
                    )
                    by1_i = max(by1_i, seg_top)
                    by2_i = min(by2_i, seg_bot)

                min_dx = max(min_dx, bx1 - ox1)
                max_dx = min(max_dx, bx2 - ox2)
                min_dy = max(min_dy, by1_i - oy1)
                max_dy = min(max_dy, by2_i - oy2)

            ddx = max(min_dx, min(max_dx, dx))
            ddy = max(min_dy, min(max_dy, dy))

            active_int = (
                dict(canvas.active_interaction) if canvas.active_interaction else {}
            )

            for c_id, orig_b in drag_orig_boxes.items():
                ox1, oy1, ox2, oy2 = orig_b
                w, h = ox2 - ox1, oy2 - oy1
                active_int[c_id] = Bounds(x=ox1 + ddx, y=oy1 + ddy, w=w, h=h)

            workspace = canvas.workspace_state

            def shift_descendants_transient(c_id: UUID):
                comp = workspace.components.get(c_id)
                if comp and c_id in state.drag_orig_descendants:
                    d_ox1, d_oy1, d_ox2, d_oy2 = state.drag_orig_descendants[c_id]
                    d_w = d_ox2 - d_ox1
                    d_h = d_oy2 - d_oy1
                    active_int[c_id] = Bounds(
                        x=d_ox1 + ddx, y=d_oy1 + ddy, w=d_w, h=d_h
                    )
                    for child_id in comp.childrenIds:
                        shift_descendants_transient(child_id)

            for c_id in drag_orig_boxes:
                comp = workspace.components.get(c_id)
                if comp:
                    for child_id in comp.childrenIds:
                        shift_descendants_transient(child_id)

            if canvas.callbacks.on_active_interaction_changed:
                canvas.callbacks.on_active_interaction_changed(active_int)

        canvas.schedule_redraw()

    @staticmethod
    def on_release(state: GestureState, canvas: Any, selected_boxes: list) -> bool:
        if not state.is_dragging or len(selected_boxes) == 0:
            state.is_dragging = False
            state.resize_handle = None
            return False

        is_resize = state.resize_handle is not None
        active_int = canvas.active_interaction
        event_generated = False

        if is_resize:
            if len(selected_boxes) != 1:
                state.is_dragging = False
                state.resize_handle = None
                return False
            box = selected_boxes[0]
            transient_bounds = active_int.get(box.id) if active_int else None
            ox1, oy1, ox2, oy2 = state.drag_orig_bounds
            if transient_bounds and (
                transient_bounds.left != ox1
                or transient_bounds.top != oy1
                or transient_bounds.right != ox2
                or transient_bounds.bottom != oy2
            ):
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
            drag_orig_boxes = getattr(state, "drag_orig_boxes", None)
            if not drag_orig_boxes:
                drag_orig_boxes = {selected_boxes[0].id: state.drag_orig_bounds}

            moves = {}
            for c_id, orig_b in drag_orig_boxes.items():
                transient_bounds = active_int.get(c_id) if active_int else None
                ox1, oy1, ox2, oy2 = orig_b
                if transient_bounds and (
                    transient_bounds.left != ox1
                    or transient_bounds.top != oy1
                    or transient_bounds.right != ox2
                    or transient_bounds.bottom != oy2
                ):
                    moves[str(c_id)] = (
                        int(transient_bounds.x),
                        int(transient_bounds.y),
                    )

            if moves:
                if getattr(canvas.callbacks, "on_components_moved", None):
                    canvas.callbacks.on_components_moved(moves)
                    event_generated = True
                elif canvas.callbacks.on_component_moved:
                    for c_id_str, (nx, ny) in moves.items():
                        canvas.callbacks.on_component_moved(c_id_str, nx, ny)
                    event_generated = True

        state.is_dragging = False
        state.resize_handle = None

        if not event_generated:
            # Revert interaction state if no event fired
            active_int = canvas.active_interaction
            if active_int:
                active_dict = dict(active_int)
                drag_orig_boxes = getattr(state, "drag_orig_boxes", None)
                if not drag_orig_boxes:
                    drag_orig_boxes = {selected_boxes[0].id: state.drag_orig_bounds}

                workspace = canvas.workspace_state

                def remove_descendants(c_id: UUID):
                    comp = workspace.components.get(c_id)
                    if comp:
                        active_dict.pop(c_id, None)
                        for child_id in comp.childrenIds:
                            remove_descendants(child_id)

                for c_id in drag_orig_boxes:
                    active_dict.pop(c_id, None)
                    comp = workspace.components.get(c_id)
                    if comp:
                        for child_id in comp.childrenIds:
                            remove_descendants(child_id)

                if canvas.callbacks.on_active_interaction_changed:
                    canvas.callbacks.on_active_interaction_changed(active_dict)
                canvas.schedule_redraw()

        return event_generated
