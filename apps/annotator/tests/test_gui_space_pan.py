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
    assert view.canvas.space_pan_active is False


def test_show_labels_checkbox(qapp):
    # Setup workspace
    ws = WorkspaceManager()
    ws.import_image(create_test_image())

    # Setup GUI
    store = UIStateStore()
    dialog_service = QtDialogService()
    view = MainAppWindow()
    AppController(ws, store, view, dialog_service)

    # Initial state should be: labels shown, chk_show_labels checked and enabled
    assert view.canvas.show_labels is True
    assert view.chk_show_labels.isChecked() is True
    assert view.chk_show_labels.isEnabled() is True

    # Simulate user toggling the checkbox
    view.chk_show_labels.setChecked(False)

    # Verify canvas show_labels is False and checkbox is unchecked
    assert view.canvas.show_labels is False
    assert view.chk_show_labels.isChecked() is False

    # Simulate keyboard shortcut 'T'
    press_event = QKeyEvent(
        QEvent.Type.KeyPress, Qt.Key.Key_T, Qt.KeyboardModifier.NoModifier
    )
    QApplication.sendEvent(view, press_event)

    # Verify canvas show_labels is True and checkbox is checked again
    assert view.canvas.show_labels is True
    assert view.chk_show_labels.isChecked() is True
