"""Tests for annotator.gui.validation (BoundsValidator, CutValidator)."""

import uuid

from annotator.gui.validation import BoundsValidator, CutValidator
from annotator.models import Bounds, Component

# ── BoundsValidator.clamp_val ─────────────────────────────────────────


class TestClampVal:
    def test_within_range(self):
        assert BoundsValidator.clamp_val(5, 0, 10) == 5

    def test_below_lower(self):
        assert BoundsValidator.clamp_val(-5, 0, 10) == 0

    def test_above_upper(self):
        assert BoundsValidator.clamp_val(15, 0, 10) == 10

    def test_at_boundaries(self):
        assert BoundsValidator.clamp_val(0, 0, 10) == 0
        assert BoundsValidator.clamp_val(10, 0, 10) == 10


# ── BoundsValidator.clamp_box_position ────────────────────────────────


class TestClampBoxPosition:
    def test_no_movement(self):
        rx, ry = BoundsValidator.clamp_box_position(
            10, 10, 50, 50, 0, 0, 0, 0, 800, 600
        )
        assert rx == 10
        assert ry == 10

    def test_normal_move(self):
        rx, ry = BoundsValidator.clamp_box_position(
            10, 10, 50, 50, 20, 30, 0, 0, 800, 600
        )
        assert rx == 30
        assert ry == 40

    def test_clamp_left_boundary(self):
        rx, ry = BoundsValidator.clamp_box_position(
            10, 10, 50, 50, -100, 0, 0, 0, 800, 600
        )
        assert rx == 0

    def test_clamp_right_boundary(self):
        rx, ry = BoundsValidator.clamp_box_position(
            700, 10, 50, 50, 200, 0, 0, 0, 800, 600
        )
        assert rx == 750  # 800 - 50

    def test_clamp_top_boundary(self):
        rx, ry = BoundsValidator.clamp_box_position(
            10, 10, 50, 50, 0, -100, 0, 0, 800, 600
        )
        assert ry == 0

    def test_clamp_bottom_boundary(self):
        rx, ry = BoundsValidator.clamp_box_position(
            10, 500, 50, 50, 0, 200, 0, 0, 800, 600
        )
        assert ry == 550  # 600 - 50


# ── BoundsValidator.clamp_resize ──────────────────────────────────────


class TestClampResize:
    def test_resize_east(self):
        rx1, ry1, rx2, ry2 = BoundsValidator.clamp_resize(
            10, 10, 60, 60, 20, 0, "e", 0, 0, 800, 600
        )
        assert rx1 == 10
        assert rx2 == 80  # 60 + 20

    def test_resize_south(self):
        rx1, ry1, rx2, ry2 = BoundsValidator.clamp_resize(
            10, 10, 60, 60, 0, 20, "s", 0, 0, 800, 600
        )
        assert ry1 == 10
        assert ry2 == 80

    def test_resize_west(self):
        rx1, ry1, rx2, ry2 = BoundsValidator.clamp_resize(
            100, 10, 200, 60, -30, 0, "w", 0, 0, 800, 600
        )
        assert rx1 == 70
        assert rx2 == 200

    def test_resize_north(self):
        rx1, ry1, rx2, ry2 = BoundsValidator.clamp_resize(
            10, 100, 60, 200, 0, -30, "n", 0, 0, 800, 600
        )
        assert ry1 == 70
        assert ry2 == 200

    def test_resize_se_corner(self):
        rx1, ry1, rx2, ry2 = BoundsValidator.clamp_resize(
            10, 10, 60, 60, 20, 30, "se", 0, 0, 800, 600
        )
        assert rx1 == 10
        assert ry1 == 10
        assert rx2 == 80
        assert ry2 == 90

    def test_min_size_enforced(self):
        rx1, ry1, rx2, ry2 = BoundsValidator.clamp_resize(
            10, 10, 60, 60, 55, 0, "w", 0, 0, 800, 600, min_size=10
        )
        # rx1 cannot go past rx2 - min_size
        assert rx2 - rx1 >= 10

    def test_boundary_clamp(self):
        rx1, ry1, rx2, ry2 = BoundsValidator.clamp_resize(
            10, 10, 60, 60, 900, 0, "e", 0, 0, 100, 100
        )
        assert rx2 == 100  # Clamped to boundary

    def test_children_union_constraint(self):
        children_union = (20, 20, 50, 50)
        rx1, ry1, rx2, ry2 = BoundsValidator.clamp_resize(
            10, 10, 60, 60, 40, 0, "w", 0, 0, 800, 600,
            children_union=children_union,
        )
        # rx1 cannot exceed children's left edge
        assert rx1 <= 20

    def test_children_union_prevents_shrink_right(self):
        children_union = (20, 20, 55, 55)
        rx1, ry1, rx2, ry2 = BoundsValidator.clamp_resize(
            10, 10, 60, 60, -30, 0, "e", 0, 0, 800, 600,
            children_union=children_union,
        )
        assert rx2 >= 55


# ── CutValidator.get_intersecting_component ───────────────────────────


def _make_comp(x: int, y: int, w: int = 50, h: int = 50) -> Component:
    return Component(
        id=uuid.uuid4(),
        number="",
        label="",
        bounds=Bounds(x=x, y=y, w=w, h=h),
    )


class TestGetIntersectingComponent:
    def test_no_intersection(self):
        components = [_make_comp(0, 100, 50, 50)]
        result = CutValidator.get_intersecting_component(50, components)
        assert result is None

    def test_hit_component(self):
        comp = _make_comp(0, 100, 50, 50)
        result = CutValidator.get_intersecting_component(120, [comp])
        assert result is comp

    def test_at_top_edge(self):
        comp = _make_comp(0, 100, 50, 50)
        result = CutValidator.get_intersecting_component(100, [comp])
        assert result is comp

    def test_at_bottom_edge(self):
        comp = _make_comp(0, 100, 50, 50)
        result = CutValidator.get_intersecting_component(150, [comp])
        assert result is comp

    def test_empty_list(self):
        result = CutValidator.get_intersecting_component(100, [])
        assert result is None


# ── CutValidator.is_valid_position ────────────────────────────────────


class TestIsValidPosition:
    def test_valid_position(self):
        assert CutValidator.is_valid_position(300, 600, [], 20) is True

    def test_too_close_to_top(self):
        assert CutValidator.is_valid_position(10, 600, [], 20) is False

    def test_too_close_to_bottom(self):
        assert CutValidator.is_valid_position(590, 600, [], 20) is False

    def test_too_close_to_existing_cut(self):
        assert CutValidator.is_valid_position(305, 600, [300], 20) is False

    def test_far_from_existing_cut(self):
        assert CutValidator.is_valid_position(350, 600, [300], 20) is True


# ── CutValidator.is_valid_position_for_drag ───────────────────────────


class TestIsValidPositionForDrag:
    def test_excludes_self_index(self):
        # Position 305 is too close to cut at index 0 (300), but we exclude index 0
        assert CutValidator.is_valid_position_for_drag(305, 600, [300], 0, 20) is True

    def test_still_checks_other_cuts(self):
        assert CutValidator.is_valid_position_for_drag(
            305, 600, [300, 310], 0, 20
        ) is False

    def test_boundary_check_still_applies(self):
        assert CutValidator.is_valid_position_for_drag(5, 600, [300], 0, 20) is False
