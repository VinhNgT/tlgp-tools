import io
import pytest
from PIL import Image
from PySide6.QtCore import QEvent, QPointF, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QApplication

from annotator.gui.app import MainAppWindow
from annotator.gui.controller import AppController
from annotator.gui.qt_dialogs import QtDialogService
from annotator.gui.state import UIStateStore
from annotator.workspace import WorkspaceManager


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if not app:
        app = QApplication([])
    yield app


def create_test_image(width: int = 800, height: int = 600) -> bytes:
    img = Image.new("RGB", (width, height), color=(128, 128, 128))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def test_mouse_deadzone(qapp):
    ws = WorkspaceManager()
    ws.import_image(create_test_image())

    store = UIStateStore()
    dialog_service = QtDialogService()
    view = MainAppWindow()
    controller = AppController(ws, store, view, dialog_service)

    canvas = view.canvas
    canvas.deadzone_radius = 5.0
    canvas.deadzone_enabled = True

    # 1. Simulate mouse press at (100, 100)
    pos = QPointF(100.0, 100.0)
    press_event = QMouseEvent(
        QEvent.Type.MouseButtonPress,
        pos,
        pos,
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    QApplication.sendEvent(canvas, press_event)

    # With instant clicks, gestures should immediately know a press happened
    assert canvas._press_pos is not None
    assert canvas.gestures.is_dragging is False

    # 2. Move mouse by 2 pixels (within deadzone)
    move_pos_small = QPointF(102.0, 100.0)
    move_event_small = QMouseEvent(
        QEvent.Type.MouseMove,
        move_pos_small,
        move_pos_small,
        Qt.MouseButton.NoButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    QApplication.sendEvent(canvas, move_event_small)

    # Dragging shouldn't have started since we are within deadzone
    assert canvas._deadzone_bypassed is False

    # 3. Move mouse by 10 pixels (outside deadzone)
    move_pos_large = QPointF(110.0, 100.0)
    move_event_large = QMouseEvent(
        QEvent.Type.MouseMove,
        move_pos_large,
        move_pos_large,
        Qt.MouseButton.NoButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    QApplication.sendEvent(canvas, move_event_large)

    # Now hold timer is stopped, and dragging is allowed
    assert canvas._hold_timer.isActive() is False

    # 4. Release mouse
    release_event = QMouseEvent(
        QEvent.Type.MouseButtonRelease,
        move_pos_large,
        move_pos_large,
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
    )
    QApplication.sendEvent(canvas, release_event)

    assert canvas._press_pos is None


def test_mouse_deadzone_bypass_on_hold(qapp):
    ws = WorkspaceManager()
    ws.import_image(create_test_image())

    store = UIStateStore()
    dialog_service = QtDialogService()
    view = MainAppWindow()
    controller = AppController(ws, store, view, dialog_service)

    canvas = view.canvas
    canvas.deadzone_radius = 5.0
    canvas.deadzone_enabled = True

    pos = QPointF(100.0, 100.0)
    press_event = QMouseEvent(
        QEvent.Type.MouseButtonPress,
        pos,
        pos,
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    QApplication.sendEvent(canvas, press_event)

    # Timer should be active
    assert canvas._hold_timer.isActive() is True

    # Simulate timeout (holding down mouse)
    canvas._hold_timer.timeout.emit()

    assert canvas._deadzone_bypassed is True

    # Move by only 2 pixels (normally within deadzone)
    move_pos_small = QPointF(102.0, 100.0)
    move_event_small = QMouseEvent(
        QEvent.Type.MouseMove,
        move_pos_small,
        move_pos_small,
        Qt.MouseButton.NoButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    QApplication.sendEvent(canvas, move_event_small)

    # Release mouse
    release_event = QMouseEvent(
        QEvent.Type.MouseButtonRelease,
        move_pos_small,
        move_pos_small,
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
    )
    QApplication.sendEvent(canvas, release_event)

    assert canvas._press_pos is None
    assert canvas._deadzone_bypassed is False


def test_mouse_instant_click(qapp):
    ws = WorkspaceManager()
    ws.import_image(create_test_image())

    store = UIStateStore()
    dialog_service = QtDialogService()
    view = MainAppWindow()
    controller = AppController(ws, store, view, dialog_service)

    canvas = view.canvas

    pos = QPointF(100.0, 100.0)
    press_event = QMouseEvent(
        QEvent.Type.MouseButtonPress,
        pos,
        pos,
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    QApplication.sendEvent(canvas, press_event)

    # Press executes instantly, no timer is active waiting to release/execute click
    assert canvas._press_pos is not None

    release_event = QMouseEvent(
        QEvent.Type.MouseButtonRelease,
        pos,
        pos,
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
    )
    QApplication.sendEvent(canvas, release_event)

    # Press state cleared immediately
    assert canvas._press_pos is None


def test_drag_and_pan_with_state_updates(qapp):
    ws = WorkspaceManager()
    ws.import_image(create_test_image())

    store = UIStateStore()
    dialog_service = QtDialogService()
    view = MainAppWindow()
    controller = AppController(ws, store, view, dialog_service)

    canvas = view.canvas
    canvas.deadzone_radius = 5.0
    canvas.deadzone_enabled = True

    # 1. Simulate mouse press at (100, 100)
    pos = QPointF(100.0, 100.0)
    press_event = QMouseEvent(
        QEvent.Type.MouseButtonPress,
        pos,
        pos,
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    QApplication.sendEvent(canvas, press_event)

    assert canvas._press_pos is not None

    # 2. Drag past deadzone (110, 100)
    move_pos = QPointF(110.0, 100.0)
    move_event = QMouseEvent(
        QEvent.Type.MouseMove,
        move_pos,
        move_pos,
        Qt.MouseButton.NoButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    QApplication.sendEvent(canvas, move_event)

    assert canvas._deadzone_bypassed is True
    # The starting mouse reference should be aligned to the crossing position to prevent visual jump
    assert canvas.gestures.pan_start_mouse == (110.0, 100.0)

    # 3. Simulate viewport state change (should NOT reset press_pos)
    canvas.set_viewport_state(1.5, (10, 10), [], "select")
    assert canvas._press_pos is not None

    # 4. Drag back near the origin (102, 100) - should NOT freeze because deadzone is bypassed
    move_pos_near = QPointF(102.0, 100.0)
    move_event_near = QMouseEvent(
        QEvent.Type.MouseMove,
        move_pos_near,
        move_pos_near,
        Qt.MouseButton.NoButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    QApplication.sendEvent(canvas, move_event_near)

    # Release
    release_event = QMouseEvent(
        QEvent.Type.MouseButtonRelease,
        move_pos_near,
        move_pos_near,
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
    )
    QApplication.sendEvent(canvas, release_event)

    assert canvas._press_pos is None


def test_ctrl_mouse_drag_marquee_select(qapp):
    ws = WorkspaceManager()
    ws.import_image(create_test_image())

    store = UIStateStore()
    dialog_service = QtDialogService()
    view = MainAppWindow()
    controller = AppController(ws, store, view, dialog_service)

    canvas = view.canvas
    canvas.deadzone_radius = 5.0
    canvas.deadzone_enabled = True

    # 1. Simulate mouse press at (100, 100) with Control key held
    pos = QPointF(100.0, 100.0)
    press_event = QMouseEvent(
        QEvent.Type.MouseButtonPress,
        pos,
        pos,
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.ControlModifier,
    )
    QApplication.sendEvent(canvas, press_event)

    # Once clicked, the temp rect is immediately initialized
    assert canvas.gestures.has_temp_rect is True

    # 2. Move mouse to (120, 120) with Control key held to bypass deadzone and drag
    move_pos = QPointF(120.0, 120.0)
    move_event = QMouseEvent(
        QEvent.Type.MouseMove,
        move_pos,
        move_pos,
        Qt.MouseButton.NoButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.ControlModifier,
    )
    QApplication.sendEvent(canvas, move_event)

    # Now the deadzone is bypassed, and it should start drawing the selection marquee (temp rect)
    assert canvas._deadzone_bypassed is True
    assert canvas.gestures.has_temp_rect is True

    # 3. Release the mouse
    release_event = QMouseEvent(
        QEvent.Type.MouseButtonRelease,
        move_pos,
        move_pos,
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.ControlModifier,
    )
    QApplication.sendEvent(canvas, release_event)

    # After release, temp rect should be cleared
    assert canvas.gestures.has_temp_rect is False


def test_zoom_focus_target_with_cuts(qapp):
    import uuid
    from annotator.models import Bounds

    ws = WorkspaceManager()
    ws.import_image(create_test_image(800, 600))
    ws.update_cut_lines([150])  # Adds a cut line at y = 150

    comp_id = uuid.uuid4()
    # Adding a component below the cut line
    ws.add_component(comp_id, "Component", Bounds(x=100, y=200, w=100, h=100))

    store = UIStateStore()
    dialog_service = QtDialogService()
    view = MainAppWindow()
    controller = AppController(ws, store, view, dialog_service)

    canvas = view.canvas
    canvas.selected_component_ids = [comp_id]

    # Rebuild segments for testing
    canvas.transformer.rebuild_segments(ws.state.cutLines)

    viewport_changes = []
    def on_viewport_change(zoom, pan):
        viewport_changes.append((zoom, pan))
    canvas.on_viewport_change_request = on_viewport_change

    canvas.zoom_focus_target()

    assert len(viewport_changes) == 1
    zoom, (pan_x, pan_y) = viewport_changes[0]

    vw, vh = canvas.width(), canvas.height()
    # Calculate expected values
    # comp.bounds.top = 200, which is > 150 (cut line), so gap_top = 20.
    # comp.bounds.bottom = 300, which is > 150, so gap_bottom = 20.
    # visual_top = 220, visual_bottom = 320, visual_h = 100.
    # visual_w = 100.
    zoom_x = (vw - 120) / 100.0
    zoom_y = (vh - 120) / 100.0
    expected_zoom = max(0.1, min(4.0, min(zoom_x, zoom_y)))
    expected_pan_x = (vw / 2) - 150.0 * expected_zoom
    expected_pan_y = (vh / 2) - 270.0 * expected_zoom

    assert zoom == pytest.approx(expected_zoom)
    assert pan_x == pytest.approx(expected_pan_x)
    assert pan_y == pytest.approx(expected_pan_y)


def test_fit_to_screen_with_parent_stack(qapp):
    import uuid
    from annotator.models import Bounds

    ws = WorkspaceManager()
    ws.import_image(create_test_image(800, 600))
    ws.update_cut_lines([150])  # Adds a cut line at y = 150

    comp_id = uuid.uuid4()
    # Adding a component below the cut line
    ws.add_component(comp_id, "Component", Bounds(x=100, y=200, w=100, h=100))

    store = UIStateStore()
    dialog_service = QtDialogService()
    view = MainAppWindow()
    controller = AppController(ws, store, view, dialog_service)

    canvas = view.canvas
    canvas.parent_stack = [comp_id]  # Mock drill-down state

    # Rebuild segments for testing
    canvas.transformer.rebuild_segments(ws.state.cutLines)

    viewport_changes = []
    def on_viewport_change(zoom, pan):
        viewport_changes.append((zoom, pan))
    canvas.on_viewport_change_request = on_viewport_change

    canvas.fit_to_screen()

    assert len(viewport_changes) == 1
    zoom, (pan_x, pan_y) = viewport_changes[0]

    vw, vh = canvas.width(), canvas.height()
    # Calculate expected values
    # comp.bounds.top = 200, which is > 150 (cut line), so gap_top = 20.
    # comp.bounds.bottom = 300, which is > 150, so gap_bottom = 20.
    # visual_top = 220, visual_bottom = 320, visual_h = 100.
    # visual_w = 100.
    zoom_x = (vw - 120) / 100.0
    zoom_y = (vh - 120) / 100.0
    expected_zoom = max(0.1, min(4.0, min(zoom_x, zoom_y)))
    expected_pan_x = (vw / 2) - 150.0 * expected_zoom
    expected_pan_y = (vh / 2) - 270.0 * expected_zoom

    assert zoom == pytest.approx(expected_zoom)
    assert pan_x == pytest.approx(expected_pan_x)
    assert pan_y == pytest.approx(expected_pan_y)


def test_fit_to_screen_with_highlighted_box(qapp):
    import uuid
    from annotator.models import Bounds

    ws = WorkspaceManager()
    ws.import_image(create_test_image(800, 600))
    ws.update_cut_lines([150])  # Adds a cut line at y = 150

    comp_id = uuid.uuid4()
    # Adding a component below the cut line
    ws.add_component(comp_id, "Component", Bounds(x=100, y=200, w=100, h=100))

    store = UIStateStore()
    dialog_service = QtDialogService()
    view = MainAppWindow()
    controller = AppController(ws, store, view, dialog_service)

    canvas = view.canvas
    canvas.selected_component_ids = [comp_id]  # Component is selected/highlighted

    # Rebuild segments for testing
    canvas.transformer.rebuild_segments(ws.state.cutLines)

    viewport_changes = []
    def on_viewport_change(zoom, pan):
        viewport_changes.append((zoom, pan))
    canvas.on_viewport_change_request = on_viewport_change

    canvas.fit_to_screen()

    assert len(viewport_changes) == 1
    zoom, (pan_x, pan_y) = viewport_changes[0]

    vw, vh = canvas.width(), canvas.height()
    # Calculate expected values
    # comp.bounds.top = 200, which is > 150 (cut line), so gap_top = 20.
    # comp.bounds.bottom = 300, which is > 150, so gap_bottom = 20.
    # visual_top = 220, visual_bottom = 320, visual_h = 100.
    # visual_w = 100.
    zoom_x = (vw - 120) / 100.0
    zoom_y = (vh - 120) / 100.0
    expected_zoom = max(0.1, min(4.0, min(zoom_x, zoom_y)))
    expected_pan_x = (vw / 2) - 150.0 * expected_zoom
    expected_pan_y = (vh / 2) - 270.0 * expected_zoom

    assert zoom == pytest.approx(expected_zoom)
    assert pan_x == pytest.approx(expected_pan_x)
    assert pan_y == pytest.approx(expected_pan_y)


def test_app_fit_button(qapp):
    ws = WorkspaceManager()
    ws.import_image(create_test_image(800, 600))
    store = UIStateStore()
    dialog_service = QtDialogService()
    view = MainAppWindow()
    controller = AppController(ws, store, view, dialog_service)

    # Initially enabled since image is loaded
    assert view.btn_fit.isEnabled() is True

    # Triggering fit button should invoke fit_to_screen without errors
    view.btn_fit.trigger()

    # If image is removed, it should be disabled
    view.set_canvas_image(None)
    assert view.btn_fit.isEnabled() is False


def test_properties_cleared_after_unselecting(qapp):
    import uuid
    from annotator.models import Bounds, Style

    ws = WorkspaceManager()
    ws.import_image(create_test_image(800, 600))
    comp_id = uuid.uuid4()
    ws.add_component(comp_id, "TestComponent", Bounds(x=100, y=200, w=100, h=100))
    ws.state.components[comp_id].style = Style(pillCorner="bottom_right")

    store = UIStateStore()
    dialog_service = QtDialogService()
    view = MainAppWindow()
    controller = AppController(ws, store, view, dialog_service)

    # 1. Select the component
    store.update_state("selection", selected_component_ids=[comp_id])
    controller._sync_properties()

    # Verify fields are populated
    assert view.properties.entry_name.text() == "TestComponent"
    assert view.properties.prop_entries["x"].text() == "100"
    assert view.properties.prop_entries["y"].text() == "200"
    assert view.properties.prop_entries["w"].text() == "100"
    assert view.properties.prop_entries["h"].text() == "100"
    assert view.properties.entry_name.isEnabled() is True
    assert view.properties.corner_selector.selected_corner == "bottom_right"

    # 2. Clear selection (unselect)
    store.update_state("selection", selected_component_ids=[])
    controller._sync_properties()

    # Verify fields are cleared
    assert view.properties.entry_name.text() == ""
    assert view.properties.prop_entries["x"].text() == ""
    assert view.properties.prop_entries["y"].text() == ""
    assert view.properties.prop_entries["w"].text() == ""
    assert view.properties.prop_entries["h"].text() == ""
    assert view.properties.entry_name.isEnabled() is False
    assert view.properties.corner_selector.selected_corner is None




