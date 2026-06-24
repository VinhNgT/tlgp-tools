import time
from dataclasses import dataclass
from typing import Any
from uuid import UUID

from annotator.models import Bounds, Component

from .design_system import ColorSystem
from .transformer import ViewportTransformer
from .validation import BoundsValidator


@dataclass
class GestureEvent:
    """Framework-agnostic wrapper for pointer events used by the gesture interpreter.

    The hosting canvas widget translates native events (Qt, etc.)
    into this portable representation before passing to GestureInterpreter.
    """

    x: float  # Widget-space x coordinate
    y: float  # Widget-space y coordinate
    x_root: int = 0  # Screen-space x coordinate (for context menus)
    y_root: int = 0  # Screen-space y coordinate (for context menus)
    shift: bool = False  # Shift modifier held
    ctrl: bool = False  # Control/Command modifier held


class GestureInterpreter:
    """Manages active canvas gestures (moving, resizing, viewport panning) and pointer hit tests."""

    def __init__(self, transformer: ViewportTransformer):
        self.transformer = transformer

        # Interaction tracking
        self.is_dragging = False
        self.drag_mouse_start_abs = (0, 0)
        self.resize_handle: str | None = None
        self.drag_orig_bounds = (0, 0, 0, 0)  # (left, top, right, bottom) raw absolute
        self.drag_orig_descendants: dict[UUID, tuple[int, int, int, int]] = {}

        # Viewport space panning tracking
        self.space_panning = False
        self.pan_start_mouse: tuple[float, float] = (0.0, 0.0)
        self.pan_start_offset = (0.0, 0.0)

        # Drawing coordinates
        self.draw_start_x = 0.0
        self.draw_start_y = 0.0
        self.has_temp_rect = False

        # Double-click interaction tracking
        self.last_click_time = 0.0
        self.last_click_cx = 0.0
        self.last_click_cy = 0.0
        self.click_sequence_count = 0
        self.cycle_components = None
        self.last_cycle_index = -1

    def _resolve_boundary(self, canvas: Any) -> tuple[int, int, int, int]:
        workspace = canvas.workspace_state
        parent_stack = canvas.parent_stack
        parent_bounds = None
        if workspace and parent_stack:
            parent = workspace.components.get(parent_stack[-1])
            if parent:
                b = parent.bounds
                parent_bounds = (b.left, b.top, b.right, b.bottom)
        image_size = (
            (workspace.image.width, workspace.image.height)
            if workspace and workspace.image
            else None
        )
        return self.transformer.get_boundary(parent_bounds, image_size)

    def hit_handle(
        self,
        canvas: Any,
        cx: float,
        cy: float,
        selected_boxes: list[Component],
        zoom_factor: float,
        parent_stack: list[UUID],
        cut_lines: list[int],
        pan_offset: tuple[float, float],
    ) -> str | None:
        """Determines if pointer lies within interactive drag handles of selected component."""
        if len(selected_boxes) != 1:
            return None
        box = selected_boxes[0]
        if canvas.is_effectively_locked(box):
            return None

        cx1, cy1 = self.transformer.to_canvas(
            box.bounds.left,
            box.bounds.top,
            zoom_factor,
            parent_stack,
            cut_lines,
            pan_offset=pan_offset,
        )
        cx2, cy2 = self.transformer.to_canvas(
            box.bounds.right,
            box.bounds.bottom,
            zoom_factor,
            parent_stack,
            cut_lines,
            pan_offset=pan_offset,
        )
        mx, my = (cx1 + cx2) / 2, (cy1 + cy2) / 2
        hs = 5

        handles = {
            "nw": (cx1, cy1),
            "n": (mx, cy1),
            "ne": (cx2, cy1),
            "w": (cx1, my),
            "e": (cx2, my),
            "sw": (cx1, cy2),
            "s": (mx, cy2),
            "se": (cx2, cy2),
        }

        for name, (hx, hy) in handles.items():
            if hx - hs <= cx <= hx + hs and hy - hs <= cy <= hy + hs:
                return name
        return None

    def get_hit_boxes(
        self,
        canvas: Any,
        cx: float,
        cy: float,
        components: list[Component],
        zoom_factor: float,
        parent_stack: list[UUID],
        cut_lines: list[int],
        pan_offset: tuple[float, float],
    ) -> list[Component]:
        """Calculates a list of all visible components intersected by absolute coordinates."""
        hit = []
        for box in components:
            bx1, by1 = self.transformer.to_canvas(
                box.bounds.left,
                box.bounds.top,
                zoom_factor,
                parent_stack,
                cut_lines,
                pan_offset=pan_offset,
            )
            bx2, by2 = self.transformer.to_canvas(
                box.bounds.right,
                box.bounds.bottom,
                zoom_factor,
                parent_stack,
                cut_lines,
                pan_offset=pan_offset,
            )
            if bx1 <= cx <= bx2 and by1 <= cy <= by2:
                hit.append(box)
        return hit

    def hit_box(
        self,
        canvas: Any,
        cx: float,
        cy: float,
        components: list[Component],
        selected_boxes: list[Component],
        zoom_factor: float,
        parent_stack: list[UUID],
        cut_lines: list[int],
        pan_offset: tuple[float, float],
    ) -> Component | None:
        """Identifies intersected component, sorting with selected box priorities for cycling."""
        boxes = self.get_hit_boxes(
            canvas, cx, cy, components, zoom_factor, parent_stack, cut_lines, pan_offset
        )
        if not boxes:
            return None
        selected = [b for b in boxes if b in selected_boxes]
        non_selected = [b for b in boxes if b not in selected_boxes]
        ordered = non_selected + selected
        return ordered[-1] if ordered else None

    def on_click(self, canvas: Any, event: GestureEvent, cx: float, cy: float):
        """Processes canvas click triggers, initiating moves, resizes, or workspace panning."""
        if not canvas.full_pil_img:
            return

        state = canvas
        if canvas.space_pan_active or state.current_mode == "pan":
            self.space_panning = True
            self.pan_start_mouse = (event.x, event.y)
            self.pan_start_offset = state.pan_offset
            canvas.set_cursor("pan_active")
            return

        workspace = state.workspace_state
        parent_stack = state.parent_stack
        cut_lines = workspace.cutLines if workspace else []
        selected_boxes = [
            workspace.components[uid]
            for uid in state.selected_component_ids
            if workspace and uid in workspace.components
        ]

        now = time.time()
        is_multi = event.shift or event.ctrl
        active_comps = canvas.get_active_boxes()
        hit_boxes_at_click = self.get_hit_boxes(
            canvas,
            cx,
            cy,
            active_comps,
            state.zoom_factor,
            parent_stack,
            cut_lines,
            state.pan_offset,
        )
        primary_sel = selected_boxes[-1] if selected_boxes else None

        clicked = self.hit_box(
            canvas,
            cx,
            cy,
            active_comps,
            selected_boxes,
            state.zoom_factor,
            parent_stack,
            cut_lines,
            state.pan_offset,
        )
        is_selection_click = clicked is not None and clicked not in selected_boxes

        if (
            now - self.last_click_time < 0.5
            and abs(cx - self.last_click_cx) < 15
            and abs(cy - self.last_click_cy) < 15
            and primary_sel
            and primary_sel in hit_boxes_at_click
        ):
            self.click_sequence_count += 1
        else:
            self.click_sequence_count = 1
            self.cycle_components = None

        self.last_click_time = 0.0 if is_selection_click else now
        self.last_click_cx = cx
        self.last_click_cy = cy

        if (
            self.click_sequence_count % 2 == 0
            and state.current_mode == "select"
            and not is_multi
        ):
            handle = self.hit_handle(
                canvas,
                cx,
                cy,
                selected_boxes,
                state.zoom_factor,
                parent_stack,
                cut_lines,
                state.pan_offset,
            )
            if not handle:
                if self.cycle_components is None:
                    hit_boxes = list(hit_boxes_at_click)
                    hit_boxes.reverse()
                    if len(hit_boxes) > 1:
                        self.cycle_components = hit_boxes
                        if primary_sel is not None and primary_sel in hit_boxes:
                            self.last_cycle_index = hit_boxes.index(primary_sel)
                        else:
                            self.last_cycle_index = 0

                if self.cycle_components is not None:
                    self.last_cycle_index = (self.last_cycle_index + 1) % len(
                        self.cycle_components
                    )
                    new_box = self.cycle_components[self.last_cycle_index]
                    canvas.set_selection([new_box])

                    if not canvas.is_effectively_locked(new_box):
                        self.is_dragging = True
                        self.drag_mouse_start_abs = self.transformer.to_abs(
                            cx,
                            cy,
                            state.zoom_factor,
                            parent_stack,
                            cut_lines,
                            pan_offset=state.pan_offset,
                        )
                        self.drag_orig_bounds = (
                            new_box.bounds.left,
                            new_box.bounds.top,
                            new_box.bounds.right,
                            new_box.bounds.bottom,
                        )
                        self.drag_orig_descendants = {}

                        def cache_descendants(c_id: UUID):
                            comp = workspace.components.get(c_id)
                            if comp:
                                self.drag_orig_descendants[c_id] = (
                                    comp.bounds.left,
                                    comp.bounds.top,
                                    comp.bounds.right,
                                    comp.bounds.bottom,
                                )
                                for child_id in comp.childrenIds:
                                    cache_descendants(child_id)

                        for child_id in new_box.childrenIds:
                            cache_descendants(child_id)
                    return

        handle = self.hit_handle(
            canvas,
            cx,
            cy,
            selected_boxes,
            state.zoom_factor,
            parent_stack,
            cut_lines,
            state.pan_offset,
        )
        if handle:
            self.resize_handle = handle
            self.is_dragging = True
            self.drag_mouse_start_abs = self.transformer.to_abs(
                cx,
                cy,
                state.zoom_factor,
                parent_stack,
                cut_lines,
                pan_offset=state.pan_offset,
            )
            active_box = selected_boxes[0]
            self.drag_orig_bounds = (
                active_box.bounds.left,
                active_box.bounds.top,
                active_box.bounds.right,
                active_box.bounds.bottom,
            )
            return

        if state.current_mode == "select":
            if clicked:
                is_multi = event.shift or event.ctrl
                if is_multi:
                    new_sel = list(selected_boxes)
                    if clicked in new_sel:
                        new_sel.remove(clicked)
                    else:
                        new_sel.append(clicked)
                    canvas.set_selection(new_sel)
                else:
                    canvas.set_selection([clicked])

                if not canvas.is_effectively_locked(clicked):
                    self.is_dragging = True
                    self.drag_mouse_start_abs = self.transformer.to_abs(
                        cx,
                        cy,
                        state.zoom_factor,
                        parent_stack,
                        cut_lines,
                        pan_offset=state.pan_offset,
                    )
                    self.drag_orig_bounds = (
                        clicked.bounds.left,
                        clicked.bounds.top,
                        clicked.bounds.right,
                        clicked.bounds.bottom,
                    )
                    self.drag_orig_descendants = {}

                    def cache_descendants(c_id: UUID):
                        comp = workspace.components.get(c_id)
                        if comp:
                            self.drag_orig_descendants[c_id] = (
                                comp.bounds.left,
                                comp.bounds.top,
                                comp.bounds.right,
                                comp.bounds.bottom,
                            )
                            for child_id in comp.childrenIds:
                                cache_descendants(child_id)

                    for child_id in clicked.childrenIds:
                        cache_descendants(child_id)
            else:
                is_multi = event.shift or event.ctrl
                if not is_multi:
                    if canvas.is_text_focused():
                        canvas.clear_text_focus()
                    else:
                        canvas.set_selection([])

                self.draw_start_x = cx
                self.draw_start_y = cy
                canvas.set_temp_rect(
                    cx, cy, cx, cy, color=ColorSystem.get_box_active(), dash=True
                )
                self.has_temp_rect = True

        elif state.current_mode == "draw":
            self.draw_start_x = cx
            self.draw_start_y = cy
            canvas.set_temp_rect(
                cx,
                cy,
                cx,
                cy,
                color=ColorSystem.get_box_inactive(),
                dash=False,
                width=2,
            )
            self.has_temp_rect = True

    def on_drag(self, canvas: Any, event: GestureEvent, cx: float, cy: float):
        """Manages viewport space shifts, vector bounds resizing, and element coordinate dragging."""
        if not canvas.full_pil_img:
            return

        if self.space_panning:
            dx = event.x - self.pan_start_mouse[0]
            dy = event.y - self.pan_start_mouse[1]
            new_pan_x = self.pan_start_offset[0] + dx
            new_pan_y = self.pan_start_offset[1] + dy
            if canvas.on_viewport_change_request:
                canvas.on_viewport_change_request(
                    canvas.zoom_factor, (new_pan_x, new_pan_y)
                )
            return

        if self.has_temp_rect:
            state = canvas
            workspace = state.workspace_state
            parent_stack = state.parent_stack
            cut_lines = workspace.cutLines if workspace else []

            ax1, ay1 = self.transformer.to_abs(
                self.draw_start_x,
                self.draw_start_y,
                state.zoom_factor,
                parent_stack,
                cut_lines,
                pan_offset=state.pan_offset,
            )
            ax2, ay2 = self.transformer.to_abs(
                cx,
                cy,
                state.zoom_factor,
                parent_stack,
                cut_lines,
                pan_offset=state.pan_offset,
            )

            boundary = self._resolve_boundary(canvas)
            bx1, by1, bx2, by2 = boundary

            if self.transformer.has_active_cuts(parent_stack, cut_lines):
                seg_top, seg_bot = self.transformer.get_segment_y_bounds(
                    ay1, parent_stack, cut_lines, boundary
                )
                by1 = max(by1, seg_top)
                by2 = min(by2, seg_bot)

            c_ax1 = BoundsValidator.clamp_val(ax1, bx1, bx2)
            c_ay1 = BoundsValidator.clamp_val(ay1, by1, by2)
            c_ax2 = BoundsValidator.clamp_val(ax2, bx1, bx2)
            c_ay2 = BoundsValidator.clamp_val(ay2, by1, by2)

            gcx1, gcy1 = self.transformer.to_canvas(
                c_ax1,
                c_ay1,
                state.zoom_factor,
                parent_stack,
                cut_lines,
                pan_offset=state.pan_offset,
            )
            gcx2, gcy2 = self.transformer.to_canvas(
                c_ax2,
                c_ay2,
                state.zoom_factor,
                parent_stack,
                cut_lines,
                pan_offset=state.pan_offset,
            )

            canvas.update_temp_rect(gcx1, gcy1, gcx2, gcy2)
            return

        state = canvas
        workspace = state.workspace_state
        parent_stack = state.parent_stack
        cut_lines = workspace.cutLines if workspace else []
        selected_boxes = [
            workspace.components[uid]
            for uid in state.selected_component_ids
            if workspace and uid in workspace.components
        ]

        if not self.is_dragging or len(selected_boxes) != 1:
            return

        box = selected_boxes[0]
        mx, my = self.transformer.to_abs(
            cx,
            cy,
            state.zoom_factor,
            parent_stack,
            cut_lines,
            pan_offset=state.pan_offset,
        )
        orig_mx, orig_my = self.drag_mouse_start_abs

        dx = mx - orig_mx
        dy = my - orig_my

        boundary = self._resolve_boundary(canvas)
        bx1, by1, bx2, by2 = boundary

        if self.transformer.has_active_cuts(parent_stack, cut_lines):
            seg_top, seg_bot = self.transformer.get_segment_y_bounds(
                self.drag_orig_bounds[1], parent_stack, cut_lines, boundary
            )
            by1 = max(by1, seg_top)
            by2 = min(by2, seg_bot)

        if self.resize_handle:
            ox1, oy1, ox2, oy2 = self.drag_orig_bounds
            union = canvas.get_children_bounds_union(box)
            rx1, ry1, rx2, ry2 = BoundsValidator.clamp_resize(
                ox1,
                oy1,
                ox2,
                oy2,
                dx,
                dy,
                self.resize_handle,
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
            if canvas.on_active_interaction_changed:
                canvas.on_active_interaction_changed(active_int)

        else:
            ox1, oy1, ox2, oy2 = self.drag_orig_bounds
            w, h = ox2 - ox1, oy2 - oy1
            rx1, ry1 = BoundsValidator.clamp_box_position(
                ox1, oy1, w, h, dx, dy, bx1, by1, bx2, by2
            )
            ddx = rx1 - ox1
            ddy = ry1 - oy1

            active_int = (
                dict(canvas.active_interaction) if canvas.active_interaction else {}
            )
            active_int[box.id] = Bounds(x=rx1, y=ry1, w=w, h=h)

            def shift_descendants_transient(c_id: UUID):
                comp = workspace.components.get(c_id)
                if comp and c_id in self.drag_orig_descendants:
                    d_ox1, d_oy1, d_ox2, d_oy2 = self.drag_orig_descendants[c_id]
                    d_w = d_ox2 - d_ox1
                    d_h = d_oy2 - d_oy1
                    active_int[c_id] = Bounds(
                        x=d_ox1 + ddx, y=d_oy1 + ddy, w=d_w, h=d_h
                    )
                    for child_id in comp.childrenIds:
                        shift_descendants_transient(child_id)

            for child_id in box.childrenIds:
                shift_descendants_transient(child_id)

            if canvas.on_active_interaction_changed:
                canvas.on_active_interaction_changed(active_int)

        canvas.schedule_redraw()

    def on_release(self, canvas: Any, event: GestureEvent, cx: float, cy: float):
        """Concludes drawing operations, committing element shifts or selections to model layers."""
        if not canvas.full_pil_img:
            return

        if self.space_panning:
            self.space_panning = False
            canvas.set_cursor("pan_inactive")
            return

        state = canvas
        workspace = state.workspace_state
        parent_stack = state.parent_stack
        cut_lines = workspace.cutLines if workspace else []
        selected_boxes = [
            workspace.components[uid]
            for uid in state.selected_component_ids
            if workspace and uid in workspace.components
        ]

        event_generated = False

        if state.current_mode == "select":
            if self.has_temp_rect:
                canvas.clear_temp_rect()
                self.has_temp_rect = False

                boundary = self._resolve_boundary(canvas)
                bx1, by1, bx2, by2 = boundary
                ax1, ay1 = self.transformer.to_abs(
                    self.draw_start_x,
                    self.draw_start_y,
                    state.zoom_factor,
                    parent_stack,
                    cut_lines,
                    pan_offset=state.pan_offset,
                )
                ax2, ay2 = self.transformer.to_abs(
                    cx,
                    cy,
                    state.zoom_factor,
                    parent_stack,
                    cut_lines,
                    pan_offset=state.pan_offset,
                )

                if self.transformer.has_active_cuts(parent_stack, cut_lines):
                    seg_top, seg_bot = self.transformer.get_segment_y_bounds(
                        ay1, parent_stack, cut_lines, boundary
                    )
                    by1 = max(by1, seg_top)
                    by2 = min(by2, seg_bot)

                left = max(bx1, min(bx2, min(ax1, ax2)))
                top = max(by1, min(by2, min(ay1, ay2)))
                right = max(bx1, min(bx2, max(ax1, ax2)))
                bot = max(by1, min(by2, max(ay1, ay2)))

                if (right - left) > 3 or (bot - top) > 3:
                    intersected = []
                    for box in canvas.get_active_boxes():
                        if (
                            box.bounds.left < right
                            and box.bounds.right > left
                            and box.bounds.top < bot
                            and box.bounds.bottom > top
                        ):
                            intersected.append(box)

                    is_multi = event.shift or event.ctrl
                    if is_multi:
                        new_sel = list(selected_boxes)
                        for box in intersected:
                            if box not in new_sel:
                                new_sel.append(box)
                        canvas.set_selection(new_sel)
                    else:
                        canvas.set_selection(intersected)

            elif self.is_dragging:
                box = selected_boxes[0]
                is_resize = self.resize_handle is not None

                active_int = canvas.active_interaction
                transient_bounds = active_int.get(box.id) if active_int else None

                ox1, oy1, ox2, oy2 = self.drag_orig_bounds
                if transient_bounds and (
                    transient_bounds.left != ox1
                    or transient_bounds.top != oy1
                    or transient_bounds.right != ox2
                    or transient_bounds.bottom != oy2
                ):
                    if is_resize:
                        if canvas.on_component_resized:
                            canvas.on_component_resized(
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
                        if canvas.on_component_moved:
                            canvas.on_component_moved(
                                str(box.id),
                                int(transient_bounds.x),
                                int(transient_bounds.y),
                            )
                        event_generated = True

        elif state.current_mode == "draw" and self.has_temp_rect:
            canvas.clear_temp_rect()
            self.has_temp_rect = False

            if abs(cx - self.draw_start_x) > 5 and abs(cy - self.draw_start_y) > 5:
                boundary = self._resolve_boundary(canvas)
                bx1, by1, bx2, by2 = boundary
                ax1, ay1 = self.transformer.to_abs(
                    self.draw_start_x,
                    self.draw_start_y,
                    state.zoom_factor,
                    parent_stack,
                    cut_lines,
                    pan_offset=state.pan_offset,
                )
                ax2, ay2 = self.transformer.to_abs(
                    cx,
                    cy,
                    state.zoom_factor,
                    parent_stack,
                    cut_lines,
                    pan_offset=state.pan_offset,
                )

                if self.transformer.has_active_cuts(parent_stack, cut_lines):
                    seg_top, seg_bot = self.transformer.get_segment_y_bounds(
                        ay1, parent_stack, cut_lines, boundary
                    )
                    by1 = max(by1, seg_top)
                    by2 = min(by2, seg_bot)

                left = max(bx1, min(bx2, min(ax1, ax2)))
                top = max(by1, min(by2, min(ay1, ay2)))
                right = max(bx1, min(bx2, max(ax1, ax2)))
                bot = max(by1, min(by2, max(ay1, ay2)))

                if right - left > 3 and bot - top > 3:
                    if canvas.on_component_created:
                        canvas.on_component_created(
                            {
                                "x": left,
                                "y": top,
                                "w": right - left,
                                "h": bot - top,
                            }
                        )
                    event_generated = True

        self.is_dragging = False
        self.resize_handle = None

        if not event_generated:
            active_int = canvas.active_interaction
            if active_int:
                active_dict = dict(active_int)
                if selected_boxes:
                    box = selected_boxes[0]
                    active_dict.pop(box.id, None)

                    def remove_descendants(c_id: UUID):
                        comp = workspace.components.get(c_id)
                        if comp:
                            active_dict.pop(c_id, None)
                            for child_id in comp.childrenIds:
                                remove_descendants(child_id)

                    for child_id in box.childrenIds:
                        remove_descendants(child_id)
                final_active_int = None if not active_dict else active_dict
                if canvas.on_active_interaction_changed:
                    canvas.on_active_interaction_changed(final_active_int)
            canvas.schedule_redraw()

    def on_mouse_move(self, canvas: Any, event: GestureEvent, cx: float, cy: float):
        """Adjusts visual cursors depending on mouse hover positions over resize handles."""
        if not canvas.full_pil_img:
            return
        state = canvas
        if state.current_mode == "pan" or canvas.space_pan_active:
            canvas.set_cursor("pan_active" if self.space_panning else "pan_inactive")
            return

        workspace = state.workspace_state
        parent_stack = state.parent_stack
        cut_lines = workspace.cutLines if workspace else []
        selected_boxes = [
            workspace.components[uid]
            for uid in state.selected_component_ids
            if workspace and uid in workspace.components
        ]

        if (
            state.current_mode == "select"
            and len(selected_boxes) == 1
            and not self.is_dragging
        ):
            handle = self.hit_handle(
                canvas,
                cx,
                cy,
                selected_boxes,
                state.zoom_factor,
                parent_stack,
                cut_lines,
                state.pan_offset,
            )
            if handle:
                cursors = {
                    "nw": "size_nw_se",
                    "se": "size_nw_se",
                    "ne": "size_ne_sw",
                    "sw": "size_ne_sw",
                    "n": "size_ns",
                    "s": "size_ns",
                    "e": "size_we",
                    "w": "size_we",
                }
                canvas.set_cursor(cursors.get(handle, ""))
                return

        if state.current_mode == "draw":
            canvas.set_cursor("draw")
            return

        canvas.set_cursor("default")

    def on_middle_click(self, canvas: Any, event: GestureEvent):
        """Initiates viewport space panning via middle mouse press."""
        if not canvas.full_pil_img:
            return
        self.space_panning = True
        self.pan_start_mouse = (event.x, event.y)
        self.pan_start_offset = canvas.pan_offset
        canvas.set_cursor("pan_active")

    def on_middle_drag(self, canvas: Any, event: GestureEvent):
        """Handles viewport space panning via middle mouse dragging."""
        if not canvas.full_pil_img:
            return
        if self.space_panning:
            dx = event.x - self.pan_start_mouse[0]
            dy = event.y - self.pan_start_mouse[1]
            new_pan_x = self.pan_start_offset[0] + dx
            new_pan_y = self.pan_start_offset[1] + dy
            if canvas.on_viewport_change_request:
                canvas.on_viewport_change_request(
                    canvas.zoom_factor, (new_pan_x, new_pan_y)
                )

    def on_middle_release(self, canvas: Any, event: GestureEvent, cx: float, cy: float):
        """Concludes viewport space panning via middle mouse release."""
        if not canvas.full_pil_img:
            return
        self.space_panning = False
        self.on_mouse_move(canvas, event, cx, cy)

    def on_right_click(self, canvas: Any, event: GestureEvent, cx: float, cy: float):
        """Identifies right-clicked component and triggers the context menu delegate."""
        if not canvas.full_pil_img:
            return

        state = canvas
        workspace = state.workspace_state
        parent_stack = state.parent_stack
        cut_lines = workspace.cutLines if workspace else []
        selected_boxes = [
            workspace.components[uid]
            for uid in state.selected_component_ids
            if workspace and uid in workspace.components
        ]

        active_comps = canvas.get_active_boxes()
        clicked = self.hit_box(
            canvas,
            cx,
            cy,
            active_comps,
            selected_boxes,
            state.zoom_factor,
            parent_stack,
            cut_lines,
            state.pan_offset,
        )

        if canvas.on_request_context_menu:
            canvas.on_request_context_menu(event, clicked)

    def on_control_click(self, canvas: Any, event: GestureEvent, cx: float, cy: float):
        """Handles Control/Command click shortcuts to drill down into components."""
        if not canvas.full_pil_img:
            return

        state = canvas
        workspace = state.workspace_state
        parent_stack = state.parent_stack
        cut_lines = workspace.cutLines if workspace else []
        selected_boxes = [
            workspace.components[uid]
            for uid in state.selected_component_ids
            if workspace and uid in workspace.components
        ]

        active_comps = canvas.get_active_boxes()
        clicked = self.hit_box(
            canvas,
            cx,
            cy,
            active_comps,
            selected_boxes,
            state.zoom_factor,
            parent_stack,
            cut_lines,
            state.pan_offset,
        )

        if clicked:
            if canvas.on_drill_into:
                canvas.on_drill_into(clicked.id)

    def on_scroll(
        self,
        canvas: Any,
        delta: float,
        mouse_x: float,
        mouse_y: float,
        shift: bool = False,
        ctrl: bool = False,
    ):
        """Translates wheel rotations to zoom scales or horizontal/vertical scrolls."""
        if not canvas.full_pil_img:
            return

        state = canvas
        if ctrl:
            self.zoom(canvas, delta / 1200.0, (mouse_x, mouse_y))
        else:
            pan_x, pan_y = state.pan_offset
            if shift:
                pan_x += delta
            else:
                pan_y += delta

            if canvas.on_viewport_change_request:
                canvas.on_viewport_change_request(canvas.zoom_factor, (pan_x, pan_y))

    def on_trackpad_scroll(
        self,
        canvas: Any,
        delta_x: float,
        delta_y: float,
        mouse_x: float,
        mouse_y: float,
        ctrl: bool = False,
    ):
        """Processes trackpad inputs, supporting standard panning and pinch-zooms."""
        if not canvas.full_pil_img:
            return

        if ctrl:
            zoom_delta = delta_y * 0.01
            self.zoom(canvas, zoom_delta, mouse_pos=(mouse_x, mouse_y))
        else:
            state = canvas
            pan_x, pan_y = state.pan_offset
            pan_x += delta_x
            pan_y += delta_y
            if canvas.on_viewport_change_request:
                canvas.on_viewport_change_request(canvas.zoom_factor, (pan_x, pan_y))

    def zoom(
        self,
        canvas: Any,
        delta: float,
        mouse_pos: tuple[float, float] | None = None,
    ):
        """Rescales the viewport zoom factor focusing around the target mouse position."""
        if not canvas.full_pil_img:
            return
        state = canvas
        workspace = state.workspace_state
        parent_stack = state.parent_stack
        cut_lines = workspace.cutLines if workspace else []

        old_zoom = state.zoom_factor
        new_zoom = max(0.1, min(4.0, old_zoom + delta))

        cw = canvas.width()
        ch = canvas.height()
        mx, my = mouse_pos if mouse_pos else (cw / 2, ch / 2)

        pan_x, pan_y = state.pan_offset
        abs_x, abs_y = self.transformer.to_abs(
            mx, my, old_zoom, parent_stack, cut_lines, pan_offset=(pan_x, pan_y)
        )

        gap_y = (
            self.transformer.gap_offset_for_y(abs_y)
            if self.transformer.has_active_cuts(parent_stack, cut_lines)
            else 0
        )

        new_pan_x = mx - abs_x * new_zoom
        new_pan_y = my - (abs_y + gap_y) * new_zoom

        if canvas.on_viewport_change_request:
            canvas.on_viewport_change_request(new_zoom, (new_pan_x, new_pan_y))
