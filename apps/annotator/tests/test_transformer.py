"""Tests for annotator.gui.transformer (ViewportTransformer coordinate math)."""

from annotator.gui.transformer import CUT_GAP_PX, ViewportTransformer


# ── Construction & Image Size ──────────────────────────────────────────


class TestConstruction:
    def test_default_gap(self):
        t = ViewportTransformer()
        assert t.cut_gap_px == CUT_GAP_PX

    def test_custom_gap(self):
        t = ViewportTransformer(cut_gap_px=40)
        assert t.cut_gap_px == 40

    def test_initial_segments_empty(self):
        t = ViewportTransformer()
        assert t.segments == []

    def test_update_image_size(self):
        t = ViewportTransformer()
        t.update_image_size(800, 600)
        assert t._image_width == 800
        assert t._image_height == 600


# ── rebuild_segments ───────────────────────────────────────────────────


class TestRebuildSegments:
    def test_no_cuts_single_segment(self):
        t = ViewportTransformer()
        t.update_image_size(800, 600)
        t.rebuild_segments([])
        assert len(t.segments) == 1
        assert t.segments[0] == (0, 600, 0)

    def test_zero_image_height_empty(self):
        t = ViewportTransformer()
        t.update_image_size(800, 0)
        t.rebuild_segments([100])
        assert t.segments == []

    def test_single_cut(self):
        t = ViewportTransformer()
        t.update_image_size(800, 600)
        t.rebuild_segments([300])
        assert len(t.segments) == 2
        assert t.segments[0] == (0, 300, 0)
        assert t.segments[1] == (300, 600, CUT_GAP_PX)

    def test_multiple_cuts_sorted(self):
        t = ViewportTransformer()
        t.update_image_size(800, 600)
        # Unsorted input
        t.rebuild_segments([400, 200])
        assert len(t.segments) == 3
        assert t.segments[0] == (0, 200, 0)
        assert t.segments[1] == (200, 400, CUT_GAP_PX)
        assert t.segments[2] == (400, 600, CUT_GAP_PX * 2)

    def test_cut_at_edge_clamped(self):
        t = ViewportTransformer()
        t.update_image_size(800, 600)
        t.rebuild_segments([0, 600])
        # Cut at 0 produces no segment before it; cut at 600 produces no segment after it
        assert len(t.segments) == 1
        assert t.segments[0] == (0, 600, CUT_GAP_PX)

    def test_cut_beyond_image_clamped(self):
        t = ViewportTransformer()
        t.update_image_size(800, 600)
        t.rebuild_segments([900])
        # Clamped to 600 → only (0, 600, 0) since cut equals image height
        assert len(t.segments) == 1
        assert t.segments[0] == (0, 600, 0)


# ── has_active_cuts ───────────────────────────────────────────────────


class TestHasActiveCuts:
    def test_no_cuts(self):
        t = ViewportTransformer()
        assert t.has_active_cuts([], []) is False

    def test_with_cuts(self):
        t = ViewportTransformer()
        assert t.has_active_cuts([], [100, 200]) is True


# ── gap_offset_for_y ──────────────────────────────────────────────────


class TestGapOffsetForY:
    def test_no_segments_returns_zero(self):
        t = ViewportTransformer()
        assert t.gap_offset_for_y(100) == 0

    def test_single_segment_returns_zero(self):
        t = ViewportTransformer()
        t.update_image_size(800, 600)
        t.rebuild_segments([])
        assert t.gap_offset_for_y(300) == 0

    def test_before_first_cut(self):
        t = ViewportTransformer()
        t.update_image_size(800, 600)
        t.rebuild_segments([300])
        assert t.gap_offset_for_y(100) == 0

    def test_after_first_cut(self):
        t = ViewportTransformer()
        t.update_image_size(800, 600)
        t.rebuild_segments([300])
        assert t.gap_offset_for_y(400) == CUT_GAP_PX

    def test_at_cut_boundary(self):
        t = ViewportTransformer()
        t.update_image_size(800, 600)
        t.rebuild_segments([300])
        # y=300 is the start of the second segment
        assert t.gap_offset_for_y(300) == CUT_GAP_PX

    def test_beyond_all_segments(self):
        t = ViewportTransformer()
        t.update_image_size(800, 600)
        t.rebuild_segments([300])
        assert t.gap_offset_for_y(700) == CUT_GAP_PX


# ── gap_offset_inverse ────────────────────────────────────────────────


class TestGapOffsetInverse:
    def test_no_segments_passthrough(self):
        t = ViewportTransformer()
        assert t.gap_offset_inverse(150) == 150

    def test_single_segment_passthrough(self):
        t = ViewportTransformer()
        t.update_image_size(800, 600)
        t.rebuild_segments([])
        assert t.gap_offset_inverse(150) == 150

    def test_before_first_cut(self):
        t = ViewportTransformer()
        t.update_image_size(800, 600)
        t.rebuild_segments([300])
        assert t.gap_offset_inverse(100) == 100

    def test_after_first_cut(self):
        t = ViewportTransformer()
        t.update_image_size(800, 600)
        t.rebuild_segments([300])
        # display_y = 300 + CUT_GAP_PX = 320 maps back to abs_y = 300
        assert t.gap_offset_inverse(300 + CUT_GAP_PX) == 300


# ── to_canvas / to_abs round-trip ─────────────────────────────────────


class TestCoordinateRoundTrip:
    def test_identity_no_zoom_no_pan_no_cuts(self):
        t = ViewportTransformer()
        cx, cy = t.to_canvas(100, 200, 1.0, [], [])
        assert cx == 100.0
        assert cy == 200.0

    def test_zoom_only(self):
        t = ViewportTransformer()
        cx, cy = t.to_canvas(100, 200, 2.0, [], [])
        assert cx == 200.0
        assert cy == 400.0

    def test_pan_offset(self):
        t = ViewportTransformer()
        cx, cy = t.to_canvas(100, 200, 1.0, [], [], pan_offset=(50.0, 30.0))
        assert cx == 150.0
        assert cy == 230.0

    def test_round_trip_no_cuts(self):
        t = ViewportTransformer()
        zoom = 2.5
        pan = (100.0, -50.0)
        cx, cy = t.to_canvas(300, 400, zoom, [], [], pan_offset=pan)
        ax, ay = t.to_abs(cx, cy, zoom, [], [], pan_offset=pan)
        assert ax == 300
        assert ay == 400

    def test_round_trip_with_cuts(self):
        t = ViewportTransformer()
        t.update_image_size(800, 600)
        t.rebuild_segments([200])
        zoom = 1.5
        pan = (10.0, 20.0)
        cuts = [200]
        # Point before cut
        cx, cy = t.to_canvas(100, 100, zoom, [], cuts, pan_offset=pan)
        ax, ay = t.to_abs(cx, cy, zoom, [], cuts, pan_offset=pan)
        assert ax == 100
        assert ay == 100

    def test_to_abs_with_zoom_and_pan(self):
        t = ViewportTransformer()
        zoom = 2.0
        pan = (100.0, 100.0)
        # canvas(300, 500) with zoom 2.0 and pan (100, 100):
        # raw_x = round((300 - 100) / 2.0) = 100
        # raw_y = round((500 - 100) / 2.0) = 200
        ax, ay = t.to_abs(300.0, 500.0, zoom, [], [], pan_offset=pan)
        assert ax == 100
        assert ay == 200


# ── get_boundary ──────────────────────────────────────────────────────


class TestGetBoundary:
    def test_parent_bounds_preferred(self):
        t = ViewportTransformer()
        result = t.get_boundary((10, 20, 300, 400), (800, 600))
        assert result == (10, 20, 300, 400)

    def test_image_size_fallback(self):
        t = ViewportTransformer()
        result = t.get_boundary(None, (800, 600))
        assert result == (0, 0, 800, 600)

    def test_default_fallback(self):
        t = ViewportTransformer()
        result = t.get_boundary(None, None)
        assert result == (0, 0, 99999, 99999)


# ── get_segment_y_bounds ──────────────────────────────────────────────


class TestGetSegmentYBounds:
    def test_no_cuts_returns_boundary(self):
        t = ViewportTransformer()
        result = t.get_segment_y_bounds(100, [], [], (0, 0, 800, 600))
        assert result == (0, 600)

    def test_with_cuts_returns_segment(self):
        t = ViewportTransformer()
        t.update_image_size(800, 600)
        t.rebuild_segments([300])
        result = t.get_segment_y_bounds(100, [], [300], (0, 0, 800, 600))
        # y=100 is in first segment (0, 300)
        assert result[0] == 0
        assert result[1] == 299  # src_end - 1 for non-last segment

    def test_with_cuts_last_segment(self):
        t = ViewportTransformer()
        t.update_image_size(800, 600)
        t.rebuild_segments([300])
        result = t.get_segment_y_bounds(400, [], [300], (0, 0, 800, 600))
        assert result[0] == 300
        assert result[1] == 600  # Last segment keeps its full end
