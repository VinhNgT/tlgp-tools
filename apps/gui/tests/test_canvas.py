from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from gui.views.canvas import AnnotationCanvasView
from models import Bounds, Component, Style, Visibility, WorkspaceState


def test_zoom_focus_target_single_selection():
    transformer = MagicMock()
    gestures = MagicMock()
    canvas = AnnotationCanvasView(None, transformer, gestures)

    canvas.winfo_width = MagicMock(return_value=800)
    canvas.winfo_height = MagicMock(return_value=600)
    canvas.on_viewport_change_request = MagicMock()

    comp_id = uuid4()
    comp = Component(
        id=comp_id,
        number="1",
        label="Test Box",
        bounds=Bounds(x=10, y=20, w=100, h=150),
        style=Style(),
        visibility=Visibility(),
    )
    canvas.workspace_state = WorkspaceState(
        sessionId=uuid4(),
        components={comp_id: comp}
    )

    canvas.selected_component_ids = [comp_id]
    canvas.parent_stack = []

    # Mock transformer to map 1:1 for canvas coordinates
    canvas.transformer.to_canvas.side_effect = lambda x, y, zoom, parent_stack, cut_lines: (x, y)

    canvas.zoom_focus_target()

    # cx1, cy1 = 10, 20
    # cx2, cy2 = 110, 170
    # cx = (10 + 110)/2 = 60
    # cy = (20 + 170)/2 = 95
    # zoom_factor = 3.0 (cap)
    # scroll_x = 400 - 60 * 3 = 220
    # scroll_y = 300 - 95 * 3 = 15
    canvas.on_viewport_change_request.assert_called_once_with(3.0, (220.0, 15.0))


def test_zoom_focus_target_multi_selection():
    transformer = MagicMock()
    gestures = MagicMock()
    canvas = AnnotationCanvasView(None, transformer, gestures)

    canvas.winfo_width = MagicMock(return_value=800)
    canvas.winfo_height = MagicMock(return_value=600)
    canvas.on_viewport_change_request = MagicMock()

    comp_id1 = uuid4()
    comp1 = Component(
        id=comp_id1,
        number="1",
        label="Test Box 1",
        bounds=Bounds(x=100, y=100, w=100, h=100),
        style=Style(),
        visibility=Visibility(),
    )
    comp_id2 = uuid4()
    comp2 = Component(
        id=comp_id2,
        number="2",
        label="Test Box 2",
        bounds=Bounds(x=300, y=300, w=100, h=100),
        style=Style(),
        visibility=Visibility(),
    )
    canvas.workspace_state = WorkspaceState(
        sessionId=uuid4(),
        components={comp_id1: comp1, comp_id2: comp2}
    )

    canvas.selected_component_ids = [comp_id1, comp_id2]
    canvas.parent_stack = []

    canvas.transformer.to_canvas.side_effect = lambda x, y, zoom, parent_stack, cut_lines: (x, y)

    canvas.zoom_focus_target()

    # Union bounds of comp1 & comp2:
    # left = 100, top = 100
    # right = 400, bottom = 400
    # cx1, cy1 = 100, 100
    # cx2, cy2 = 400, 400
    # box_w = 300, box_h = 300
    # pad = 80
    # fit_w = (800 - 80) / 300 = 2.4
    # fit_h = (600 - 80) / 300 = 1.733
    # zoom_factor = min(2.4, 1.733) = 1.733...
    # cx = (100 + 400)/2 = 250
    # cy = (100 + 400)/2 = 250
    # scroll_x = 400 - 250 * zoom_factor
    # scroll_y = 300 - 250 * zoom_factor
    args, kwargs = canvas.on_viewport_change_request.call_args
    zoom_factor = args[0]
    scroll_x, scroll_y = args[1]

    assert zoom_factor == pytest.approx(1.7333333333333334)
    assert scroll_x == pytest.approx(400 - 250 * zoom_factor)
    assert scroll_y == pytest.approx(300 - 250 * zoom_factor)


def test_zoom_focus_target_parent_stack_fallback():
    transformer = MagicMock()
    gestures = MagicMock()
    canvas = AnnotationCanvasView(None, transformer, gestures)

    canvas.winfo_width = MagicMock(return_value=800)
    canvas.winfo_height = MagicMock(return_value=600)
    canvas.on_viewport_change_request = MagicMock()

    pid = uuid4()
    parent_comp = Component(
        id=pid,
        number="P1",
        label="Parent Box",
        bounds=Bounds(x=50, y=50, w=200, h=200),
        style=Style(),
        visibility=Visibility(),
    )
    canvas.workspace_state = WorkspaceState(
        sessionId=uuid4(),
        components={pid: parent_comp}
    )

    canvas.selected_component_ids = []
    canvas.parent_stack = [pid]

    canvas.transformer.to_canvas.side_effect = lambda x, y, zoom, parent_stack, cut_lines: (x, y)

    canvas.zoom_focus_target()

    # Targets parent box because parent_stack is active and selection is empty
    # parent box bounds: center (150, 150)
    # zoom_factor = 2.6
    # scroll_x = 400 - 150 * 2.6 = 10
    # scroll_y = 300 - 150 * 2.6 = -90
    canvas.on_viewport_change_request.assert_called_once_with(2.6, (10.0, -90.0))


def test_zoom_focus_target_empty_active_components_fallback():
    transformer = MagicMock()
    gestures = MagicMock()
    canvas = AnnotationCanvasView(None, transformer, gestures)

    canvas.winfo_width = MagicMock(return_value=800)
    canvas.winfo_height = MagicMock(return_value=600)
    canvas.on_viewport_change_request = MagicMock()
    canvas.fit_to_screen = MagicMock()

    # Nothing selected, empty active components, empty parent stack
    canvas.selected_component_ids = []
    canvas.parent_stack = []
    canvas.workspace_state = WorkspaceState(sessionId=uuid4(), components={})

    canvas.zoom_focus_target()

    canvas.fit_to_screen.assert_called_once()
    canvas.on_viewport_change_request.assert_not_called()


def test_parent_mask_with_cut_lines():
    from gui.domain.transformer import ViewportTransformer
    from PIL import Image

    transformer = ViewportTransformer()
    transformer.update_image_size(100, 200)

    gestures = MagicMock()
    canvas = AnnotationCanvasView(None, transformer, gestures)
    canvas._w = "mock_canvas_w"
    canvas.winfo_width = MagicMock(return_value=100)
    canvas.winfo_height = MagicMock(return_value=220)

    parent_id = uuid4()
    parent_comp = Component(
        id=parent_id,
        number="1",
        label="Parent",
        bounds=Bounds(x=10, y=50, w=80, h=100),
        style=Style(),
        visibility=Visibility(),
    )
    canvas.workspace_state = WorkspaceState(
        sessionId=uuid4(),
        components={parent_id: parent_comp},
        cutLines=[80]
    )
    canvas.parent_stack = [parent_id]

    bg_img = Image.new("RGB", (100, 200), (255, 255, 255))
    canvas.set_background_image(bg_img)
    from unittest.mock import patch
    with patch("PIL.ImageTk.PhotoImage", return_value=MagicMock()):
        canvas.update_view()



    mask = canvas._get_or_create_full_parent_mask()
    assert mask is not None
    assert mask.width == 100
    assert mask.height == 220

    # Under current code (without fix), the mask rectangle is drawn at absolute bounds (y=50 to y=150).
    # With a gap at y=80, the parent content in the image starts at y=50 and ends at y=170.
    # Therefore, y=165 (which is inside the parent) will be outside the mask bounds (165 > 150) and have value 80.
    # Let's assert that the corrected behavior matches:
    assert mask.getpixel((50, 45)) == 80
    assert mask.getpixel((50, 55)) == 255
    assert mask.getpixel((50, 165)) == 255
    assert mask.getpixel((50, 175)) == 80



