from uuid import uuid4

from gui.domain.validation import BoundsValidator, CutValidator
from models import Bounds, Component, Style, Visibility


def test_clamp_val():
    assert BoundsValidator.clamp_val(5, 10, 20) == 10
    assert BoundsValidator.clamp_val(15, 10, 20) == 15
    assert BoundsValidator.clamp_val(25, 10, 20) == 20


def test_clamp_box_position():
    # Box: x=100, y=100, w=50, h=50. Drag dx=20, dy=20.
    # Boundary: [0, 0, 200, 200]
    rx1, ry1 = BoundsValidator.clamp_box_position(
        100, 100, 50, 50, 20, 20, 0, 0, 200, 200
    )
    assert rx1 == 120
    assert ry1 == 120

    # Drag out of bounds: dx=100, dy=100. Should clamp to boundary limit (x_max = 200 - 50 = 150)
    rx1, ry1 = BoundsValidator.clamp_box_position(
        100, 100, 50, 50, 100, 100, 0, 0, 200, 200
    )
    assert rx1 == 150
    assert ry1 == 150


def test_clamp_resize():
    # Box: x1=100, y1=100, x2=200, y2=200. Resize "se" by dx=50, dy=50.
    # Boundary: [0, 0, 300, 300]
    rx1, ry1, rx2, ry2 = BoundsValidator.clamp_resize(
        100, 100, 200, 200, 50, 50, "se", 0, 0, 300, 300
    )
    assert rx1 == 100
    assert ry1 == 100
    assert rx2 == 250
    assert ry2 == 250

    # Resize "w" (left edge) to exceed right edge (size < min_size)
    rx1, ry1, rx2, ry2 = BoundsValidator.clamp_resize(
        100, 100, 110, 200, 20, 0, "w", 0, 0, 300, 300, min_size=4
    )
    assert rx1 == 106  # should keep min_size of 4 relative to rx2 (110)
    assert rx2 == 110

    # Resize with children union restriction: children union is [120, 120, 180, 180]
    # Resize "e" (right edge) trying to shrink past 180 (dx=-50 -> rx2 becomes 150)
    rx1, ry1, rx2, ry2 = BoundsValidator.clamp_resize(
        100,
        100,
        200,
        200,
        -50,
        0,
        "e",
        0,
        0,
        300,
        300,
        children_union=(120, 120, 180, 180),
    )
    assert rx2 == 180  # clamped to children's right edge union


def test_cut_validator_get_intersecting_component():
    comp = Component(
        id=uuid4(),
        number="1",
        label="Test Button",
        bounds=Bounds(x=50, y=100, w=100, h=50),  # top=100, bottom=150
        style=Style(),
        visibility=Visibility(visible=True, locked=False),
    )
    components = [comp]

    # Coordinate is above the component bounds
    assert CutValidator.get_intersecting_component(99, components) is None

    # Coordinate is exactly at the top boundary of the component
    assert CutValidator.get_intersecting_component(100, components) == comp

    # Coordinate is inside the component bounds
    assert CutValidator.get_intersecting_component(120, components) == comp

    # Coordinate is exactly at the bottom boundary of the component
    assert CutValidator.get_intersecting_component(150, components) == comp

    # Coordinate is below the component bounds
    assert CutValidator.get_intersecting_component(151, components) is None


def test_cut_validator_is_valid_position():
    image_height = 1000
    cut_lines = [200, 400]
    min_gap = 50

    # Outside top margin
    assert not CutValidator.is_valid_position(49, image_height, cut_lines, min_gap)

    # At exact top margin limit
    assert CutValidator.is_valid_position(50, image_height, cut_lines, min_gap)

    # Outside bottom margin
    assert not CutValidator.is_valid_position(951, image_height, cut_lines, min_gap)

    # At exact bottom margin limit
    assert CutValidator.is_valid_position(950, image_height, cut_lines, min_gap)

    # Too close to an existing cut line (lower side)
    assert not CutValidator.is_valid_position(199, image_height, cut_lines, min_gap)

    # Too close to an existing cut line (higher side)
    assert not CutValidator.is_valid_position(201, image_height, cut_lines, min_gap)

    # Valid position between cut lines
    assert CutValidator.is_valid_position(300, image_height, cut_lines, min_gap)


def test_cut_validator_is_valid_position_for_drag():
    image_height = 1000
    cut_lines = [200, 400]
    min_gap = 50

    # Dragging the first cut line (index 0) too close to the second cut line
    assert not CutValidator.is_valid_position_for_drag(
        351, image_height, cut_lines, 0, min_gap
    )

    # Dragging the first cut line (index 0) to a valid position (e.g. 100)
    assert CutValidator.is_valid_position_for_drag(
        100, image_height, cut_lines, 0, min_gap
    )

    # Dragging index 0 too close to index 1 (400)
    assert not CutValidator.is_valid_position_for_drag(
        399, image_height, cut_lines, 0, min_gap
    )

    # Margin check limits should still apply during drag
    assert not CutValidator.is_valid_position_for_drag(
        49, image_height, cut_lines, 0, min_gap
    )
    assert CutValidator.is_valid_position_for_drag(
        50, image_height, cut_lines, 0, min_gap
    )
