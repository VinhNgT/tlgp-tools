import sys
import time
import tkinter as tk
from uuid import UUID

from models import Bounds, Component
from ..domain.validation import BoundsValidator
from ..state import UIStateStore
from .transformer import ViewportTransformer


class GestureInterpreter:
    """Manages active canvas gestures (moving, resizing, viewport panning) and pointer hit tests."""

    def __init__(self, store: UIStateStore, transformer: ViewportTransformer):
        self.store = store
        self.transformer = transformer

        # Interaction tracking
        self.is_dragging = False
        self.drag_mouse_start_abs = (0, 0)
        self.resize_handle: str | None = None
        self.drag_orig_bounds = (0, 0, 0, 0)  # (left, top, right, bottom) raw absolute
        self.drag_orig_descendants: dict[UUID, tuple[int, int, int, int]] = {}

        # Viewport space panning tracking
        self.space_panning = False
        self.pan_start_mouse = (0, 0)
        self.pan_start_offset = (0.0, 0.0)

        # Drawing coordinates
        self.draw_start_x = 0.0
        self.draw_start_y = 0.0
        self.temp_rect_id = None

        # Double-click interaction tracking
        self.last_click_time = 0.0
        self.last_click_cx = 0.0
        self.last_click_cy = 0.0
        self.click_sequence_count = 0
        self.cycle_components = None
        self.last_cycle_index = -1

    def hit_handle(
        self,
        cx: float,
        cy: float,
        selected_boxes: list[Component],
        zoom_factor: float,
        parent_stack: list[UUID],
        cut_lines: list[int],
    ) -> str | None:
        """Determines if pointer lies within interactive drag handles of selected component."""
        if len(selected_boxes) != 1:
            return None
        box = selected_boxes[0]
        if getattr(box.visibility, "locked", False) or not getattr(
            box.visibility, "visible", True
        ):
            return None

        pan_offset = self.store.state.pan_offset
        cx1, cy1 = self.transformer.to_canvas(
            box.bounds.left, box.bounds.top, zoom_factor, parent_stack, cut_lines, pan_offset=pan_offset
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
        cx: float,
        cy: float,
        components: list[Component],
        zoom_factor: float,
        parent_stack: list[UUID],
        cut_lines: list[int],
    ) -> list[Component]:
        """Calculates a list of all visible components intersected by absolute coordinates."""
        hit = []
        for box in components:
            if not getattr(box.visibility, "visible", True):
                continue
            pan_offset = self.store.state.pan_offset
            bx1, by1 = self.transformer.to_canvas(
                box.bounds.left, box.bounds.top, zoom_factor, parent_stack, cut_lines, pan_offset=pan_offset
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
        cx: float,
        cy: float,
        components: list[Component],
        selected_boxes: list[Component],
        zoom_factor: float,
        parent_stack: list[UUID],
        cut_lines: list[int],
    ) -> Component | None:
        """Identifies intersected component, sorting with selected box priorities for cycling."""
        boxes = self.get_hit_boxes(
            cx, cy, components, zoom_factor, parent_stack, cut_lines
        )
        if not boxes:
            return None
        selected = [b for b in boxes if b in selected_boxes]
        non_selected = [b for b in boxes if b not in selected_boxes]
        ordered = non_selected + selected
        return ordered[-1] if ordered else None

    def on_click(self, canvas, event, cx: float, cy: float):
        """Processes canvas click triggers, initiating moves, resizes, or workspace panning."""
        if not canvas.full_pil_img:
            return

        state = self.store.state
        if canvas._space_pan_active or state.current_mode == "pan":
            self.space_panning = True
            self.pan_start_mouse = (event.x, event.y)
            self.pan_start_offset = state.pan_offset
            canvas.config(cursor=canvas._get_pan_cursor(active=True))
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
        is_multi = (event.state & 0x0001) or (event.state & 0x0004)
        active_comps = canvas._active_boxes()
        hit_boxes_at_click = self.get_hit_boxes(
            cx, cy, active_comps, state.zoom_factor, parent_stack, cut_lines
        )
        primary_sel = selected_boxes[-1] if selected_boxes else None

        clicked = self.hit_box(
            cx,
            cy,
            active_comps,
            selected_boxes,
            state.zoom_factor,
            parent_stack,
            cut_lines,
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
                cx, cy, selected_boxes, state.zoom_factor, parent_stack, cut_lines
            )
            if not handle:
                if self.cycle_components is None:
                    hit_boxes = list(hit_boxes_at_click)
                    hit_boxes.reverse()
                    if len(hit_boxes) > 1:
                        self.cycle_components = hit_boxes
                        if primary_sel in hit_boxes:
                            self.last_cycle_index = hit_boxes.index(primary_sel)
                        else:
                            self.last_cycle_index = 0

                if self.cycle_components is not None:
                    self.last_cycle_index = (self.last_cycle_index + 1) % len(
                        self.cycle_components
                    )
                    new_box = self.cycle_components[self.last_cycle_index]
                    canvas.set_selection([new_box])

                    if not getattr(new_box.visibility, "locked", False):
                        self.is_dragging = True
                        self.drag_mouse_start_abs = self.transformer.to_abs(
                            cx, cy, state.zoom_factor, parent_stack, cut_lines, pan_offset=state.pan_offset
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
            cx, cy, selected_boxes, state.zoom_factor, parent_stack, cut_lines
        )
        if handle:
            self.resize_handle = handle
            self.is_dragging = True
            self.drag_mouse_start_abs = self.transformer.to_abs(
                cx, cy, state.zoom_factor, parent_stack, cut_lines, pan_offset=state.pan_offset
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
                is_multi = (event.state & 0x0001) or (event.state & 0x0004)
                if is_multi:
                    new_sel = list(selected_boxes)
                    if clicked in new_sel:
                        new_sel.remove(clicked)
                    else:
                        new_sel.append(clicked)
                    canvas.set_selection(new_sel)
                else:
                    canvas.set_selection([clicked])

                if not getattr(clicked.visibility, "locked", False):
                    self.is_dragging = True
                    self.drag_mouse_start_abs = self.transformer.to_abs(
                        cx, cy, state.zoom_factor, parent_stack, cut_lines, pan_offset=state.pan_offset
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
                is_multi = (event.state & 0x0001) or (event.state & 0x0004)
                if not is_multi:
                    parent_app = canvas.winfo_toplevel()
                    if (
                        hasattr(parent_app, "is_text_focused")
                        and parent_app.is_text_focused()
                    ):
                        parent_app.focus_set()
                    else:
                        canvas.set_selection([])

                self.draw_start_x = cx
                self.draw_start_y = cy
                self.temp_rect_id = canvas.create_rectangle(
                    cx, cy, cx, cy, outline="#0c8ce9", dash=(2, 2)
                )

        elif state.current_mode == "draw":
            self.draw_start_x = cx
            self.draw_start_y = cy
            self.temp_rect_id = canvas.create_rectangle(
                cx, cy, cx, cy, outline="#ff4444", width=2
            )

    def on_drag(self, canvas, event, cx: float, cy: float):
        """Manages viewport space shifts, vector bounds resizing, and element coordinate dragging."""
        if not canvas.full_pil_img:
            return

        if self.space_panning:
            dx = event.x - self.pan_start_mouse[0]
            dy = event.y - self.pan_start_mouse[1]
            new_pan_x = self.pan_start_offset[0] + dx
            new_pan_y = self.pan_start_offset[1] + dy
            self.store.update_state("viewport", pan_offset=(new_pan_x, new_pan_y))
            return

        if self.temp_rect_id:
            state = self.store.state
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

            bx1, by1, bx2, by2 = self.transformer.get_boundary(parent_stack, workspace)

            if self.transformer.has_active_cuts(parent_stack, cut_lines):
                seg_top, seg_bot = self.transformer.get_segment_y_bounds(
                    ay1, parent_stack, cut_lines, workspace
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

            canvas.coords(self.temp_rect_id, gcx1, gcy1, gcx2, gcy2)
            return

        state = self.store.state
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
            cx, cy, state.zoom_factor, parent_stack, cut_lines, pan_offset=state.pan_offset
        )
        orig_mx, orig_my = self.drag_mouse_start_abs

        dx = mx - orig_mx
        dy = my - orig_my

        bx1, by1, bx2, by2 = self.transformer.get_boundary(parent_stack, workspace)

        if self.transformer.has_active_cuts(parent_stack, cut_lines):
            seg_top, seg_bot = self.transformer.get_segment_y_bounds(
                self.drag_orig_bounds[1], parent_stack, cut_lines, workspace
            )
            by1 = max(by1, seg_top)
            by2 = min(by2, seg_bot)

        if self.resize_handle:
            ox1, oy1, ox2, oy2 = self.drag_orig_bounds
            union = canvas._get_children_bounds_union(box)
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
            active_int = dict(self.store.state.active_interaction) if self.store.state.active_interaction else {}
            active_int[box.id] = bounds
            self.store.update_state("selection", active_interaction=active_int)

        else:
            ox1, oy1, ox2, oy2 = self.drag_orig_bounds
            w, h = ox2 - ox1, oy2 - oy1
            rx1, ry1 = BoundsValidator.clamp_box_position(
                ox1, oy1, w, h, dx, dy, bx1, by1, bx2, by2
            )
            ddx = rx1 - ox1
            ddy = ry1 - doy1 if 'doy1' in locals() else ry1 - oy1

            active_int = dict(self.store.state.active_interaction) if self.store.state.active_interaction else {}
            active_int[box.id] = Bounds(x=rx1, y=ry1, w=w, h=h)

            def shift_descendants_transient(c_id: UUID):
                comp = workspace.components.get(c_id)
                if comp and c_id in self.drag_orig_descendants:
                    d_ox1, d_oy1, d_ox2, d_oy2 = self.drag_orig_descendants[c_id]
                    d_w = d_ox2 - d_ox1
                    d_h = d_oy2 - d_oy1
                    active_int[c_id] = Bounds(x=d_ox1 + ddx, y=d_oy1 + ddy, w=d_w, h=d_h)
                    for child_id in comp.childrenIds:
                        shift_descendants_transient(child_id)

            for child_id in box.childrenIds:
                shift_descendants_transient(child_id)

            self.store.update_state("selection", active_interaction=active_int)

        canvas.draw_boxes()

    def on_release(self, canvas, event, cx: float, cy: float):
        """Concludes drawing operations, committing element shifts or selections to model layers."""
        if not canvas.full_pil_img:
            return

        if self.space_panning:
            self.space_panning = False
            canvas.config(cursor=canvas._get_pan_cursor(active=False))
            return

        state = self.store.state
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
            if self.temp_rect_id:
                canvas.delete(self.temp_rect_id)
                self.temp_rect_id = None

                bx1, by1, bx2, by2 = self.transformer.get_boundary(parent_stack, workspace)
                ax1, ay1 = self.transformer.to_abs(
                    self.draw_start_x,
                    self.draw_start_y,
                    state.zoom_factor,
                    parent_stack,
                    cut_lines,
                    pan_offset=state.pan_offset,
                )
                ax2, ay2 = self.transformer.to_abs(
                    cx, cy, state.zoom_factor, parent_stack, cut_lines, pan_offset=state.pan_offset
                )

                if self.transformer.has_active_cuts(parent_stack, cut_lines):
                    seg_top, seg_bot = self.transformer.get_segment_y_bounds(
                        ay1, parent_stack, cut_lines, workspace
                    )
                    by1 = max(by1, seg_top)
                    by2 = min(by2, seg_bot)

                left = max(bx1, min(bx2, min(ax1, ax2)))
                top = max(by1, min(by2, min(ay1, ay2)))
                right = max(bx1, min(bx2, max(ax1, ax2)))
                bot = max(by1, min(by2, max(ay1, ay2)))

                if (right - left) > 3 or (bot - top) > 3:
                    intersected = []
                    for box in canvas._active_boxes():
                        if (
                            box.bounds.left < right
                            and box.bounds.right > left
                            and box.bounds.top < bot
                            and box.bounds.bottom > top
                        ):
                            intersected.append(box)

                    is_multi = (event.state & 0x0001) or (event.state & 0x0004)
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

                active_int = self.store.state.active_interaction
                transient_bounds = active_int.get(box.id) if active_int else None

                ox1, oy1, ox2, oy2 = self.drag_orig_bounds
                if transient_bounds and (
                    transient_bounds.left != ox1
                    or transient_bounds.top != oy1
                    or transient_bounds.right != ox2
                    or transient_bounds.bottom != oy2
                ):
                    if is_resize:
                        canvas.last_resized_component = (
                            box,
                            {
                                "x": int(transient_bounds.x),
                                "y": int(transient_bounds.y),
                                "w": int(transient_bounds.w),
                                "h": int(transient_bounds.h),
                            },
                        )
                        canvas.event_generate("<<ComponentResized>>")
                        event_generated = True
                    else:
                        canvas.last_moved_component = (box, int(transient_bounds.x), int(transient_bounds.y))
                        canvas.event_generate("<<ComponentMoved>>")
                        event_generated = True

        elif state.current_mode == "draw" and self.temp_rect_id:
            canvas.delete(self.temp_rect_id)
            self.temp_rect_id = None

            if abs(cx - self.draw_start_x) > 5 and abs(cy - self.draw_start_y) > 5:
                bx1, by1, bx2, by2 = self.transformer.get_boundary(parent_stack, workspace)
                ax1, ay1 = self.transformer.to_abs(
                    self.draw_start_x,
                    self.draw_start_y,
                    state.zoom_factor,
                    parent_stack,
                    cut_lines,
                    pan_offset=state.pan_offset,
                )
                ax2, ay2 = self.transformer.to_abs(
                    cx, cy, state.zoom_factor, parent_stack, cut_lines, pan_offset=state.pan_offset
                )

                if self.transformer.has_active_cuts(parent_stack, cut_lines):
                    seg_top, seg_bot = self.transformer.get_segment_y_bounds(
                        ay1, parent_stack, cut_lines, workspace
                    )
                    by1 = max(by1, seg_top)
                    by2 = min(by2, seg_bot)

                left = max(bx1, min(bx2, min(ax1, ax2)))
                top = max(by1, min(by2, min(ay1, ay2)))
                right = max(bx1, min(bx2, max(ax1, ax2)))
                bot = max(by1, min(by2, max(ay1, ay2)))

                if right - left > 3 and bot - top > 3:
                    canvas.last_created_component = {
                        "x": int(left),
                        "y": int(top),
                        "w": int(right - left),
                        "h": int(bot - top),
                    }
                    canvas.event_generate("<<ComponentCreated>>")
                    event_generated = True

        self.is_dragging = False
        self.resize_handle = None

        if not event_generated:
            active_int = self.store.state.active_interaction
            if active_int:
                active_int = dict(active_int)
                if selected_boxes:
                    box = selected_boxes[0]
                    active_int.pop(box.id, None)
                    def remove_descendants(c_id: UUID):
                        comp = workspace.components.get(c_id)
                        if comp:
                            active_int.pop(c_id, None)
                            for child_id in comp.childrenIds:
                                remove_descendants(child_id)
                    for child_id in box.childrenIds:
                        remove_descendants(child_id)
                if not active_int:
                    active_int = None
                self.store.update_state("selection", active_interaction=active_int)
            canvas.draw_boxes()

    def on_mouse_move(self, canvas, event, cx: float, cy: float):
        """Adjusts visual cursors depending on mouse hover positions over resize handles."""
        if not canvas.full_pil_img:
            return
        state = self.store.state
        if state.current_mode == "pan" or getattr(canvas, "_space_pan_active", False):
            try:
                canvas.config(cursor=canvas._get_pan_cursor(active=self.space_panning))
            except tk.TclError:
                pass
            return

        workspace = state.workspace_state
        parent_stack = state.parent_stack
        cut_lines = workspace.cutLines if workspace else []
        selected_boxes = [
            workspace.components[uid]
            for uid in state.selected_component_ids
            if workspace and uid in workspace.components
        ]

        if state.current_mode == "select" and len(selected_boxes) == 1 and not self.is_dragging:
            handle = self.hit_handle(
                cx, cy, selected_boxes, state.zoom_factor, parent_stack, cut_lines
            )
            if handle:
                if sys.platform == "darwin":
                    # macOS Cocoa cursors mapping matching the legacy tool definition
                    cursors = {
                        "nw": "resizetopleft",
                        "se": "resizebottomright",
                        "ne": "resizetopright",
                        "sw": "resizebottomleft",
                        "n": "resizeupdown",
                        "s": "resizeupdown",
                        "e": "resizeleftright",
                        "w": "resizeleftright",
                    }
                else:
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
                try:
                    canvas.config(cursor=cursors.get(handle, ""))
                except tk.TclError:
                    try:
                        canvas.config(cursor="")
                    except tk.TclError:
                        pass
                return

        if state.current_mode == "draw":
            try:
                canvas.config(cursor="crosshair")
            except tk.TclError:
                pass
            return

        try:
            canvas.config(cursor="")
        except tk.TclError:
            pass

    def on_right_click(self, canvas, event, cx: float, cy: float):
        """Identifies right-clicked component and triggers the context menu delegate."""
        if not canvas.full_pil_img:
            return

        state = self.store.state
        workspace = state.workspace_state
        parent_stack = state.parent_stack
        cut_lines = workspace.cutLines if workspace else []
        selected_boxes = [
            workspace.components[uid]
            for uid in state.selected_component_ids
            if workspace and uid in workspace.components
        ]

        active_comps = canvas._active_boxes()
        clicked = self.hit_box(
            cx,
            cy,
            active_comps,
            selected_boxes,
            state.zoom_factor,
            parent_stack,
            cut_lines,
        )

        if canvas.on_request_context_menu:
            canvas.on_request_context_menu(event, clicked)

    def on_control_click(self, canvas, event, cx: float, cy: float):
        """Handles Control/Command click shortcuts to drill down into components."""
        if not canvas.full_pil_img:
            return

        state = self.store.state
        workspace = state.workspace_state
        parent_stack = state.parent_stack
        cut_lines = workspace.cutLines if workspace else []
        selected_boxes = [
            workspace.components[uid]
            for uid in state.selected_component_ids
            if workspace and uid in workspace.components
        ]

        active_comps = canvas._active_boxes()
        clicked = self.hit_box(
            cx,
            cy,
            active_comps,
            selected_boxes,
            state.zoom_factor,
            parent_stack,
            cut_lines,
        )

        if clicked:
            canvas.drill_into(clicked.id)

    def on_scroll(self, canvas, event):
        """Translates wheel rotations to zoom scales or horizontal/vertical scrolls."""
        if not canvas.full_pil_img:
            return

        is_control = (event.state & 0x0004) != 0
        is_command = (event.state & 0x0008) != 0 or (event.state & 0x0010) != 0
        is_shift = (event.state & 0x0001) != 0

        state = self.store.state
        if is_control or is_command:
            delta = 0.0
            if event.num == 4:
                delta = 0.1
            elif event.num == 5:
                delta = -0.1
            else:
                delta = event.delta / 1200.0
            self.zoom(canvas, delta, (event.x, event.y))
        else:
            pan_x, pan_y = state.pan_offset
            if event.num == 4:
                pan_y -= 40
            elif event.num == 5:
                pan_y += 40
            elif event.delta != 0:
                if is_shift:
                    pan_x -= event.delta
                else:
                    pan_y -= event.delta

            self.store.update_state("viewport", pan_offset=(pan_x, pan_y))

    def on_touchpad_scroll(self, canvas, event):
        """Processes trackpad inputs, supporting standard panning and control-key pinch-zooms."""
        if not canvas.full_pil_img:
            return "break"
        if str(event.widget) == str(canvas):
            try:
                res = canvas.tk.call("tk::PreciseScrollDeltas", event.delta)
                deltas = canvas.tk.splitlist(res)
                delta_x = float(deltas[0])
                delta_y = float(deltas[1])
            except Exception:
                return "break"

            is_control = (event.state & 0x0004) != 0
            is_command = (event.state & 0x0008) != 0 or (event.state & 0x0010) != 0

            if is_control or is_command:
                zoom_delta = delta_y * 0.01
                self.zoom(canvas, zoom_delta, mouse_pos=(event.x, event.y))
            else:
                state = self.store.state
                pan_x, pan_y = state.pan_offset
                pan_x += delta_x
                pan_y += delta_y
                self.store.update_state("viewport", pan_offset=(pan_x, pan_y))
            return "break"

    def zoom(self, canvas, delta: float, mouse_pos: tuple[int, int] | None = None):
        """Rescales the viewport zoom factor focusing around the target mouse position."""
        if not canvas.full_pil_img:
            return
        state = self.store.state
        workspace = state.workspace_state
        parent_stack = state.parent_stack
        cut_lines = workspace.cutLines if workspace else []

        old_zoom = state.zoom_factor
        new_zoom = max(0.1, min(4.0, old_zoom + delta))

        cw = canvas.winfo_width()
        ch = canvas.winfo_height()
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

        self.store.update_state(
            "viewport", zoom_factor=new_zoom, pan_offset=(new_pan_x, new_pan_y)
        )
