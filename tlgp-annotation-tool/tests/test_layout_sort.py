"""Tests for layout_sort — geometry-aware auto-numbering algorithm."""

import pytest
from tlgp_annotation_tool.models import AnnotationBox
from tlgp_annotation_tool.layout_sort import (
    _compute_overlap_ratio,
    sort_boxes_reading_order,
    sort_and_renumber_recursive,
)


def _box(id: int, x1: int, y1: int, x2: int, y2: int, children=None) -> AnnotationBox:
    """Helper to create a box with minimal boilerplate."""
    return AnnotationBox(
        id=id, label=f"Box {id}",
        x1=x1, y1=y1, x2=x2, y2=y2,
        children=children or [],
    )


# ── Overlap Ratio ─────────────────────────────────────────────────────

class TestOverlapRatio:
    def test_no_overlap(self):
        a = _box(1, 0, 0, 100, 50)
        b = _box(2, 0, 60, 100, 110)
        assert _compute_overlap_ratio(a, b) == 0.0

    def test_full_overlap(self):
        a = _box(1, 0, 0, 100, 100)
        b = _box(2, 50, 0, 150, 100)
        assert _compute_overlap_ratio(a, b) == 1.0

    def test_partial_overlap(self):
        a = _box(1, 0, 0, 100, 100)   # height=100
        b = _box(2, 50, 50, 150, 150)  # height=100, overlap=50
        ratio = _compute_overlap_ratio(a, b)
        assert ratio == pytest.approx(0.5)

    def test_mixed_height(self):
        tall = _box(1, 0, 0, 100, 200)   # height=200
        short = _box(2, 120, 50, 200, 100)  # height=50, overlap=50
        ratio = _compute_overlap_ratio(tall, short)
        # overlap=50, min_height=50, ratio=1.0
        assert ratio == pytest.approx(1.0)

    def test_zero_height_box(self):
        a = _box(1, 0, 50, 100, 50)  # height=0
        b = _box(2, 0, 0, 100, 100)
        assert _compute_overlap_ratio(a, b) == 0.0


# ── Edge Cases ────────────────────────────────────────────────────────

class TestEdgeCases:
    def test_empty_list(self):
        result = sort_boxes_reading_order([])
        assert result == []

    def test_single_box(self):
        box = _box(1, 10, 20, 30, 40)
        result = sort_boxes_reading_order([box])
        assert result == [box]


# ── Row Detection ──────────────────────────────────────────────────────

class TestSingleRow:
    def test_boxes_sorted_left_to_right(self):
        """Multiple boxes at the same Y should be sorted left-to-right."""
        b1 = _box(3, 200, 0, 300, 50)
        b2 = _box(1, 0, 0, 100, 50)
        b3 = _box(2, 100, 0, 200, 50)
        result = sort_boxes_reading_order([b1, b2, b3])
        assert [b.id for b in result] == [1, 2, 3]

    def test_slight_y_offset_same_row(self):
        """Boxes with slight Y differences but significant overlap → same row."""
        b1 = _box(1, 0, 0, 100, 80)
        b2 = _box(2, 120, 10, 220, 90)  # 10px offset, 70px overlap, min_height=80, ratio=0.875
        b3 = _box(3, 240, 5, 340, 85)
        result = sort_boxes_reading_order([b3, b1, b2])
        assert [b.id for b in result] == [1, 2, 3]


class TestSingleColumn:
    def test_boxes_sorted_top_to_bottom(self):
        """Multiple boxes at similar X should be sorted top-to-bottom."""
        b1 = _box(1, 0, 200, 100, 300)
        b2 = _box(2, 0, 0, 100, 80)
        b3 = _box(3, 0, 100, 100, 180)
        result = sort_boxes_reading_order([b1, b2, b3])
        assert [b.id for b in result] == [2, 3, 1]


class TestGridLayout:
    def test_2x2_grid_row_major(self):
        """2×2 grid → row-major order: top-left, top-right, bottom-left, bottom-right."""
        tl = _box(1, 0, 0, 100, 80)
        tr = _box(2, 150, 0, 250, 80)
        bl = _box(3, 0, 120, 100, 200)
        br = _box(4, 150, 120, 250, 200)
        result = sort_boxes_reading_order([br, tl, bl, tr])
        assert [b.id for b in result] == [1, 2, 3, 4]

    def test_3x2_grid(self):
        """3 columns × 2 rows → 1,2,3 (top) then 4,5,6 (bottom)."""
        boxes = [
            _box(1, 0, 0, 80, 50),
            _box(2, 100, 0, 180, 50),
            _box(3, 200, 0, 280, 50),
            _box(4, 0, 80, 80, 130),
            _box(5, 100, 80, 180, 130),
            _box(6, 200, 80, 280, 130),
        ]
        import random
        shuffled = list(boxes)
        random.shuffle(shuffled)
        result = sort_boxes_reading_order(shuffled)
        assert [b.id for b in result] == [1, 2, 3, 4, 5, 6]


class TestMixedHeightRow:
    def test_tall_and_short_same_row(self):
        """A tall box and short boxes at the same visual position → one row."""
        tall = _box(1, 0, 0, 100, 200)      # height=200
        short1 = _box(2, 120, 50, 200, 100)  # height=50, overlap with tall = 50, ratio = 50/50 = 1.0
        short2 = _box(3, 220, 60, 300, 110)  # height=50, overlap with tall = 50, ratio = 50/50 = 1.0
        result = sort_boxes_reading_order([short2, tall, short1])
        assert [b.id for b in result] == [1, 2, 3]


class TestTransitiveOverlap:
    def test_bridged_by_tall_box(self):
        """A↔B↔C where B bridges A and C. A and C don't directly overlap."""
        a = _box(1, 0, 0, 80, 40)      # top section, height=40
        b = _box(2, 100, 0, 180, 200)  # tall, spans full range, height=200
        c = _box(3, 200, 160, 280, 200) # bottom section, height=40

        # A↔B: overlap = min(40,200) - max(0,0) = 40, min_height=40, ratio=1.0 ✓
        # B↔C: overlap = min(200,200) - max(0,160) = 40, min_height=40, ratio=1.0 ✓
        # A↔C: overlap = min(40,200) - max(0,160) = -120, ratio=0.0 ✗
        # But connected via B → all one row
        result = sort_boxes_reading_order([c, b, a])
        assert [b.id for b in result] == [1, 2, 3]


class TestNearMissSeparateRows:
    def test_close_but_no_overlap(self):
        """Two rows with a small gap and no vertical overlap → separate rows."""
        top1 = _box(1, 0, 0, 100, 50)
        top2 = _box(2, 120, 0, 220, 50)
        bot1 = _box(3, 0, 55, 100, 105)  # gap of 5px, no overlap with top row
        bot2 = _box(4, 120, 55, 220, 105)
        result = sort_boxes_reading_order([bot2, top1, bot1, top2])
        assert [b.id for b in result] == [1, 2, 3, 4]


# ── Recursive Numbering ───────────────────────────────────────────────

class TestNestedChildren:
    def test_children_renumbered(self):
        """Children within a parent are sorted and renumbered recursively."""
        child_a = _box(99, 200, 10, 280, 50)  # right
        child_b = _box(98, 10, 10, 90, 50)    # left

        parent = _box(1, 0, 0, 300, 100, children=[child_a, child_b])

        sort_and_renumber_recursive([parent])

        assert parent.id == 1
        assert parent.children[0].id == 1  # child_b (left) → renumbered to 1
        assert parent.children[1].id == 2  # child_a (right) → renumbered to 2
        assert parent.children[0] is child_b
        assert parent.children[1] is child_a

    def test_deep_nesting(self):
        """Three levels of nesting: root → parent → grandchildren."""
        gc1 = _box(99, 50, 50, 80, 70)   # right grandchild
        gc2 = _box(98, 10, 50, 40, 70)   # left grandchild

        child = _box(1, 0, 0, 100, 100, children=[gc1, gc2])
        root_box = _box(1, 0, 0, 500, 500, children=[child])

        boxes = [root_box]
        sort_and_renumber_recursive(boxes)

        assert root_box.children[0].children[0].id == 1  # gc2 (left)
        assert root_box.children[0].children[1].id == 2  # gc1 (right)


# ── Scale Consistency ──────────────────────────────────────────────────

class TestScaleConsistency:
    def test_same_layout_different_scale(self):
        """Same proportional layout at 1× and 2× produces identical ordering.

        This mirrors the font/border scaling test: if you uniformly scale
        all boxes, the overlap ratios (and thus row grouping) are identical.
        """
        # 1× scale: 2×2 grid in a 1000px space
        boxes_1x = [
            _box(1, 0, 0, 100, 80),
            _box(2, 150, 5, 250, 85),
            _box(3, 0, 120, 100, 200),
            _box(4, 150, 125, 250, 205),
        ]
        order_1x = [b.id for b in sort_boxes_reading_order(boxes_1x)]

        # 2× scale: same layout doubled
        boxes_2x = [
            _box(1, 0, 0, 200, 160),
            _box(2, 300, 10, 500, 170),
            _box(3, 0, 240, 200, 400),
            _box(4, 300, 250, 500, 410),
        ]
        order_2x = [b.id for b in sort_boxes_reading_order(boxes_2x)]

        assert order_1x == order_2x

    def test_depth_consistency(self):
        """Same relative layout at root and inside a small parent → identical ordering.

        At root (1000px image), boxes are large.
        Inside a 200px parent, same proportional layout, boxes are small.
        The overlap ratios should produce the same grouping.
        """
        # Root level: large boxes in a 2×2 grid
        root_boxes = [
            _box(1, 0, 0, 200, 150),
            _box(2, 300, 10, 500, 160),
            _box(3, 0, 250, 200, 400),
            _box(4, 300, 260, 500, 410),
        ]
        order_root = [b.id for b in sort_boxes_reading_order(root_boxes)]

        # Sub-level: same proportional layout inside a 200px-wide parent
        # (all coords scaled by 0.2)
        sub_boxes = [
            _box(1, 0, 0, 40, 30),
            _box(2, 60, 2, 100, 32),
            _box(3, 0, 50, 40, 80),
            _box(4, 60, 52, 100, 82),
        ]
        order_sub = [b.id for b in sort_boxes_reading_order(sub_boxes)]

        assert order_root == order_sub
