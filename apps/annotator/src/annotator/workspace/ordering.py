"""Heuristics and algorithms for determining logical reading order of UI components."""

from typing import Final
from uuid import UUID

from annotator.models import Component, WorkspaceState

from .errors import BoundaryViolationError

# Sentinel indicating that root-level sibling ordering should be recalculated.
ROOTS_CHANGED: Final = object()

ROW_OVERLAP_THRESHOLD = 0.5


def _compute_overlap_ratio(a: Component, b: Component) -> float:
    """Compute the vertical overlap between two components as a ratio.

    Returns the overlap distance divided by the smaller component's height.
    Returns 0.0 if there is no overlap or either component has zero height.
    """
    overlap = min(a.bounds.bottom, b.bounds.bottom) - max(a.bounds.top, b.bounds.top)
    if overlap <= 0:
        return 0.0

    min_height = min(a.bounds.h, b.bounds.h)
    if min_height <= 0:
        return 0.0

    return overlap / min_height


class _UnionFind:
    """Lightweight union-find (disjoint set) data structure."""

    def __init__(self, n: int):
        self.parent = list(range(n))
        self.rank = [0] * n

    def find(self, x: int) -> int:
        while self.parent[x] != x:
            self.parent[x] = self.parent[self.parent[x]]
            x = self.parent[x]
        return x

    def union(self, x: int, y: int):
        rx, ry = self.find(x), self.find(y)
        if rx == ry:
            return
        if self.rank[rx] < self.rank[ry]:
            rx, ry = ry, rx
        self.parent[ry] = rx
        if self.rank[rx] == self.rank[ry]:
            self.rank[rx] += 1


def _build_row_groups(components: list[Component]) -> list[list[Component]]:
    """Group components into rows using vertical overlap and connected components."""
    n = len(components)
    if n == 0:
        return []
    if n == 1:
        return [list(components)]

    uf = _UnionFind(n)
    for i in range(n):
        for j in range(i + 1, n):
            ratio = _compute_overlap_ratio(components[i], components[j])
            if ratio >= ROW_OVERLAP_THRESHOLD:
                uf.union(i, j)

    groups = {}
    for i in range(n):
        root = uf.find(i)
        if root not in groups:
            groups[root] = []
        groups[root].append(i)

    row_groups = []
    for indices in groups.values():
        row = [components[i] for i in indices]
        row.sort(key=lambda c: c.bounds.left)
        row_groups.append(row)

    def row_median_center(row: list[Component]) -> float:
        centers = sorted((c.bounds.top + c.bounds.bottom) / 2 for c in row)
        mid = len(centers) // 2
        if len(centers) % 2 == 0:
            return (centers[mid - 1] + centers[mid]) / 2
        return centers[mid]

    row_groups.sort(key=row_median_center)
    return row_groups


def sort_components_reading_order(components: list[Component]) -> list[Component]:
    """Sort components into natural reading order (row-major)."""
    if len(components) <= 1:
        return list(components)
    row_groups = _build_row_groups(components)
    result = []
    for row in row_groups:
        result.extend(row)
    return result


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
