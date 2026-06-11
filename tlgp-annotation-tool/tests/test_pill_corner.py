import pytest
from unittest.mock import MagicMock
from tlgp_annotation_tool.models import AnnotationBox, ScreenSession
from tlgp_annotation_tool.controller import SessionController
from tlgp_annotation_tool.annotation_renderer import get_pill_coords


def test_get_pill_coords_corners():
    # Box bounds: left=10, top=20, right=110, bottom=70 (width=100, height=50)
    # Pill size: width=30, height=15
    left, top, right, bottom = 10, 20, 110, 70
    pill_w, pill_h = 30, 15

    # Top-Left: px = 10, py = 20
    px, py = get_pill_coords(left, top, right, bottom, pill_w, pill_h, "top_left")
    assert px == 10
    assert py == 20

    # Top-Right: px = 10 + (100 - 30) = 80, py = 20
    px, py = get_pill_coords(left, top, right, bottom, pill_w, pill_h, "top_right")
    assert px == 80
    assert py == 20

    # Bottom-Left: px = 10, py = 20 + (50 - 15) = 55
    px, py = get_pill_coords(left, top, right, bottom, pill_w, pill_h, "bottom_left")
    assert px == 10
    assert py == 55

    # Bottom-Right: px = 80, py = 55
    px, py = get_pill_coords(left, top, right, bottom, pill_w, pill_h, "bottom_right")
    assert px == 80
    assert py == 55


def test_get_pill_coords_clamped_for_small_box():
    # Box bounds: left=10, top=20, right=20, bottom=25 (width=10, height=5)
    # Pill size: width=30, height=15 (box is smaller than pill)
    left, top, right, bottom = 10, 20, 20, 25
    pill_w, pill_h = 30, 15

    # Should clamp offsets to 0.0, placing at top-left corner
    for corner in ["top_left", "top_right", "bottom_left", "bottom_right"]:
        px, py = get_pill_coords(left, top, right, bottom, pill_w, pill_h, corner)
        assert px == 10
        assert py == 20


def test_serialization_and_deserialization():
    # Serialize AnnotationBox
    box = AnnotationBox(
        id=1,
        label="Test Box",
        x1=10,
        y1=20,
        x2=110,
        y2=70,
        pill_corner="bottom_right"
    )
    serialized = box.to_dict()
    assert serialized["pill_corner"] == "bottom_right"

    # Simulate parse_box deserialization in app.py (mocking expected layout)
    # bounds are relative to parent (assumed parent origin is 0, 0 here)
    box_data = {
        "id": 2,
        "label": "Loaded Box",
        "bounds": {"x": 5, "y": 5, "w": 50, "h": 30},
        "pill_corner": "top_right"
    }
    
    # We parse the box using direct instantiation mimicking app.py's parse_box
    loaded_box = AnnotationBox(
        id=box_data["id"],
        label=box_data["label"],
        x1=box_data["bounds"]["x"],
        y1=box_data["bounds"]["y"],
        x2=box_data["bounds"]["x"] + box_data["bounds"]["w"],
        y2=box_data["bounds"]["y"] + box_data["bounds"]["h"],
        children=[],
        pill_corner=box_data.get("pill_corner", "top_left")
    )
    
    assert loaded_box.pill_corner == "top_right"


def test_controller_pill_corner_updates_and_history():
    box = AnnotationBox(id=1, label="Test Box", x1=0, y1=0, x2=100, y2=100)
    session = ScreenSession(screen_name="Test Screen", components=[box])
    controller = SessionController(session)

    # Initial state
    assert box.pill_corner == "top_left"

    # Subscribe to update_coords event
    callback = MagicMock()
    controller.subscribe("update_coords", callback)

    # Update pill corner
    controller.update_box_pill_corner(box, "bottom_right")
    assert box.pill_corner == "bottom_right"

    # Verify event was fired
    callback.assert_called_once_with(box)

    # Verify undo restores it
    controller.undo()
    # Undo restores from a deep-copy snapshot, so we re-fetch the component reference
    restored_box = controller.session.components[0]
    assert restored_box.pill_corner == "top_left"

    # Verify redo works
    controller.redo()
    restored_box = controller.session.components[0]
    assert restored_box.pill_corner == "bottom_right"
