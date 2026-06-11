"""Tests for horizontal cut segment logic and coordinate transforms."""

import pytest
from unittest.mock import MagicMock, patch
from PIL import Image
from tlgp_annotation_tool.models import AnnotationBox, ScreenSession
from tlgp_annotation_tool.controller import SessionController
from tlgp_annotation_tool.canvas import CUT_GAP_PX


def _box(id: int, x1: int, y1: int, x2: int, y2: int) -> AnnotationBox:
    return AnnotationBox(id=id, label=f"Box {id}", x1=x1, y1=y1, x2=x2, y2=y2)


def _make_controller(cut_lines=None, img_height=1000):
    """Create a controller with a session containing the given cut lines."""
    session = ScreenSession(
        screen_name="Test",
        cut_lines=sorted(cut_lines or []),
    )
    return SessionController(session), img_height


# ── Segment Building ──────────────────────────────────────────────────

class TestBuildSegments:
    """Test the segment building logic for horizontal cut lines."""

    def _build_segments(self, cut_lines, img_height):
        """Simulate _build_segments from canvas without needing a real canvas."""
        cuts = sorted(cut_lines)
        if not cuts:
            return [(0, img_height, 0)]

        segments = []
        prev_y = 0
        for i, cut_y in enumerate(cuts):
            clamped = max(0, min(img_height, cut_y))
            if clamped > prev_y:
                segments.append((prev_y, clamped, i * CUT_GAP_PX))
            prev_y = clamped

        if prev_y < img_height:
            segments.append((prev_y, img_height, len(cuts) * CUT_GAP_PX))

        return segments

    def test_no_cuts(self):
        segs = self._build_segments([], 1000)
        assert segs == [(0, 1000, 0)]

    def test_one_cut(self):
        segs = self._build_segments([500], 1000)
        assert len(segs) == 2
        assert segs[0] == (0, 500, 0)
        assert segs[1] == (500, 1000, CUT_GAP_PX)

    def test_two_cuts(self):
        segs = self._build_segments([300, 700], 1000)
        assert len(segs) == 3
        assert segs[0] == (0, 300, 0)
        assert segs[1] == (300, 700, CUT_GAP_PX)
        assert segs[2] == (700, 1000, 2 * CUT_GAP_PX)

    def test_cuts_at_edges(self):
        """Cuts at 0 or img_height should produce valid segments."""
        segs = self._build_segments([0, 1000], 1000)
        # cut at 0 → clamped to 0, prev_y=0, no segment before it
        # cut at 1000 → clamped to 1000, segment (0, 1000, 0)
        # after loop: prev_y=1000, no trailing segment
        assert len(segs) == 1
        assert segs[0] == (0, 1000, CUT_GAP_PX)

    def test_unsorted_cuts(self):
        """Cuts should be sorted internally."""
        segs = self._build_segments([700, 300], 1000)
        assert len(segs) == 3
        assert segs[0] == (0, 300, 0)
        assert segs[1] == (300, 700, CUT_GAP_PX)
        assert segs[2] == (700, 1000, 2 * CUT_GAP_PX)


# ── Gap Offset ────────────────────────────────────────────────────────

class TestGapOffset:
    """Test gap offset calculation for coordinate mapping."""

    def _gap_offset_for_y(self, segments, abs_y):
        """Simulate _gap_offset_for_y from canvas."""
        if not segments or len(segments) <= 1:
            return 0
        for src_start, src_end, offset in segments:
            if abs_y < src_end:
                return offset
        return segments[-1][2]

    def _gap_offset_inverse(self, segments, display_y):
        """Simulate _gap_offset_inverse from canvas."""
        if not segments or len(segments) <= 1:
            return display_y
        for src_start, src_end, offset in segments:
            disp_start = src_start + offset
            disp_end = src_end + offset
            if display_y < disp_end:
                return display_y - offset
        return display_y - segments[-1][2]

    def test_no_cuts_offset_zero(self):
        segs = [(0, 1000, 0)]
        assert self._gap_offset_for_y(segs, 500) == 0

    def test_one_cut_first_segment(self):
        segs = [(0, 500, 0), (500, 1000, CUT_GAP_PX)]
        assert self._gap_offset_for_y(segs, 250) == 0

    def test_one_cut_second_segment(self):
        segs = [(0, 500, 0), (500, 1000, CUT_GAP_PX)]
        assert self._gap_offset_for_y(segs, 750) == CUT_GAP_PX

    def test_round_trip_first_segment(self):
        segs = [(0, 500, 0), (500, 1000, CUT_GAP_PX)]
        abs_y = 250
        display_y = abs_y + self._gap_offset_for_y(segs, abs_y)
        recovered = self._gap_offset_inverse(segs, display_y)
        assert recovered == abs_y

    def test_round_trip_second_segment(self):
        segs = [(0, 500, 0), (500, 1000, CUT_GAP_PX)]
        abs_y = 750
        display_y = abs_y + self._gap_offset_for_y(segs, abs_y)
        recovered = self._gap_offset_inverse(segs, display_y)
        assert recovered == abs_y

    def test_round_trip_three_segments(self):
        segs = [(0, 300, 0), (300, 700, CUT_GAP_PX), (700, 1000, 2 * CUT_GAP_PX)]
        for abs_y in [0, 150, 299, 300, 500, 699, 700, 850, 999]:
            display_y = abs_y + self._gap_offset_for_y(segs, abs_y)
            recovered = self._gap_offset_inverse(segs, display_y)
            assert recovered == abs_y, f"Round-trip failed for abs_y={abs_y}"


# ── Box-to-Segment Assignment ─────────────────────────────────────────

class TestBoxSegmentAssignment:
    """Test that boxes are correctly assigned to segments by vertical center."""

    def _assign_box_to_segment(self, box, boundaries):
        """Determine which segment a box belongs to based on its vertical center."""
        center_y = (box.top + box.bottom) / 2
        for i in range(len(boundaries) - 1):
            if boundaries[i] <= center_y < boundaries[i + 1]:
                return i
        return len(boundaries) - 2  # last segment

    def test_box_in_first_segment(self):
        box = _box(1, 0, 100, 100, 200)  # center_y = 150
        assert self._assign_box_to_segment(box, [0, 500, 1000]) == 0

    def test_box_in_second_segment(self):
        box = _box(1, 0, 600, 100, 800)  # center_y = 700
        assert self._assign_box_to_segment(box, [0, 500, 1000]) == 1

    def test_box_crossing_cut_assigned_by_center(self):
        """A box crossing a cut boundary is assigned based on its center."""
        box = _box(1, 0, 400, 100, 600)  # center_y = 500
        # center is at exactly 500, which is the boundary → goes to segment 1
        assert self._assign_box_to_segment(box, [0, 500, 1000]) == 1

    def test_box_center_just_above_cut(self):
        box = _box(1, 0, 390, 100, 500)  # center_y = 445
        assert self._assign_box_to_segment(box, [0, 500, 1000]) == 0

    def test_empty_segment(self):
        """No boxes in a segment is valid."""
        boxes = [_box(1, 0, 0, 100, 100)]  # all in first segment
        boundaries = [0, 500, 1000]
        # Segment 1 has no boxes
        seg1_boxes = [b for b in boxes if 500 <= (b.top + b.bottom) / 2 < 1000]
        assert seg1_boxes == []


# ── Controller Cut Lines ──────────────────────────────────────────────

class TestControllerCutLines:
    def test_set_and_get(self):
        ctrl, _ = _make_controller()
        ctrl.set_cut_lines([700, 300])
        assert ctrl.get_cut_lines() == [300, 700]

    def test_set_empty(self):
        ctrl, _ = _make_controller(cut_lines=[500])
        ctrl.set_cut_lines([])
        assert ctrl.get_cut_lines() == []

    def test_notifies_cuts_change(self):
        ctrl, _ = _make_controller()
        callback = MagicMock()
        ctrl.subscribe("cuts_change", callback)
        ctrl.set_cut_lines([500])
        callback.assert_called_once()

    def test_undo_restores_cuts(self):
        ctrl, _ = _make_controller()
        ctrl.set_cut_lines([500])
        assert ctrl.get_cut_lines() == [500]
        ctrl.undo()
        assert ctrl.get_cut_lines() == []

    def test_redo_restores_cuts(self):
        ctrl, _ = _make_controller()
        ctrl.set_cut_lines([500])
        ctrl.undo()
        assert ctrl.get_cut_lines() == []
        ctrl.redo()
        assert ctrl.get_cut_lines() == [500]
