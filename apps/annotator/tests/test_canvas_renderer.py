"""Tests for annotator.gui.canvas_renderer."""

import uuid
from unittest.mock import Mock

from annotator.gui.canvas import TempRect
from annotator.gui.canvas_renderer import CanvasRenderer, CanvasRenderState
from annotator.gui.transformer import ViewportTransformer
from annotator.gui.viewport_context import ViewportContext
from annotator.models import Bounds, Component
from PySide6.QtCore import QRectF
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


def test_canvas_renderer_paint_annotations_borders_inside(qapp):
    """Verify that paint_annotations draws borders fully inside by insetting coordinates."""
    transformer = ViewportTransformer()
    renderer = CanvasRenderer(transformer)

    ctx = ViewportContext(
        zoom_factor=1.0,
        parent_stack=(),
        cut_lines=(),
        pan_offset=(0.0, 0.0),
    )

    comp = Component(
        id=uuid.uuid4(),
        number="1",
        label="TestBox",
        bounds=Bounds(x=10, y=20, w=100, h=50),
    )

    state = CanvasRenderState(
        viewport_ctx=ctx,
        active_comps=[comp],
        selected_ids=[],
        active_interaction=None,
        is_dragging=False,
        resize_handle=None,
        show_labels=False,
        temp_rect=None,
        parent_comp=None,
        full_img_width=800,
        children_bounds_union=None,
    )

    p = Mock(spec=QPainter)
    font = QFont()

    renderer.paint_annotations(p, state, font)

    # Let's inspect the drawRect calls on QPainter mock.
    # The border width 'lw' should be 5 (computed via scale=1.0, BASE_BORDER=5).
    # Since lw=5, half_lw=2.5.
    # Box border should be inset:
    # cx1 + 2.5 = 12.5
    # cy1 + 2.5 = 22.5
    # cx2 - cx1 - 5 = 95
    # cy2 - cy1 - 5 = 45
    # The actual call should match QRectF(12.5, 22.5, 95.0, 45.0).
    draw_rect_calls = [call[0][0] for call in p.drawRect.call_args_list]
    assert any(
        isinstance(arg, QRectF)
        and abs(arg.x() - 12.5) < 1e-5
        and abs(arg.y() - 22.5) < 1e-5
        and abs(arg.width() - 95.0) < 1e-5
        and abs(arg.height() - 45.0) < 1e-5
        for arg in draw_rect_calls
    )


def test_canvas_renderer_paint_temp_rect_borders_inside(qapp):
    """Verify that paint_temp_rect draws temporary marquee borders fully inside by insetting coordinates."""
    transformer = ViewportTransformer()
    renderer = CanvasRenderer(transformer)
    p = Mock(spec=QPainter)

    # Let's create a temporary rectangle with width=4
    temp_rect = TempRect(x1=10, y1=20, x2=110, y2=70, width=4)
    renderer.paint_temp_rect(p, temp_rect)

    # w=4, half_w=2.0.
    # Inset is:
    # x1 + 2.0 = 12.0
    # y1 + 2.0 = 22.0
    # x2 - x1 - 4 = 96.0
    # y2 - y1 - 4 = 46.0
    draw_rect_calls = [call[0][0] for call in p.drawRect.call_args_list]
    assert any(
        isinstance(arg, QRectF)
        and abs(arg.x() - 12.0) < 1e-5
        and abs(arg.y() - 22.0) < 1e-5
        and abs(arg.width() - 96.0) < 1e-5
        and abs(arg.height() - 46.0) < 1e-5
        for arg in draw_rect_calls
    )


def test_canvas_renderer_paint_selected_annotations_handles_centered(qapp):
    """Verify that selection handles are painted centered on the visual border (inset coordinates)."""
    transformer = ViewportTransformer()
    renderer = CanvasRenderer(transformer)

    ctx = ViewportContext(
        zoom_factor=1.0,
        parent_stack=(),
        cut_lines=(),
        pan_offset=(0.0, 0.0),
    )

    comp_id = uuid.uuid4()
    comp = Component(
        id=comp_id,
        number="1",
        label="TestBox",
        bounds=Bounds(x=10, y=20, w=100, h=50),
    )

    state = CanvasRenderState(
        viewport_ctx=ctx,
        active_comps=[comp],
        selected_ids=[comp_id],
        active_interaction=None,
        is_dragging=False,
        resize_handle=None,
        show_labels=False,
        temp_rect=None,
        parent_comp=None,
        full_img_width=800,
        children_bounds_union=None,
    )

    p = Mock(spec=QPainter)
    font = QFont()

    renderer.paint_annotations(p, state, font)

    # With comp selected: lw = border_width + 1 = 6. half_lw = 3.0.
    # The visual borders are at:
    # vx1 = 10 + 3.0 = 13.0
    # vy1 = 20 + 3.0 = 23.0
    # vx2 = 110 - 3.0 = 107.0
    # vy2 = 70 - 3.0 = 67.0
    # Selection handles should be centered exactly at these visual coordinates.
    # The handles list includes: (vx1, vy1), (mx, vy1), (vx2, vy1), (vx1, my), (vx2, my), (vx1, vy2), (mx, vy2), (vx2, vy2).
    # Specifically, top-left handle is centered at (13.0, 23.0) with size 10x10.
    # So drawRect is called with QRectF(13 - 5, 23 - 5, 10, 10) = QRectF(8, 18, 10, 10).
    # Bottom-right handle: QRectF(107 - 5, 67 - 5, 10, 10) = QRectF(102, 62, 10, 10).
    draw_rect_calls = [call[0][0] for call in p.drawRect.call_args_list]

    # Check top-left handle
    assert any(
        isinstance(arg, QRectF)
        and abs(arg.x() - 8.0) < 1e-5
        and abs(arg.y() - 18.0) < 1e-5
        and abs(arg.width() - 10.0) < 1e-5
        and abs(arg.height() - 10.0) < 1e-5
        for arg in draw_rect_calls
    )
    # Check bottom-right handle
    assert any(
        isinstance(arg, QRectF)
        and abs(arg.x() - 102.0) < 1e-5
        and abs(arg.y() - 62.0) < 1e-5
        and abs(arg.width() - 10.0) < 1e-5
        and abs(arg.height() - 10.0) < 1e-5
        for arg in draw_rect_calls
    )


def test_canvas_renderer_paint_child_bounds_inset(qapp):
    """Verify that the child bounds union overlay is inset correctly."""
    transformer = ViewportTransformer()
    renderer = CanvasRenderer(transformer)

    ctx = ViewportContext(
        zoom_factor=1.0,
        parent_stack=(),
        cut_lines=(),
        pan_offset=(0.0, 0.0),
    )

    comp_id = uuid.uuid4()
    comp = Component(
        id=comp_id,
        number="1",
        label="TestBox",
        bounds=Bounds(x=10, y=20, w=100, h=50),
    )

    state = CanvasRenderState(
        viewport_ctx=ctx,
        active_comps=[comp],
        selected_ids=[comp_id],
        active_interaction=None,
        is_dragging=True,
        resize_handle="se",
        show_labels=False,
        temp_rect=None,
        parent_comp=None,
        full_img_width=800,
        children_bounds_union=(20, 30, 80, 60),  # child union boundaries
    )

    p = Mock(spec=QPainter)
    font = QFont()

    renderer.paint_annotations(p, state, font)

    # Let's verify the child bounds drawing.
    # The bounds union is (20, 30, 80, 60), which transforms directly to (20, 30, 80, 60) on canvas.
    # border_width = 5, lw = 6, inset = 6.0.
    # max_w_inset = max(0.0, (60 - 2.0)/2.0) = 29.0
    # max_h_inset = max(0.0, (30 - 2.0)/2.0) = 14.0
    # actual_inset = min(6.0, 29.0, 14.0) = 6.0
    # The child bounds rect is drawn at:
    # x1 + actual_inset + 1.0 = 20 + 6.0 + 1.0 = 27.0
    # y1 + actual_inset + 1.0 = 30 + 6.0 + 1.0 = 37.0
    # w = (80 - 20) - 2 * 6.0 - 2.0 = 60 - 12 - 2 = 46.0
    # h = (60 - 30) - 2 * 6.0 - 2.0 = 30 - 12 - 2 = 16.0
    # Expected call: QRectF(27.0, 37.0, 46.0, 16.0).
    draw_rect_calls = [call[0][0] for call in p.drawRect.call_args_list]
    assert any(
        isinstance(arg, QRectF)
        and abs(arg.x() - 27.0) < 1e-5
        and abs(arg.y() - 37.0) < 1e-5
        and abs(arg.width() - 46.0) < 1e-5
        and abs(arg.height() - 16.0) < 1e-5
        for arg in draw_rect_calls
    )
