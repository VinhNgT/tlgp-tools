from gui.domain.validation import BoundsValidator

def test_clamp_val():
    assert BoundsValidator.clamp_val(5, 10, 20) == 10
    assert BoundsValidator.clamp_val(15, 10, 20) == 15
    assert BoundsValidator.clamp_val(25, 10, 20) == 20

def test_clamp_box_position():
    # Box: x=100, y=100, w=50, h=50. Drag dx=20, dy=20.
    # Boundary: [0, 0, 200, 200]
    rx1, ry1 = BoundsValidator.clamp_box_position(100, 100, 50, 50, 20, 20, 0, 0, 200, 200)
    assert rx1 == 120
    assert ry1 == 120

    # Drag out of bounds: dx=100, dy=100. Should clamp to boundary limit (x_max = 200 - 50 = 150)
    rx1, ry1 = BoundsValidator.clamp_box_position(100, 100, 50, 50, 100, 100, 0, 0, 200, 200)
    assert rx1 == 150
    assert ry1 == 150

def test_clamp_resize():
    # Box: x1=100, y1=100, x2=200, y2=200. Resize "se" by dx=50, dy=50.
    # Boundary: [0, 0, 300, 300]
    rx1, ry1, rx2, ry2 = BoundsValidator.clamp_resize(100, 100, 200, 200, 50, 50, "se", 0, 0, 300, 300)
    assert rx1 == 100
    assert ry1 == 100
    assert rx2 == 250
    assert ry2 == 250

    # Resize "w" (left edge) to exceed right edge (size < min_size)
    rx1, ry1, rx2, ry2 = BoundsValidator.clamp_resize(100, 100, 110, 200, 20, 0, "w", 0, 0, 300, 300, min_size=4)
    assert rx1 == 106  # should keep min_size of 4 relative to rx2 (110)
    assert rx2 == 110

    # Resize with children union restriction: children union is [120, 120, 180, 180]
    # Resize "e" (right edge) trying to shrink past 180 (dx=-50 -> rx2 becomes 150)
    rx1, ry1, rx2, ry2 = BoundsValidator.clamp_resize(100, 100, 200, 200, -50, 0, "e", 0, 0, 300, 300, children_union=(120, 120, 180, 180))
    assert rx2 == 180  # clamped to children's right edge union
