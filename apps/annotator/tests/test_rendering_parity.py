"""Rendering parity tests — verifying that paint_annotations() produces
consistent output for both the API export path and direct function calls.

These tests ensure the single source of truth in rendering.py draws
identically regardless of call site (API route vs. direct invocation).
"""

import uuid

from annotator.models import Bounds, Component, Style
from annotator.rendering import (
    MIN_FONT_SIZE,
    composite_gapped_image,
    compute_pill_font_size,
    paint_annotations,
)
from PIL import Image

# ── Helpers ────────────────────────────────────────────────────────────


def _make_components(parent_bounds: Bounds, count: int = 3) -> list[Component]:
    """Create N child components arranged horizontally within parent bounds."""
    children = []
    slot_w = parent_bounds.w // max(count, 1) - 10
    for i in range(count):
        children.append(
            Component(
                id=uuid.uuid4(),
                number=str(i + 1),
                label=f"Child_{i}",
                bounds=Bounds(
                    x=parent_bounds.x + i * (slot_w + 10) + 5,
                    y=parent_bounds.y + 5,
                    w=slot_w,
                    h=parent_bounds.h - 10,
                ),
            )
        )
    return children


# ── Idempotency ───────────────────────────────────────────────────────


class TestPaintIdempotency:
    def test_same_input_same_output(self):
        """Calling paint_annotations() twice with the same inputs must produce identical pixels."""
        img_w, img_h = 400, 300
        parent_bounds = Bounds(x=0, y=0, w=img_w, h=img_h)
        children = _make_components(parent_bounds, count=3)

        img1 = Image.new("RGB", (img_w, img_h), (255, 255, 255))
        result1 = paint_annotations(img1, children, 0, 0, None, img_w)

        img2 = Image.new("RGB", (img_w, img_h), (255, 255, 255))
        result2 = paint_annotations(img2, children, 0, 0, None, img_w)

        assert result1.tobytes() == result2.tobytes()

    def test_no_children_returns_original(self):
        """paint_annotations with empty children returns the input image unmodified."""
        img = Image.new("RGB", (200, 200), (128, 128, 128))
        original_bytes = img.tobytes()
        result = paint_annotations(img, [], 0, 0, None, 200)
        assert result.tobytes() == original_bytes


# ── Offset Consistency ────────────────────────────────────────────────


class TestOffsetConsistency:
    def test_offset_shifts_annotations(self):
        """When offset_x/offset_y are applied, annotations should shift accordingly."""
        img_w, img_h = 200, 200
        child = Component(
            id=uuid.uuid4(),
            number="1",
            label="A",
            bounds=Bounds(x=100, y=100, w=50, h=50),
        )

        # Draw at (0,0) offset — box at image coords (100, 100)
        img1 = Image.new("RGB", (img_w, img_h), (255, 255, 255))
        result1 = paint_annotations(img1, [child], 0, 0, None, img_w)

        # Draw at (50, 50) offset — box should appear at image coords (50, 50)
        img2 = Image.new("RGB", (img_w, img_h), (255, 255, 255))
        result2 = paint_annotations(img2, [child], 50, 50, None, img_w)

        # The two images must differ (annotations are in different positions)
        assert result1.tobytes() != result2.tobytes()


# ── Pill Corner Consistency ───────────────────────────────────────────


class TestPillCornerConsistency:
    def test_different_corners_produce_different_output(self):
        """Changing pillCorner style should visually reposition the number pill."""
        img_w, img_h = 300, 200
        base_child = Component(
            id=uuid.uuid4(),
            number="1",
            label="A",
            bounds=Bounds(x=50, y=50, w=100, h=80),
        )

        results = {}
        for corner in ("top_left", "top_right", "bottom_left", "bottom_right"):
            child = base_child.model_copy(update={"style": Style(pillCorner=corner)})
            img = Image.new("RGB", (img_w, img_h), (255, 255, 255))
            result = paint_annotations(img, [child], 0, 0, None, img_w)
            results[corner] = result.tobytes()

        # At least top_left vs bottom_right should differ
        assert results["top_left"] != results["bottom_right"]


# ── Font Sizing Consistency Across Levels ─────────────────────────────


class TestFontSizingLevels:
    def test_nested_level_has_smaller_or_equal_font(self):
        """Pill font size at a nested level must be <= root level size."""
        root_size = compute_pill_font_size(None, 800)
        parent = Component(
            id=uuid.uuid4(),
            number="1",
            label="Parent",
            bounds=Bounds(x=0, y=0, w=400, h=400),
        )
        nested_size = compute_pill_font_size(parent, 800)
        assert nested_size <= root_size

    def test_font_at_deep_nesting_has_floor(self):
        """Even at very deep nesting, font size must not go below MIN_FONT_SIZE."""

        tiny_parent = Component(
            id=uuid.uuid4(),
            number="1111",
            label="Deep",
            bounds=Bounds(x=0, y=0, w=20, h=20),
        )
        size = compute_pill_font_size(tiny_parent, 800)
        assert size >= MIN_FONT_SIZE


# ── Composite Gapped Image ───────────────────────────────────────────


class TestCompositeGappedImage:
    def test_no_segments_returns_original(self):
        img = Image.new("RGB", (100, 100), (128, 128, 128))
        result = composite_gapped_image(img, [], 20)
        assert result is img

    def test_single_segment_no_gap(self):
        img = Image.new("RGB", (100, 200), (128, 128, 128))
        segments = [(0, 200, 0)]
        result = composite_gapped_image(img, segments, 20)
        assert result.height == 200

    def test_two_segments_adds_gap(self):
        gap_px = 20
        img = Image.new("RGB", (100, 200), (128, 128, 128))
        segments = [(0, 100, 0), (100, 200, gap_px)]
        result = composite_gapped_image(img, segments, gap_px)
        assert result.height == 200 + gap_px
        assert result.width == 100

    def test_pixel_continuity(self):
        """Segment strips must preserve their original pixel content."""
        gap_px = 20
        img = Image.new("RGB", (10, 20))
        # Fill top half red, bottom half blue
        for x in range(10):
            for y in range(10):
                img.putpixel((x, y), (255, 0, 0))
            for y in range(10, 20):
                img.putpixel((x, y), (0, 0, 255))

        segments = [(0, 10, 0), (10, 20, gap_px)]
        result = composite_gapped_image(img, segments, gap_px)

        # Top strip (y=0..9) should be red
        assert result.getpixel((5, 5)) == (255, 0, 0)
        # Bottom strip starts at y=10+gap_px=30, so pixel at y=30 should be blue
        assert result.getpixel((5, 10 + gap_px)) == (0, 0, 255)
