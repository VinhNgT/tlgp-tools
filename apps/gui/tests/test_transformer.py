from uuid import uuid4

from gui.views.transformer import ViewportTransformer


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


def test_transformer_parent_stack_disables_cuts():
    transformer = ViewportTransformer(cut_gap_px=20)
    transformer.update_image_size(1000, 1000)
    cut_lines = [300, 600]
    transformer.rebuild_segments(cut_lines)

    # Drill down active -> cuts ignored visually
    parent_stack = [uuid4()]

    cx, cy = transformer.to_canvas(100, 400, 2.0, parent_stack, cut_lines)
    assert cx == 200.0
    assert cy == 800.0  # straight zoom 400 * 2.0
