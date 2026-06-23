"""Tests for annotator.rendering (font loading, text dimensions, paint_annotations)."""

import uuid

from annotator.models import Bounds, Component
from annotator.rendering import (
    compute_border_widths,
    compute_pill_font_size,
    compute_pill_padding,
    get_font,
    get_pill_coords,
    get_text_dimensions,
    paint_annotations,
)
from PIL import Image, ImageDraw

# ── Font Loading ───────────────────────────────────────────────────────


class TestGetFont:
    def test_returns_font_object(self):
        font = get_font(20)
        assert font is not None

    def test_caching_returns_same_object(self):
        f1 = get_font(16)
        f2 = get_font(16)
        assert f1 is f2

    def test_different_sizes_return_different_objects(self):
        f1 = get_font(12)
        f2 = get_font(24)
        assert f1 is not f2


# ── Text Dimensions ───────────────────────────────────────────────────


class TestGetTextDimensions:
    def test_with_draw_context(self):
        img = Image.new("RGB", (100, 100))
        draw = ImageDraw.Draw(img)
        font = get_font(20)
        w, h, top = get_text_dimensions(draw, "Test", font)
        assert w > 0
        assert h > 0

    def test_without_draw_context(self):
        """Callers like the Tkinter canvas pass None for draw."""
        font = get_font(20)
        w, h, top = get_text_dimensions(None, "Test", font)
        assert w > 0
        assert h > 0

    def test_empty_string(self):
        font = get_font(20)
        w, h, top = get_text_dimensions(None, "", font)
        assert w == 0


# ── Pill & Border Computation ─────────────────────────────────────────


class TestPillComputation:
    def test_pill_font_size_at_root(self):
        size = compute_pill_font_size(None, 800)
        assert size > 0

    def test_pill_font_size_with_parent(self):
        parent = Component(
            id=uuid.uuid4(),
            number="1",
            label="P",
            bounds=Bounds(x=0, y=0, w=400, h=400),
        )
        size = compute_pill_font_size(parent, 800)
        assert size > 0
        # Nested level should have smaller or equal font
        root_size = compute_pill_font_size(None, 800)
        assert size <= root_size

    def test_pill_padding(self):
        px, py = compute_pill_padding(20)
        assert px > 0
        assert py > 0

    def test_border_widths(self):
        bw, pw = compute_border_widths(None, 800)
        assert bw > 0
        assert pw > 0


# ── Pill Coordinates ──────────────────────────────────────────────────


class TestGetPillCoords:
    def test_top_left(self):
        x, y = get_pill_coords(10, 20, 110, 120, 30, 15, "top_left")
        assert x == 10
        assert y == 20

    def test_top_right(self):
        x, y = get_pill_coords(10, 20, 110, 120, 30, 15, "top_right")
        assert x == 110 - 30
        assert y == 20

    def test_bottom_left(self):
        x, y = get_pill_coords(10, 20, 110, 120, 30, 15, "bottom_left")
        assert x == 10
        assert y == 120 - 15

    def test_bottom_right(self):
        x, y = get_pill_coords(10, 20, 110, 120, 30, 15, "bottom_right")
        assert x == 110 - 30
        assert y == 120 - 15

    def test_unknown_defaults_to_top_left(self):
        x, y = get_pill_coords(10, 20, 110, 120, 30, 15, "invalid")
        assert x == 10
        assert y == 20


# ── paint_annotations ─────────────────────────────────────────────────


class TestPaintAnnotations:
    def _make_children(self, parent_bounds: Bounds) -> list[Component]:
        """Create two child components within parent bounds."""
        return [
            Component(
                id=uuid.uuid4(),
                number="1",
                label="A",
                bounds=Bounds(
                    x=parent_bounds.x + 5,
                    y=parent_bounds.y + 5,
                    w=40,
                    h=40,
                ),
            ),
            Component(
                id=uuid.uuid4(),
                number="2",
                label="B",
                bounds=Bounds(
                    x=parent_bounds.x + 55,
                    y=parent_bounds.y + 5,
                    w=40,
                    h=40,
                ),
            ),
        ]

    def test_paint_returns_image(self):
        img = Image.new("RGB", (200, 200), color=(255, 255, 255))
        children = self._make_children(Bounds(x=0, y=0, w=200, h=200))
        result = paint_annotations(img, children, 0, 0, None, 200)
        assert isinstance(result, Image.Image)
        assert result.size == img.size

    def test_paint_with_no_children_returns_copy(self):
        img = Image.new("RGB", (200, 200), color=(255, 255, 255))
        result = paint_annotations(img, [], 0, 0, None, 200)
        assert isinstance(result, Image.Image)

    def test_paint_with_parent_context(self):
        parent = Component(
            id=uuid.uuid4(),
            number="1",
            label="Parent",
            bounds=Bounds(x=0, y=0, w=200, h=200),
        )
        img = Image.new("RGB", (200, 200), color=(255, 255, 255))
        children = self._make_children(parent.bounds)
        result = paint_annotations(img, children, 0, 0, parent, 400)
        assert isinstance(result, Image.Image)
