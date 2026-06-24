"""Tests for annotator.workspace.ordering (sort_components_reading_order, recalculate_tree)."""

import uuid

import pytest
from annotator.models import Bounds, Component, WorkspaceState
from annotator.workspace.errors import BoundaryViolationError
from annotator.workspace.ordering import (
    _build_row_groups,
    _compute_overlap_ratio,
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


# ── Overlap Ratio ──────────────────────────────────────────────────────


class TestOverlapRatio:
    def test_no_overlap(self):
        a = _make_comp(0, 0, 50, 50)
        b = _make_comp(0, 100, 50, 50)
        assert _compute_overlap_ratio(a, b) == 0.0

    def test_full_overlap(self):
        a = _make_comp(0, 0, 50, 50)
        b = _make_comp(100, 0, 50, 50)
        assert _compute_overlap_ratio(a, b) == 1.0

    def test_partial_overlap(self):
        a = _make_comp(0, 0, 50, 100)
        b = _make_comp(0, 50, 50, 100)
        ratio = _compute_overlap_ratio(a, b)
        assert 0.0 < ratio < 1.0


# ── Row Groups ─────────────────────────────────────────────────────────


class TestRowGroups:
    def test_empty_list(self):
        assert _build_row_groups([]) == []

    def test_single_component(self):
        comp = _make_comp(0, 0)
        groups = _build_row_groups([comp])
        assert len(groups) == 1
        assert groups[0] == [comp]

    def test_same_row_grouped(self):
        a = _make_comp(0, 0, 50, 50)
        b = _make_comp(100, 0, 50, 50)
        groups = _build_row_groups([a, b])
        assert len(groups) == 1
        assert len(groups[0]) == 2

    def test_different_rows_separated(self):
        a = _make_comp(0, 0, 50, 50)
        b = _make_comp(0, 200, 50, 50)
        groups = _build_row_groups([a, b])
        assert len(groups) == 2


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
