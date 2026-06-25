import io
import uuid

import pytest
from annotator.gui.app import MainAppWindow
from annotator.gui.controller import AppController
from annotator.gui.qt_dialogs import QtDialogService
from annotator.gui.state import UIStateStore
from annotator.models import Bounds, Style
from annotator.workspace import WorkspaceManager
from PIL import Image
from PySide6.QtCore import QEvent, QPoint, QPointF, QRect, Qt
from PySide6.QtGui import QKeyEvent, QMouseEvent, QPaintEvent, QWheelEvent
from PySide6.QtWidgets import QApplication


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
    AppController(ws, store, view, dialog_service)

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
    AppController(ws, store, view, dialog_service)

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
    AppController(ws, store, view, dialog_service)

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
    AppController(ws, store, view, dialog_service)

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
    AppController(ws, store, view, dialog_service)

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
    ws = WorkspaceManager()
    ws.import_image(create_test_image(800, 600))
    ws.update_cut_lines([150])  # Adds a cut line at y = 150

    comp_id = uuid.uuid4()
    # Adding a component below the cut line
    ws.add_component(comp_id, "Component", Bounds(x=100, y=200, w=100, h=100))

    store = UIStateStore()
    dialog_service = QtDialogService()
    view = MainAppWindow()
    AppController(ws, store, view, dialog_service)

    canvas = view.canvas
    canvas.selected_component_ids = [comp_id]

    # Rebuild segments for testing
    canvas.transformer.rebuild_segments(ws.state.cutLines)

    viewport_changes = []

    def on_viewport_change(zoom, pan):
        viewport_changes.append((zoom, pan))

    canvas.callbacks.on_viewport_change_request = on_viewport_change

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
    ws = WorkspaceManager()
    ws.import_image(create_test_image(800, 600))
    ws.update_cut_lines([150])  # Adds a cut line at y = 150

    comp_id = uuid.uuid4()
    # Adding a component below the cut line
    ws.add_component(comp_id, "Component", Bounds(x=100, y=200, w=100, h=100))

    store = UIStateStore()
    dialog_service = QtDialogService()
    view = MainAppWindow()
    AppController(ws, store, view, dialog_service)

    canvas = view.canvas
    canvas.parent_stack = [comp_id]  # Mock drill-down state

    # Rebuild segments for testing
    canvas.transformer.rebuild_segments(ws.state.cutLines)

    viewport_changes = []

    def on_viewport_change(zoom, pan):
        viewport_changes.append((zoom, pan))

    canvas.callbacks.on_viewport_change_request = on_viewport_change

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
    ws = WorkspaceManager()
    ws.import_image(create_test_image(800, 600))
    ws.update_cut_lines([150])  # Adds a cut line at y = 150

    comp_id = uuid.uuid4()
    # Adding a component below the cut line
    ws.add_component(comp_id, "Component", Bounds(x=100, y=200, w=100, h=100))

    store = UIStateStore()
    dialog_service = QtDialogService()
    view = MainAppWindow()
    AppController(ws, store, view, dialog_service)

    canvas = view.canvas
    canvas.selected_component_ids = [comp_id]  # Component is selected/highlighted

    # Rebuild segments for testing
    canvas.transformer.rebuild_segments(ws.state.cutLines)

    viewport_changes = []

    def on_viewport_change(zoom, pan):
        viewport_changes.append((zoom, pan))

    canvas.callbacks.on_viewport_change_request = on_viewport_change

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
    AppController(ws, store, view, dialog_service)

    # Initially enabled since image is loaded
    assert view.btn_fit.isEnabled() is True

    # Triggering fit button should invoke fit_to_screen without errors
    view.btn_fit.trigger()

    # If image is removed, it should be disabled
    view.set_canvas_image(None)
    assert view.btn_fit.isEnabled() is False


def test_properties_cleared_after_unselecting(qapp):
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


def test_welcome_widget_import_callbacks(qapp):
    ws = WorkspaceManager()
    store = UIStateStore()
    dialog_service = QtDialogService()
    view = MainAppWindow()
    AppController(ws, store, view, dialog_service)

    assert view.welcome.isHidden() is False

    called_zip = False
    called_img = False

    def on_zip():
        nonlocal called_zip
        called_zip = True

    def on_img():
        nonlocal called_img
        called_img = True

    view.callbacks.on_import_zip_request = on_zip
    view.callbacks.on_import_image_request = on_img

    view.welcome.btn_zip.click()
    assert called_zip is True

    view.welcome.btn_img.click()
    assert called_img is True


def test_canvas_paint_event(qapp):
    ws = WorkspaceManager()
    ws.import_image(create_test_image())
    store = UIStateStore()
    dialog_service = QtDialogService()
    view = MainAppWindow()
    AppController(ws, store, view, dialog_service)

    event = QPaintEvent(QRect(0, 0, 800, 600))
    # This triggers paintEvent, which should not raise any AttributeError
    view.canvas.paintEvent(event)


def test_canvas_adaptive_cursors(qapp):
    ws = WorkspaceManager()
    ws.import_image(create_test_image(800, 600))

    # Add a component at bounds (100, 100, 100, 100)
    comp_id = uuid.uuid4()
    ws.add_component(comp_id, "TestComponent", Bounds(x=100, y=100, w=100, h=100))

    store = UIStateStore()
    dialog_service = QtDialogService()
    view = MainAppWindow()
    controller = AppController(ws, store, view, dialog_service)
    canvas = view.canvas

    # Resize canvas to match test image size
    canvas.resize(800, 600)
    canvas.fit_to_screen()

    # 1. Default mode is 'select'. Hovering over background (e.g. 50, 50) should show default cursor.
    pos_bg = QPointF(50.0, 50.0)
    move_bg = QMouseEvent(
        QEvent.Type.MouseMove,
        pos_bg,
        pos_bg,
        Qt.MouseButton.NoButton,
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
    )
    QApplication.sendEvent(canvas, move_bg)
    assert canvas.cursor().shape() == Qt.CursorShape.ArrowCursor

    # 2. Press 'R' to switch to draw mode. Cursor should instantly change to CrossCursor (draw) without moving the mouse.
    press_r = QKeyEvent(
        QEvent.Type.KeyPress, Qt.Key.Key_R, Qt.KeyboardModifier.NoModifier
    )
    QApplication.sendEvent(view, press_r)
    assert canvas.cursor().shape() == Qt.CursorShape.CrossCursor

    # 3. Press 'H' to switch to pan mode. Cursor should instantly change to OpenHandCursor (pan_inactive) without moving.
    press_h = QKeyEvent(
        QEvent.Type.KeyPress, Qt.Key.Key_H, Qt.KeyboardModifier.NoModifier
    )
    QApplication.sendEvent(view, press_h)
    assert canvas.cursor().shape() == Qt.CursorShape.OpenHandCursor

    # 4. Press 'V' to switch back to select mode.
    press_v = QKeyEvent(
        QEvent.Type.KeyPress, Qt.Key.Key_V, Qt.KeyboardModifier.NoModifier
    )
    QApplication.sendEvent(view, press_v)

    # Hover over background again
    QApplication.sendEvent(canvas, move_bg)
    assert canvas.cursor().shape() == Qt.CursorShape.ArrowCursor

    # 5. Hovering over the component (center at 150, 150)
    cx, cy = canvas.transformer.to_canvas(
        150, 150, canvas.zoom_factor, [], [], canvas.pan_offset
    )
    pos_comp = QPointF(cx, cy)
    move_comp = QMouseEvent(
        QEvent.Type.MouseMove,
        pos_comp,
        pos_comp,
        Qt.MouseButton.NoButton,
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
    )
    QApplication.sendEvent(canvas, move_comp)
    # Should show ArrowCursor (normal pointer)
    assert canvas.cursor().shape() == Qt.CursorShape.ArrowCursor

    # 6. Select the component
    store.update_state("selection", selected_component_ids=[comp_id])
    controller._on_selection_updated()  # syncs selection and triggers cursor update

    # Now check handles of the selected component.
    # Top-left corner of the component is (100, 100).
    cx_tl, cy_tl = canvas.transformer.to_canvas(
        100, 100, canvas.zoom_factor, [], [], canvas.pan_offset
    )
    pos_tl = QPointF(cx_tl, cy_tl)
    move_tl = QMouseEvent(
        QEvent.Type.MouseMove,
        pos_tl,
        pos_tl,
        Qt.MouseButton.NoButton,
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
    )
    QApplication.sendEvent(canvas, move_tl)
    # Should show SizeFDiagCursor (resize_nw)
    assert canvas.cursor().shape() == Qt.CursorShape.SizeFDiagCursor

    # 7. Drag on the handle (resizing)
    # Simulate press
    press_tl = QMouseEvent(
        QEvent.Type.MouseButtonPress,
        pos_tl,
        pos_tl,
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    QApplication.sendEvent(canvas, press_tl)
    # Under selection mode drag, it should keep the SizeFDiagCursor
    assert canvas.cursor().shape() == Qt.CursorShape.SizeFDiagCursor

    # Drag move
    pos_drag = QPointF(cx_tl - 20, cy_tl - 20)
    drag_tl = QMouseEvent(
        QEvent.Type.MouseMove,
        pos_drag,
        pos_drag,
        Qt.MouseButton.NoButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    # Bypass deadzone to start drag
    canvas._deadzone_bypassed = True
    QApplication.sendEvent(canvas, drag_tl)
    assert canvas.cursor().shape() == Qt.CursorShape.SizeFDiagCursor

    # Release
    release_tl = QMouseEvent(
        QEvent.Type.MouseButtonRelease,
        pos_drag,
        pos_drag,
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
    )
    QApplication.sendEvent(canvas, release_tl)


def test_drag_snap_on_winning_deadzone(qapp):
    ws = WorkspaceManager()
    ws.import_image(create_test_image(800, 600))

    comp_id = uuid.uuid4()
    ws.add_component(comp_id, "TestComponent", Bounds(x=100, y=100, w=50, h=50))

    store = UIStateStore()
    dialog_service = QtDialogService()
    view = MainAppWindow()
    controller = AppController(ws, store, view, dialog_service)
    canvas = view.canvas

    canvas.resize(800, 600)
    canvas.fit_to_screen()
    store.update_state("selection", selected_component_ids=[comp_id])
    controller._on_selection_updated()

    canvas.deadzone_radius = 5.0
    canvas.deadzone_enabled = True

    cx, cy = canvas.transformer.to_canvas(
        125, 125, canvas.zoom_factor, [], [], canvas.pan_offset
    )
    pos_press = QPointF(cx, cy)
    press_event = QMouseEvent(
        QEvent.Type.MouseButtonPress,
        pos_press,
        pos_press,
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    QApplication.sendEvent(canvas, press_event)

    assert canvas._press_pos is not None
    assert canvas.gestures.is_dragging is True

    pos_drag = QPointF(cx + 10, cy)
    drag_event = QMouseEvent(
        QEvent.Type.MouseMove,
        pos_drag,
        pos_drag,
        Qt.MouseButton.NoButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    QApplication.sendEvent(canvas, drag_event)

    assert canvas._deadzone_bypassed is True

    orig_mx, orig_my = canvas.transformer.to_abs(
        cx, cy, canvas.zoom_factor, [], [], canvas.pan_offset
    )
    drag_mx, drag_my = canvas.transformer.to_abs(
        cx + 10, cy, canvas.zoom_factor, [], [], canvas.pan_offset
    )
    expected_dx = drag_mx - orig_mx

    assert canvas.active_interaction is not None
    assert comp_id in canvas.active_interaction
    bounds = canvas.active_interaction[comp_id]

    assert bounds.x == pytest.approx(100.0 + expected_dx)

    release_event = QMouseEvent(
        QEvent.Type.MouseButtonRelease,
        pos_drag,
        pos_drag,
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
    )
    QApplication.sendEvent(canvas, release_event)


def test_parent_boundary_enforced_on_drag(qapp):
    ws = WorkspaceManager()
    ws.import_image(create_test_image(800, 600))

    parent_id = uuid.uuid4()
    child_id = uuid.uuid4()

    ws.add_component(
        comp_id=parent_id, label="parent", bounds=Bounds(x=50, y=50, w=200, h=200)
    )
    ws.add_component(
        comp_id=child_id,
        label="child",
        bounds=Bounds(x=100, y=100, w=50, h=50),
        parent_id=parent_id,
    )

    store = UIStateStore()
    dialog_service = QtDialogService()
    view = MainAppWindow()
    controller = AppController(ws, store, view, dialog_service)
    canvas = view.canvas

    canvas.resize(800, 600)
    canvas.fit_to_screen()
    # Drill into parent
    controller._on_canvas_drill_into(parent_id)
    # Now select child
    store.update_state("selection", selected_component_ids=[child_id])
    controller._on_selection_updated()

    canvas.deadzone_enabled = False

    cx, cy = canvas.transformer.to_canvas(
        125, 125, canvas.zoom_factor, [], [], canvas.pan_offset
    )

    pos_press = QPointF(cx, cy)
    press_event = QMouseEvent(
        QEvent.Type.MouseButtonPress,
        pos_press,
        pos_press,
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    QApplication.sendEvent(canvas, press_event)

    # Drag far to the right (e.g., cx + 500)
    pos_drag = QPointF(cx + 500, cy)
    drag_event = QMouseEvent(
        QEvent.Type.MouseMove,
        pos_drag,
        pos_drag,
        Qt.MouseButton.NoButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    QApplication.sendEvent(canvas, drag_event)

    assert canvas.active_interaction is not None
    assert child_id in canvas.active_interaction
    bounds = canvas.active_interaction[child_id]

    # It must be clamped exactly to the parent bounds: x + w <= 250 -> x <= 200
    assert bounds.x == 200

    # Also test dragging left past parent left boundary (x=50)
    pos_drag_left = QPointF(cx - 500, cy)
    drag_event_left = QMouseEvent(
        QEvent.Type.MouseMove,
        pos_drag_left,
        pos_drag_left,
        Qt.MouseButton.NoButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    QApplication.sendEvent(canvas, drag_event_left)

    bounds_left = canvas.active_interaction[child_id]
    # It must be clamped exactly to parent left boundary: x >= 50
    assert bounds_left.x == 50

    # Release mouse to clean up
    release_event = QMouseEvent(
        QEvent.Type.MouseButtonRelease,
        pos_drag_left,
        pos_drag_left,
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
    )
    QApplication.sendEvent(canvas, release_event)


def test_scroll_while_panning(qapp):
    ws = WorkspaceManager()
    ws.import_image(create_test_image(800, 600))

    store = UIStateStore()
    dialog_service = QtDialogService()
    view = MainAppWindow()
    AppController(ws, store, view, dialog_service)
    canvas = view.canvas

    canvas.resize(800, 600)
    canvas.fit_to_screen()
    canvas.deadzone_enabled = False

    # Initial state
    init_pan = canvas.pan_offset

    # 1. Middle mouse press at (400, 300)
    pos_press = QPointF(400.0, 300.0)
    press_event = QMouseEvent(
        QEvent.Type.MouseButtonPress,
        pos_press,
        pos_press,
        Qt.MouseButton.MiddleButton,
        Qt.MouseButton.MiddleButton,
        Qt.KeyboardModifier.NoModifier,
    )
    QApplication.sendEvent(canvas, press_event)

    assert canvas.gestures.state.space_panning is True
    assert canvas.gestures.state.pan_start_mouse == (400.0, 300.0)
    assert canvas.gestures.state.pan_start_offset == init_pan

    # 2. Drag to (410, 320)
    pos_drag1 = QPointF(410.0, 320.0)
    drag_event1 = QMouseEvent(
        QEvent.Type.MouseMove,
        pos_drag1,
        pos_drag1,
        Qt.MouseButton.NoButton,
        Qt.MouseButton.MiddleButton,
        Qt.KeyboardModifier.NoModifier,
    )
    QApplication.sendEvent(canvas, drag_event1)

    # The pan offset should be updated by dx=10, dy=20
    assert canvas.pan_offset == (init_pan[0] + 10.0, init_pan[1] + 20.0)

    # 3. Simulate a wheel scroll event at (410, 320)
    # Scroll vertically by 120 (delta = 120), which maps to delta * 0.5 = 60 pixels of pan
    wheel_event = QWheelEvent(
        QPointF(410.0, 320.0),
        QPointF(410.0, 320.0),
        QPoint(0, 0),
        QPoint(0, 120),
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
        Qt.ScrollPhase.NoScrollPhase,
        False,
    )
    QApplication.sendEvent(canvas, wheel_event)

    # Scroll amount is delta * 0.5 = 60 pixels vertically.
    # Since dy > 0, scroll_amount is positive, py += 60.
    # Old pan_offset was init_pan + (10, 20), new pan_offset should be init_pan + (10.0, 80.0)
    assert canvas.pan_offset == (init_pan[0] + 10.0, init_pan[1] + 80.0)

    # The pan_start_offset and pan_start_mouse should have updated!
    assert canvas.gestures.state.pan_start_offset == (
        init_pan[0] + 10.0,
        init_pan[1] + 80.0,
    )
    assert canvas.gestures.state.pan_start_mouse == (410.0, 320.0)

    # 4. Drag slightly more to (412, 321) (dx=2, dy=1 relative to the scroll position)
    pos_drag2 = QPointF(412.0, 321.0)
    drag_event2 = QMouseEvent(
        QEvent.Type.MouseMove,
        pos_drag2,
        pos_drag2,
        Qt.MouseButton.NoButton,
        Qt.MouseButton.MiddleButton,
        Qt.KeyboardModifier.NoModifier,
    )
    QApplication.sendEvent(canvas, drag_event2)

    # The new pan offset should be pan_start_offset + (412 - 410, 321 - 320) = init_pan + (12.0, 81.0)
    assert canvas.pan_offset == (init_pan[0] + 12.0, init_pan[1] + 81.0)

    # Release
    release_event = QMouseEvent(
        QEvent.Type.MouseButtonRelease,
        pos_drag2,
        pos_drag2,
        Qt.MouseButton.MiddleButton,
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
    )
    QApplication.sendEvent(canvas, release_event)

    assert canvas.gestures.state.space_panning is False
