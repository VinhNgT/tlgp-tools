from uuid import uuid4

from models import Bounds, Component
from rendering.renderer import (
    compute_border_widths,
    compute_level_scale,
    compute_pill_font_size,
    compute_pill_padding,
    get_pill_coords,
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
