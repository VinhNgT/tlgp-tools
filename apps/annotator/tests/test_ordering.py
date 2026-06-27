"""Tests for annotator.workspace.ordering (sort_components_reading_order, recalculate_tree)."""

import uuid

import pytest
from annotator.models import Bounds, Component, WorkspaceState
from annotator.workspace.errors import BoundaryViolationError
from annotator.workspace.ordering import (
    recalculate_tree,
    sort_components_reading_order,
)


def _make_comp(x: int, y: int, w: int = 50, h: int = 50, label: str = "") -> Component:
    """Helper to create a Component with minimal fields."""
    return Component(
        id=uuid.uuid4(),
        number="",
        label=label,
        bounds=Bounds(x=x, y=y, w=w, h=h),
    )


# ── Reading Order Sort ─────────────────────────────────────────────────


class TestSortReadingOrder:
    def test_empty(self):
        assert sort_components_reading_order([]) == []

    def test_single(self):
        comp = _make_comp(0, 0)
        result = sort_components_reading_order([comp])
        assert result == [comp]

    def test_left_to_right_same_row(self):
        right = _make_comp(200, 0, label="right")
        left = _make_comp(0, 0, label="left")
        result = sort_components_reading_order([right, left])
        assert result[0].label == "left"
        assert result[1].label == "right"

    def test_top_to_bottom_different_rows(self):
        bottom = _make_comp(0, 200, label="bottom")
        top = _make_comp(0, 0, label="top")
        result = sort_components_reading_order([bottom, top])
        assert result[0].label == "top"
        assert result[1].label == "bottom"

    def test_tall_image_does_not_collapse_rows(self):
        checkbox = _make_comp(20, 130, 20, 20, "checkbox")
        image = _make_comp(60, 100, 180, 150, "image")
        title = _make_comp(250, 100, 700, 30, "title")
        dropdown = _make_comp(250, 140, 700, 40, "dropdown")
        price = _make_comp(250, 190, 100, 40, "price")
        qty = _make_comp(360, 190, 100, 40, "qty")

        components = [qty, price, dropdown, title, image, checkbox]
        sorted_comps = sort_components_reading_order(components)

        expected = ["checkbox", "image", "title", "dropdown", "price", "qty"]
        actual = [c.label for c in sorted_comps]
        assert actual == expected

    def test_containing_component_sorted_before_contained(self):
        # A large outer box completely contains a smaller inner box.
        # Both are siblings (not parent-child). The outer box should sort first.
        outer = _make_comp(153, 435, 281, 282, "outer")
        inner = _make_comp(281, 459, 128, 95, "inner")

        # Outer has lower top/left but center Y is lower.
        # Without containment check, inner would sort first because of higher center-Y.
        result1 = sort_components_reading_order([inner, outer])
        assert result1[0].label == "outer"
        assert result1[1].label == "inner"

        result2 = sort_components_reading_order([outer, inner])
        assert result2[0].label == "outer"
        assert result2[1].label == "inner"


# ── recalculate_tree ───────────────────────────────────────────────────


class TestRecalculateTree:
    def _build_state(self, root_bounds_list: list[tuple[int, int, int, int]]):
        """Build a simple WorkspaceState with N root components at given bounds."""
        state = WorkspaceState(workspaceId=uuid.uuid4())
        for x, y, w, h in root_bounds_list:
            comp = Component(
                id=uuid.uuid4(),
                number="",
                label=f"comp_{x}_{y}",
                bounds=Bounds(x=x, y=y, w=w, h=h),
            )
            state.components[comp.id] = comp
            state.rootComponents.append(comp.id)
        return state

    def test_assigns_numbers_to_roots(self):
        state = self._build_state([(0, 0, 50, 50), (100, 0, 50, 50)])
        recalculate_tree(state)
        numbers = [state.components[rid].number for rid in state.rootComponents]
        assert numbers == ["1", "2"]

    def test_sorts_roots_reading_order(self):
        state = self._build_state([(200, 0, 50, 50), (0, 0, 50, 50)])
        recalculate_tree(state)
        labels = [state.components[rid].label for rid in state.rootComponents]
        assert labels[0] == "comp_0_0"
        assert labels[1] == "comp_200_0"

    def test_boundary_violation_raises(self):
        parent_id = uuid.uuid4()
        child_id = uuid.uuid4()
        parent = Component(
            id=parent_id,
            number="",
            label="parent",
            childrenIds=[child_id],
            bounds=Bounds(x=0, y=0, w=100, h=100),
        )
        # Child extends beyond parent
        child = Component(
            id=child_id,
            number="",
            label="child",
            parentId=parent_id,
            bounds=Bounds(x=50, y=50, w=100, h=100),
        )
        state = WorkspaceState(
            workspaceId=uuid.uuid4(),
            components={parent_id: parent, child_id: child},
            rootComponents=[parent_id],
        )
        with pytest.raises(BoundaryViolationError):
            recalculate_tree(state, changed_id=child_id)
