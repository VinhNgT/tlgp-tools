"""Heuristics and algorithms for determining logical reading order of UI components."""

from typing import Final
from uuid import UUID

from annotator.models import Component, WorkspaceState

from .errors import BoundaryViolationError

# Sentinel indicating that root-level sibling ordering should be recalculated.
ROOTS_CHANGED: Final = object()




def sort_components_reading_order(components: list[Component]) -> list[Component]:
    """Sort components into natural reading order (row-major) using Binary Recursive XY-Cut.
    
    Finds the single visually widest gap (gutter) on either the X or Y axis at each step,
    splits the layout along that cut line, and recurses. This matches visual hierarchy
    perfectly, resolving both column and row structures without interleaving.
    """
    if len(components) <= 1:
        return list(components)

    def get_intervals_and_max_gap(objs: list[Component], axis: str) -> tuple[list[tuple[int, int, Component]], tuple[int, float] | None]:
        # Get shrunk intervals for elements
        intervals = []
        for o in objs:
            if axis == 'x':
                left, right = o.bounds.left, o.bounds.right
                h_tol = min(2, (right - left) // 4)
                intervals.append((left + h_tol, right - h_tol, o))
            else:
                top, bottom = o.bounds.top, o.bounds.bottom
                v_tol = min(2, (bottom - top) // 4)
                intervals.append((top + v_tol, bottom - v_tol, o))

        intervals.sort(key=lambda x: x[0])

        # Merge intervals to find gaps
        merged = []
        for start, end, obj in intervals:
            if not merged:
                merged.append((start, end, [obj]))
            else:
                prev_start, prev_end, prev_objs = merged[-1]
                if start <= prev_end:
                    merged[-1] = (prev_start, max(prev_end, end), prev_objs + [obj])
                else:
                    merged.append((start, end, [obj]))

        if len(merged) <= 1:
            return intervals, None

        # Find the widest gap between merged intervals
        max_gap_width = -1
        cut_coord = 0.0
        for i in range(len(merged) - 1):
            gap_width = merged[i+1][0] - merged[i][1]
            if gap_width > max_gap_width:
                max_gap_width = gap_width
                cut_coord = (merged[i][1] + merged[i+1][0]) / 2.0

        return intervals, (max_gap_width, cut_coord)

    def recurse(objs: list[Component]) -> list[Component]:
        if len(objs) <= 1:
            return objs

        # Find widest gap on X and Y
        x_intervals, x_gap_info = get_intervals_and_max_gap(objs, 'x')
        y_intervals, y_gap_info = get_intervals_and_max_gap(objs, 'y')

        x_width = x_gap_info[0] if x_gap_info else -1
        y_width = y_gap_info[0] if y_gap_info else -1

        # If no gaps on either axis, fallback to sorting
        if x_width <= 0 and y_width <= 0:
            from functools import cmp_to_key

            def compare_components(a: Component, b: Component) -> int:
                a_bounds = a.bounds
                b_bounds = b.bounds

                # Does A contain B?
                a_contains_b = (
                    a_bounds.left <= b_bounds.left
                    and a_bounds.right >= b_bounds.right
                    and a_bounds.top <= b_bounds.top
                    and a_bounds.bottom >= b_bounds.bottom
                )
                # Does B contain A?
                b_contains_a = (
                    b_bounds.left <= a_bounds.left
                    and b_bounds.right >= a_bounds.right
                    and b_bounds.top <= a_bounds.top
                    and b_bounds.bottom >= a_bounds.bottom
                )

                if a_contains_b and not b_contains_a:
                    return -1  # A contains B, so A comes first
                if b_contains_a and not a_contains_b:
                    return 1   # B contains A, so B comes first

                # Standard row-major center sorting
                cy_a = (a_bounds.top + a_bounds.bottom) / 2.0
                cy_b = (b_bounds.top + b_bounds.bottom) / 2.0

                h_limit = min(10, a_bounds.h / 4, b_bounds.h / 4)
                if abs(cy_a - cy_b) < h_limit:
                    cx_a = (a_bounds.left + a_bounds.right) / 2.0
                    cx_b = (b_bounds.left + b_bounds.right) / 2.0
                    if cx_a < cx_b:
                        return -1
                    elif cx_a > cx_b:
                        return 1
                    return 0
                else:
                    if cy_a < cy_b:
                        return -1
                    elif cy_a > cy_b:
                        return 1
                    return 0

            sorted_objs = list(objs)
            sorted_objs.sort(key=cmp_to_key(compare_components))
            return sorted_objs

        # Split at the widest gap
        # Tie-breaker: prefer Y (horizontal split) to keep rows together
        if x_width > y_width:
            cut_x = x_gap_info[1]
            left_group = [o for o in objs if (o.bounds.left + o.bounds.right) / 2.0 < cut_x]
            right_group = [o for o in objs if (o.bounds.left + o.bounds.right) / 2.0 >= cut_x]
            return recurse(left_group) + recurse(right_group)
        else:
            cut_y = y_gap_info[1]
            top_group = [o for o in objs if (o.bounds.top + o.bounds.bottom) / 2.0 < cut_y]
            bottom_group = [o for o in objs if (o.bounds.top + o.bounds.bottom) / 2.0 >= cut_y]
            return recurse(top_group) + recurse(bottom_group)

    return recurse(components)


def recalculate_tree(state: WorkspaceState, changed_id: UUID | object | None = None):
    """
    Performs a top-down pass over the WorkspaceState flat map to:
    1. Sort siblings visually in natural reading order (row-major).
       If `changed_id` is provided, we ONLY sort the siblings of that level
       (and do not sort any other levels/branches).
    2. Auto-assign numbers (e.g. '1', '2', '3') relative to siblings.
    """

    # 0. Validate parent-child boundaries for mutated components recursively
    if changed_id and isinstance(changed_id, UUID):

        def check_recursive(cid: UUID):
            comp = state.components.get(cid)
            if not comp:
                return
            if comp.parentId:
                parent = state.components.get(comp.parentId)
                if parent:
                    c = comp.bounds
                    p = parent.bounds
                    if (
                        c.left < p.left
                        or c.top < p.top
                        or c.right > p.right
                        or c.bottom > p.bottom
                    ):
                        raise BoundaryViolationError(
                            f"Component '{comp.label}' bounds violate parent boundaries.",
                            component_id=str(comp.id),
                            parent_id=str(comp.parentId),
                            component_bounds=c.model_dump(),
                            parent_bounds=p.model_dump(),
                        )
            for child_id in comp.childrenIds:
                check_recursive(child_id)

        check_recursive(changed_id)



    # 1. Row-major visual sorting step
    if changed_id is ROOTS_CHANGED:
        valid_roots = [
            state.components[rid]
            for rid in state.rootComponents
            if rid in state.components
        ]
        sorted_roots = sort_components_reading_order(valid_roots)
        state.rootComponents = [r.id for r in sorted_roots]
    elif isinstance(changed_id, UUID):
        changed_comp = state.components.get(changed_id)
        if changed_comp:
            if changed_comp.parentId:
                parent = state.components.get(changed_comp.parentId)
                if parent:
                    valid_children = [
                        state.components[cid]
                        for cid in parent.childrenIds
                        if cid in state.components
                    ]
                    sorted_children = sort_components_reading_order(valid_children)
                    parent.childrenIds = [c.id for c in sorted_children]
            else:
                valid_roots = [
                    state.components[rid]
                    for rid in state.rootComponents
                    if rid in state.components
                ]
                sorted_roots = sort_components_reading_order(valid_roots)
                state.rootComponents = [r.id for r in sorted_roots]
    else:
        # Fallback/full sort: sort root components and all children levels recursively
        def sort_recursive(comp_id: UUID):
            comp = state.components.get(comp_id)
            if not comp:
                return
            valid_children = [
                state.components[cid]
                for cid in comp.childrenIds
                if cid in state.components
            ]
            sorted_children = sort_components_reading_order(valid_children)
            comp.childrenIds = [c.id for c in sorted_children]
            for child in sorted_children:
                sort_recursive(child.id)

        valid_roots = [
            state.components[rid]
            for rid in state.rootComponents
            if rid in state.components
        ]
        sorted_roots = sort_components_reading_order(valid_roots)
        state.rootComponents = [r.id for r in sorted_roots]
        for root in sorted_roots:
            sort_recursive(root.id)

    # 2. Numbering assignment step (top-down walk, always needed to keep numbers consistent)
    def assign_numbers(comp_id: UUID, number: str):
        comp = state.components.get(comp_id)
        if not comp:
            return
        comp.number = number
        comp.childrenIds = [cid for cid in comp.childrenIds if cid in state.components]
        visible_idx = 0
        for child_id in comp.childrenIds:
            child = state.components.get(child_id)
            if child:
                assign_numbers(child_id, str(visible_idx + 1))
                visible_idx += 1

    state.rootComponents = [
        rid for rid in state.rootComponents if rid in state.components
    ]
    visible_root_idx = 0
    for root_id in state.rootComponents:
        root = state.components.get(root_id)
        if root:
            assign_numbers(root_id, str(visible_root_idx + 1))
            visible_root_idx += 1
