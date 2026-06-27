import io

from annotator.gui.app import MainAppWindow
from annotator.gui.controller import AppController
from annotator.gui.qt_dialogs import QtDialogService
from annotator.gui.state import UIStateStore
from annotator.workspace import WorkspaceManager
from PIL import Image
from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QKeyEvent
from PySide6.QtWidgets import QApplication


def create_test_image(width: int = 800, height: int = 600) -> bytes:
    img = Image.new("RGB", (width, height), color=(128, 128, 128))
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def test_space_pan_keyboard_highlight(qapp):
    # Setup workspace
    ws = WorkspaceManager()
    ws.import_image(create_test_image())

    # Setup GUI
    store = UIStateStore()
    dialog_service = QtDialogService()
    view = MainAppWindow()
    AppController(ws, store, view, dialog_service)

    # Initial state should be "select"
    assert store.state.current_mode == "select"
    assert view.canvas.current_mode == "select"
    assert view._mode_actions["select"].isChecked()

    # Simulate Space key press on the main window
    press_event = QKeyEvent(
        QEvent.Type.KeyPress, Qt.Key.Key_Space, Qt.KeyboardModifier.NoModifier
    )
    QApplication.sendEvent(view, press_event)

    # Verify state switches to "pan" and is highlighted
    assert store.state.current_mode == "pan"
    assert view.canvas.current_mode == "pan"
    assert view._mode_actions["pan"].isChecked()
    assert view.canvas.space_pan_active is True

    # Simulate Space key release on the main window
    release_event = QKeyEvent(
        QEvent.Type.KeyRelease, Qt.Key.Key_Space, Qt.KeyboardModifier.NoModifier
    )
    QApplication.sendEvent(view, release_event)

    # Verify state restores to "select" and "select" action is checked
    assert store.state.current_mode == "select"
    assert view.canvas.current_mode == "select"
    assert view._mode_actions["select"].isChecked()
    assert not view.canvas.space_pan_active


def test_show_labels_checkbox(qapp):
    # Setup workspace
    ws = WorkspaceManager()
    ws.import_image(create_test_image())

    # Setup GUI
    store = UIStateStore()
    dialog_service = QtDialogService()
    view = MainAppWindow()
    AppController(ws, store, view, dialog_service)

    # Initial state should be: labels not shown, chk_show_labels unchecked and enabled
    assert not view.canvas.show_labels
    assert not view.chk_show_labels.isChecked()
    assert view.chk_show_labels.isEnabled()

    # Simulate user toggling the checkbox
    view.chk_show_labels.setChecked(True)

    # Verify canvas show_labels is True and checkbox is checked
    assert view.canvas.show_labels
    assert view.chk_show_labels.isChecked()

    # Simulate keyboard shortcut 'T'
    press_event = QKeyEvent(
        QEvent.Type.KeyPress, Qt.Key.Key_T, Qt.KeyboardModifier.NoModifier
    )
    QApplication.sendEvent(view, press_event)

    # Verify canvas show_labels is False and checkbox is unchecked again
    assert view.canvas.show_labels is False
    assert view.chk_show_labels.isChecked() is False


def test_auto_numbering_checkbox(qapp):
    # Setup workspace
    ws = WorkspaceManager()
    ws.import_image(create_test_image())

    # Add a component so we have something to select/number
    import uuid
    comp_id = uuid.uuid4()
    ws.add_component(comp_id, "Test Button", {"x": 10, "y": 10, "w": 100, "h": 50})

    # Setup GUI
    store = UIStateStore()
    dialog_service = QtDialogService()
    view = MainAppWindow()
    controller = AppController(ws, store, view, dialog_service)

    # Initial state should be: autoNumbering is enabled, chk_auto_number checked and enabled
    assert ws.state.autoNumbering is True
    assert view.chk_auto_number.isChecked()
    assert view.chk_auto_number.isEnabled()

    # Select the component so properties are loaded
    store.update_state("selection", selected_component_ids=[comp_id])
    assert view.properties.entry_number.text() == "1"
    assert view.properties.entry_number.isReadOnly() is True
    from PySide6.QtGui import QIntValidator
    assert isinstance(view.properties.entry_number.validator(), QIntValidator)

    # Simulate user toggling the checkbox off
    view.chk_auto_number.setChecked(False)
    controller._apply_state_sync()

    # Verify state autoNumbering is False, checkbox is unchecked, and entry is editable
    assert ws.state.autoNumbering is False
    assert not view.chk_auto_number.isChecked()
    assert view.properties.entry_number.isReadOnly() is False

    # Simulate user manually changing the number
    view.properties.entry_number.setText("42")
    view.properties._save_number()  # Trigger manual save slot
    controller._apply_state_sync()

    # Verify updated number
    assert ws.state.components[comp_id].number == "42"

    # Simulate toggling checkbox back on
    view.chk_auto_number.setChecked(True)
    controller._apply_state_sync()

    # Verify auto numbering re-enabled and recalculated
    assert ws.state.autoNumbering is True
    assert view.chk_auto_number.isChecked()
    assert view.properties.entry_number.isReadOnly() is True
    assert ws.state.components[comp_id].number == "1"


def test_export_images_button(qapp):
    # Setup workspace without image first
    ws = WorkspaceManager()
    store = UIStateStore()
    dialog_service = QtDialogService()
    view = MainAppWindow()
    AppController(ws, store, view, dialog_service)

    # Initially it should be disabled
    assert view.btn_export_images.text() == "Export images"
    assert view.btn_export_images.isEnabled() is False

    # Import image
    pil_img = Image.new("RGB", (800, 600))
    view.set_canvas_image(pil_img)

    # Now it should be enabled
    assert view.btn_export_images.isEnabled() is True
