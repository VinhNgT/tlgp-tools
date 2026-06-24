"""Tests for annotator.gui.viewport_calculator."""

import uuid

import pytest
from annotator.gui.transformer import ViewportTransformer
from annotator.gui.viewport_calculator import ViewportCalculator
from annotator.gui.viewport_context import ViewportContext
from annotator.models import Bounds, Component, Style


def test_calculate_fit_image_only():
    """Verify calculating zoom/pan for an image with no target component."""
    transformer = ViewportTransformer()
    ctx = ViewportContext(1.0, (), (), (0.0, 0.0))

    vw, vh = 800, 600
    img_w, img_h = 1600, 1200

    zoom, pad_x, pad_y = ViewportCalculator.calculate_fit(
        vw, vh, None, img_w, img_h, ctx, transformer
    )

    # Needs to fit 1600x1200 into 760x560 (with 40px margins)
    # zoom_x = 760/1600 = 0.475
    # zoom_y = 560/1200 = 0.466... -> Min is ~0.466
    assert 0.46 < zoom < 0.47

    # Target rect should be centered
    expected_w = img_w * zoom
    expected_h = img_h * zoom
    assert pad_x == pytest.approx((vw - expected_w) / 2)
    assert pad_y == pytest.approx((vh - expected_h) / 2)


def test_calculate_fit_target_component():
    """Verify calculating zoom/pan for a specific target component."""
    transformer = ViewportTransformer()
    ctx = ViewportContext(1.0, (), (), (0.0, 0.0))

    vw, vh = 800, 600
    comp = Component(
        id=uuid.uuid4(),
        number="1",
        label="Test",
        bounds=Bounds(x=100, y=100, w=200, h=100),
        style=Style(),
    )

    zoom, pad_x, pad_y = ViewportCalculator.calculate_fit(
        vw, vh, comp, 1600, 1200, ctx, transformer
    )

    # Needs to fit 200x100 into 680x480 (with 120px margins)
    # zoom_x = 680/200 = 3.4
    # zoom_y = 480/100 = 4.8
    # Caps at 4.0
    assert zoom == pytest.approx(3.4)
