from unittest.mock import MagicMock, patch
from uuid import uuid4

import rendering.renderer
from models import Bounds, Component, Visibility
from PIL import Image, ImageFont
from rendering.renderer import (
    composite_gapped_image,
    compute_border_widths,
    compute_level_scale,
    compute_pill_font_size,
    compute_pill_padding,
    draw_annotations_on_image,
    get_font,
    get_pill_coords,
    get_text_dimensions,
)


def test_root_level_sizing():
    scale = compute_level_scale(None, 1000)
    assert scale == 1.0

    font_size = compute_pill_font_size(None, 1000)
    assert font_size == 30

    border, outline = compute_border_widths(None, 1000)
    assert border == 5
    assert outline == 3


def test_sub_level_sizing_half():
    parent = Component(
        id=uuid4(),
        number="1",
        label="Parent",
        bounds=Bounds(x=10, y=20, w=500, h=300),
    )
    scale = compute_level_scale(parent, 1000)
    assert scale == 0.5

    font_size = compute_pill_font_size(parent, 1000)
    assert font_size == 15

    border, outline = compute_border_widths(parent, 1000)
    assert border == 2
    assert outline == 2


def test_legibility_floors():
    parent = Component(
        id=uuid4(),
        number="1",
        label="Parent",
        bounds=Bounds(x=10, y=20, w=100, h=80),
    )
    scale = compute_level_scale(parent, 1000)
    assert scale == 0.1

    font_size = compute_pill_font_size(parent, 1000)
    assert font_size == 12

    border, outline = compute_border_widths(parent, 1000)
    assert border == 1
    assert outline == 1


def test_pill_padding_proportions():
    pad_x, pad_y = compute_pill_padding(30)
    assert pad_x == 21
    assert pad_y == 12

    pad_x, pad_y = compute_pill_padding(12)
    assert pad_x == 8
    assert pad_y == 5


def test_get_pill_coords():
    left, top, right, bottom = 100.0, 200.0, 300.0, 400.0
    pill_w, pill_h = 50.0, 30.0

    px, py = get_pill_coords(left, top, right, bottom, pill_w, pill_h, "top_left")
    assert px == 100.0
    assert py == 200.0

    px, py = get_pill_coords(left, top, right, bottom, pill_w, pill_h, "top_right")
    assert px == 250.0
    assert py == 200.0

    px, py = get_pill_coords(left, top, right, bottom, pill_w, pill_h, "bottom_left")
    assert px == 100.0
    assert py == 370.0

    px, py = get_pill_coords(left, top, right, bottom, pill_w, pill_h, "bottom_right")
    assert px == 250.0
    assert py == 370.0


def test_get_font_fallbacks():
    orig_truetype = ImageFont.truetype

    def mock_truetype(font, *args, **kwargs):
        if isinstance(font, str):
            raise OSError("Font file not found")
        return orig_truetype(font, *args, **kwargs)

    with patch("PIL.ImageFont.truetype", side_effect=mock_truetype):
        rendering.renderer._font_cache.pop(999, None)
        font = get_font(999)
        assert font is not None


def test_get_text_dimensions_fallbacks():
    font = MagicMock()
    del font.getbbox
    font.size = 12

    w, h, top = get_text_dimensions(None, "1.1.1", font)
    assert w == 40
    assert h == 14
    assert top == 0


def test_draw_annotations_on_image():
    img = Image.new("RGB", (200, 200), "white")
    comp1 = Component(
        id=uuid4(),
        number="1",
        label="Test Box 1",
        bounds=Bounds(x=10, y=10, w=50, h=50),
        visibility=Visibility(visible=True)
    )
    comp2 = Component(
        id=uuid4(),
        number="2",
        label="Test Box 2",
        bounds=Bounds(x=100, y=100, w=50, h=50),
        visibility=Visibility(visible=False)
    )

    original_bytes = img.tobytes()
    draw_annotations_on_image(img, [comp1, comp2], offset_x=0, offset_y=0, parent_comp=None, full_img_width=200)

    modified_bytes = img.tobytes()
    assert original_bytes != modified_bytes


def test_composite_gapped_image():
    src_img = Image.new("RGB", (100, 100), "white")
    segments = [
        (0, 40, 0),
        (40, 100, 20)
    ]
    comp_img = composite_gapped_image(src_img, segments, cut_gap_px=20)
    assert comp_img.height == 120
    assert comp_img.width == 100
