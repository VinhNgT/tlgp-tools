from typing import Any

from annotator.gui.cut_editor import CutEditorDialog
from annotator.gui.qt_dialogs import QtDialogService
from PIL import Image
from PySide6.QtCore import QEvent, QPointF, Qt
from PySide6.QtGui import QMouseEvent
from PySide6.QtWidgets import QApplication, QFileDialog


def test_cut_editor_initialization(qapp):
    """Verify that CutEditorDialog correctly initializes and preserves initial cuts."""
    image = Image.new("RGB", (800, 1000), color=(128, 128, 128))
    initial_cuts = [100, 200, 300]
    components = []

    dialog = CutEditorDialog(None, image, initial_cuts, components)

    # The dialog's state should hold the sorted initial cuts
    assert dialog.state.cut_lines == [100, 200, 300]

    # The canvas widget's state should be synchronized/identical to the dialog's state
    assert dialog.canvas_widget.state.cut_lines == [100, 200, 300]


def test_cut_editor_add_cut(qapp):
    """Verify that adding a cut line updates both dialog and canvas state."""
    image = Image.new("RGB", (800, 1000), color=(128, 128, 128))
    initial_cuts = [100, 200]
    components = []

    dialog = CutEditorDialog(None, image, initial_cuts, components)

    # Switch to add mode
    dialog._start_add_mode()
    assert dialog.state.mode == "adding"
    assert dialog.canvas_widget.state.mode == "adding"

    # Set canvas zoom and scroll to 1.0 and 0.0 for deterministic coordinate mapping
    canvas = dialog.canvas_widget
    canvas.zoom_factor = 1.0
    canvas._scroll_offset = 0.0

    # Simulate mouse press to add a cut line at image y = 400
    pos = QPointF(100.0, 400.0)
    press_event = QMouseEvent(
        QEvent.Type.MouseButtonPress,
        pos,
        pos,
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    QApplication.sendEvent(canvas, press_event)

    # Verify that y = 400 is added and list is sorted
    assert 400 in dialog.state.cut_lines
    assert dialog.state.cut_lines == [100, 200, 400]
    assert canvas.state.cut_lines == [100, 200, 400]

    # Verify mode returns to idle
    assert dialog.state.mode == "idle"
    assert canvas.state.mode == "idle"


def test_cut_editor_drag_spacing_warning(qapp):
    """Verify that dragging a cut line to an invalid spacing position updates the status label."""
    image = Image.new("RGB", (800, 1000), color=(128, 128, 128))
    initial_cuts = [100, 200]
    components = []

    dialog = CutEditorDialog(None, image, initial_cuts, components)
    canvas = dialog.canvas_widget
    canvas.zoom_factor = 1.0
    canvas._scroll_offset = 0.0

    # Simulate mouse press on the second cut line (y=200) to start drag
    pos_press = QPointF(100.0, 200.0)
    press_event = QMouseEvent(
        QEvent.Type.MouseButtonPress,
        pos_press,
        pos_press,
        Qt.MouseButton.LeftButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    QApplication.sendEvent(canvas, press_event)

    assert dialog.state.mode == "dragging"
    assert dialog.state.drag_index == 1

    # Drag the line to y=120, which is too close to y=100 (gap is 20 < MIN_CUT_GAP=50)
    pos_drag = QPointF(100.0, 120.0)
    drag_event = QMouseEvent(
        QEvent.Type.MouseMove,
        pos_drag,
        pos_drag,
        Qt.MouseButton.NoButton,
        Qt.MouseButton.LeftButton,
        Qt.KeyboardModifier.NoModifier,
    )
    QApplication.sendEvent(canvas, drag_event)

    # Verify warning message in status label
    assert "Blocked: invalid gap to adjacent cuts" in dialog.status_label.text()
    # Verify cut lines list is not modified/remains at last valid position (200)
    assert dialog.state.cut_lines == [100, 200]


def test_dialog_service_show_cut_editor_modeless(qapp):
    """Verify that QtDialogService.show_cut_editor shows the dialog without blocking and triggers callback on save."""
    image = Image.new("RGB", (800, 1000), color=(128, 128, 128))
    initial_cuts = [100, 200]
    components = []

    callback_called = False
    callback_result = None

    def on_save(result):
        nonlocal callback_called, callback_result
        callback_called = True
        callback_result = result

    service = QtDialogService()
    service.show_cut_editor(None, image, initial_cuts, components, on_save)
    QApplication.processEvents()

    dialog: Any = None
    for widget in reversed(QApplication.topLevelWidgets()):
        if widget.__class__.__name__ == "CutEditorDialog" and widget.isVisible():
            dialog = widget
            break

    assert dialog is not None

    # Simulate saving/accepting the dialog via its save button action
    dialog._on_ok()

    assert callback_called
    assert callback_result == [100, 200]


def test_dialog_service_show_screen_info_modeless(qapp):
    """Verify that QtDialogService.show_screen_info shows the dialog without blocking and triggers callback on save."""
    callback_called = False
    callback_result = None

    def on_save(result):
        nonlocal callback_called, callback_result
        callback_called = True
        callback_result = result

    service = QtDialogService()
    service.show_screen_info(
        None,
        screen_name="Product Details",
        description="Main product info page",
        on_save=on_save,
    )
    QApplication.processEvents()

    dialog: Any = None
    for widget in reversed(QApplication.topLevelWidgets()):
        if widget.__class__.__name__ == "_ScreenInfoDialog" and widget.isVisible():
            dialog = widget
            break

    assert dialog is not None

    # Simulate saving/accepting the dialog via its save button action
    dialog._on_save()

    assert callback_called
    assert callback_result == {
        "screen_name": "Product Details",
        "description": "Main product info page",
    }


def test_dialog_service_ask_directory(qapp, monkeypatch):
    """Verify that ask_directory calls QFileDialog.getExistingDirectory and returns the selected path."""
    monkeypatch.setattr(
        QFileDialog, "getExistingDirectory", lambda parent, title: "/mock/directory"
    )
    service = QtDialogService()
    path = service.ask_directory(None, "Select Folder")
    assert path == "/mock/directory"


def test_dialog_service_ask_export_images_options(qapp):
    """Verify that ask_export_images_options properly instantiates _ExportImagesDialog, accepts choices, and triggers the callback."""
    callback_called = False
    callback_mode = None
    callback_format = None

    def on_selected(mode, format_val):
        nonlocal callback_called, callback_mode, callback_format
        callback_called = True
        callback_mode = mode
        callback_format = format_val

    service = QtDialogService()
    service.ask_export_images_options(None, on_selected)
    QApplication.processEvents()

    dialog: Any = None
    for widget in reversed(QApplication.topLevelWidgets()):
        if widget.__class__.__name__ == "_ExportImagesDialog" and widget.isVisible():
            dialog = widget
            break

    assert dialog is not None

    # Check default values
    assert dialog.rad_annotated.isChecked()
    assert dialog.rad_folder.isChecked()

    # Simulate selecting 'both' and 'zip' format
    dialog.rad_both.setChecked(True)
    dialog.rad_zip.setChecked(True)

    # Accept the dialog
    dialog.accept()
    QApplication.processEvents()

    assert callback_called
    assert callback_mode == "both"
    assert callback_format == "zip"


def test_dialog_service_ask_save_as_filename(qapp, monkeypatch):
    """Verify that ask_save_as_filename calls QFileDialog.getSaveFileName with initial_filename and returns the selected path."""
    called_initial_filename = None

    def mock_get_save_file_name(parent, title, initial_filename, filter_str):
        nonlocal called_initial_filename
        called_initial_filename = initial_filename
        return "/mock/file.zip", "Zip files (*.zip)"

    monkeypatch.setattr(QFileDialog, "getSaveFileName", mock_get_save_file_name)
    service = QtDialogService()
    path = service.ask_save_as_filename(
        None,
        "Save Zip",
        [("Zip files", "*.zip")],
        ".zip",
        initial_filename="my_default.zip",
    )
    assert path == "/mock/file.zip"
    assert called_initial_filename == "my_default.zip"


def test_cut_editor_hover_ghost_line(qapp):
    """Verify that moving mouse over the screenshot updates hover_y only in adding mode, and leaving clears it."""
    image = Image.new("RGB", (800, 1000), color=(128, 128, 128))
    initial_cuts = [100, 200]
    components = []

    dialog = CutEditorDialog(None, image, initial_cuts, components)
    canvas = dialog.canvas_widget
    canvas.fit_and_render()
    canvas.zoom_factor = 1.0
    canvas._scroll_offset = 0.0
    assert canvas._base_pixmap is not None

    # Hover is initially None
    assert dialog.state.hover_y is None

    # Simulate mouse move inside the screenshot bounds (x=100, y=450)
    pos_inside = QPointF(100.0, 450.0)
    move_event1 = QMouseEvent(
        QEvent.Type.MouseMove,
        pos_inside,
        pos_inside,
        Qt.MouseButton.NoButton,
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
    )
    QApplication.sendEvent(canvas, move_event1)

    # In idle mode, hover_y should remain None
    assert dialog.state.hover_y is None

    # Switch to adding mode
    dialog._start_add_mode()
    assert dialog.state.mode == "adding"

    # Move inside again in adding mode
    QApplication.sendEvent(canvas, move_event1)

    # hover_y should be updated to round(450) = 450
    assert dialog.state.hover_y == 450

    # Simulate mouse move outside screenshot width bounds (x=900, y=450)
    pos_outside_x = QPointF(900.0, 450.0)
    move_event2 = QMouseEvent(
        QEvent.Type.MouseMove,
        pos_outside_x,
        pos_outside_x,
        Qt.MouseButton.NoButton,
        Qt.MouseButton.NoButton,
        Qt.KeyboardModifier.NoModifier,
    )
    QApplication.sendEvent(canvas, move_event2)

    # hover_y should be cleared to None
    assert dialog.state.hover_y is None

    # Hover inside again
    QApplication.sendEvent(canvas, move_event1)
    assert dialog.state.hover_y == 450

    # Simulate leaving the widget
    leave_event = QEvent(QEvent.Type.Leave)
    QApplication.sendEvent(canvas, leave_event)

    # hover_y should be cleared to None
    assert dialog.state.hover_y is None
