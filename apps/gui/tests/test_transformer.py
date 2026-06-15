from uuid import uuid4

from gui.domain.transformer import ViewportTransformer


def test_transformer_no_cuts():
    transformer = ViewportTransformer(cut_gap_px=20)
    transformer.update_image_size(1000, 1000)
    transformer.rebuild_segments([])

    # No cuts -> straight coordinate mapping with zoom
    zoom = 1.5
    cx, cy = transformer.to_canvas(100, 200, zoom, [], [])
    assert cx == 150.0
    assert cy == 300.0

    ax, ay = transformer.to_abs(150.0, 300.0, zoom, [], [])
    assert ax == 100
    assert ay == 200


def test_transformer_with_cuts():
    transformer = ViewportTransformer(cut_gap_px=20)
    transformer.update_image_size(1000, 1000)
    # Cut lines at y=300 and y=600
    cut_lines = [300, 600]
    transformer.rebuild_segments(cut_lines)

    # If active cuts are visible (parent_stack is empty)
    parent_stack = []

    # Below first cut: Y=100 -> gap offset is 0
    cx, cy = transformer.to_canvas(100, 100, 2.0, parent_stack, cut_lines)
    assert cx == 200.0
    assert cy == 200.0

    # Between first and second cut: Y=400 -> gap offset should be CUT_GAP_PX (20)
    cx, cy = transformer.to_canvas(100, 400, 2.0, parent_stack, cut_lines)
    assert cx == 200.0
    assert cy == (400 + 20) * 2.0  # 840.0

    # Beyond second cut: Y=700 -> gap offset should be 2 * CUT_GAP_PX (40)
    cx, cy = transformer.to_canvas(100, 700, 2.0, parent_stack, cut_lines)
    assert cx == 200.0
    assert cy == (700 + 40) * 2.0  # 1480.0

    # Inverse mapping
    ax, ay = transformer.to_abs(200.0, 840.0, 2.0, parent_stack, cut_lines)
    assert ax == 100
    assert ay == 400

    ax2, ay2 = transformer.to_abs(200.0, 1480.0, 2.0, parent_stack, cut_lines)
    assert ax2 == 100
    assert ay2 == 700


def test_transformer_parent_stack_keeps_cuts():
    transformer = ViewportTransformer(cut_gap_px=20)
    transformer.update_image_size(1000, 1000)
    cut_lines = [300, 600]
    transformer.rebuild_segments(cut_lines)

    # Drill down active -> cuts remain visible/active
    parent_stack = [uuid4()]

    cx, cy = transformer.to_canvas(100, 400, 2.0, parent_stack, cut_lines)
    assert cx == 200.0
    assert cy == 840.0  # (400 + 20) * 2.0


def test_transformer_get_boundary():
    transformer = ViewportTransformer()

    # Under drill-down bounds constraint
    parent_bounds = (10, 20, 100, 200)
    boundary = transformer.get_boundary(parent_bounds, (1000, 1000))
    assert boundary == (10, 20, 100, 200)

    # Full screen screenshot bounds fallback
    boundary_fallback = transformer.get_boundary(None, (800, 600))
    assert boundary_fallback == (0, 0, 800, 600)

    # Completely uninitialized fallback
    boundary_default = transformer.get_boundary(None, None)
    assert boundary_default == (0, 0, 99999, 99999)


def test_transformer_get_segment_y_bounds():
    transformer = ViewportTransformer(cut_gap_px=20)
    transformer.update_image_size(1000, 1000)
    cut_lines = [300, 600]
    transformer.rebuild_segments(cut_lines)

    parent_stack = []
    boundary = (0, 0, 1000, 1000)

    # Segment 1 bounds (Y < 300)
    seg_top, seg_bot = transformer.get_segment_y_bounds(
        100, parent_stack, cut_lines, boundary
    )
    assert seg_top == 0
    assert seg_bot == 299

    # Segment 2 bounds (300 <= Y < 600)
    seg_top, seg_bot = transformer.get_segment_y_bounds(
        400, parent_stack, cut_lines, boundary
    )
    assert seg_top == 300
    assert seg_bot == 599

    # Segment 3 bounds (Y >= 600)
    seg_top, seg_bot = transformer.get_segment_y_bounds(
        700, parent_stack, cut_lines, boundary
    )
    assert seg_top == 600
    assert seg_bot == 1000

    # Drill down active -> horizontal cuts segment clamping remains active
    seg_top, seg_bot = transformer.get_segment_y_bounds(
        400, [uuid4()], cut_lines, boundary
    )
    assert seg_top == 300
    assert seg_bot == 599
