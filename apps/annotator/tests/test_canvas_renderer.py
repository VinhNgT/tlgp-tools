"""Tests for annotator.gui.canvas_renderer."""

from unittest.mock import Mock

from annotator.gui.canvas_renderer import CanvasRenderer, CanvasRenderState
from annotator.gui.transformer import ViewportTransformer
from annotator.gui.viewport_context import ViewportContext
from PySide6.QtGui import QFont, QPainter


def test_canvas_renderer_paint_annotations_empty():
    """Verify that paint_annotations safely handles an empty state without throwing."""
    transformer = ViewportTransformer()
    renderer = CanvasRenderer(transformer)

    ctx = ViewportContext(
        zoom_factor=1.0,
        parent_stack=(),
        cut_lines=(),
        pan_offset=(0.0, 0.0),
    )

    state = CanvasRenderState(
        viewport_ctx=ctx,
        active_comps=[],
        selected_ids=[],
        active_interaction=None,
        is_dragging=False,
        resize_handle=None,
        show_labels=True,
        temp_rect=None,
        parent_comp=None,
        full_img_width=800,
        children_bounds_union=None,
    )

    # We use a mock QPainter, as instantiating a real one requires a QPaintDevice
    p = Mock(spec=QPainter)
    font = Mock(spec=QFont)

    # Should complete without error
    renderer.paint_annotations(p, state, font)


def test_canvas_renderer_paint_temp_rect_empty():
    """Verify that paint_temp_rect safely handles an empty state without throwing."""
    transformer = ViewportTransformer()
    renderer = CanvasRenderer(transformer)
    p = Mock(spec=QPainter)
    renderer.paint_temp_rect(p, None)


def test_canvas_renderer_paint_parent_mask_empty():
    """Verify that paint_parent_mask safely handles an empty state without throwing."""
    transformer = ViewportTransformer()
    renderer = CanvasRenderer(transformer)
    p = Mock(spec=QPainter)

    ctx = ViewportContext(
        zoom_factor=1.0,
        parent_stack=(),
        cut_lines=(),
        pan_offset=(0.0, 0.0),
    )

    state = CanvasRenderState(
        viewport_ctx=ctx,
        active_comps=[],
        selected_ids=[],
        active_interaction=None,
        is_dragging=False,
        resize_handle=None,
        show_labels=True,
        temp_rect=None,
        parent_comp=None,
        full_img_width=800,
        children_bounds_union=None,
    )

    renderer.paint_parent_mask(p, state, None)
