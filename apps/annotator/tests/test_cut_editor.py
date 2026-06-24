import pytest
from PIL import Image
from PySide6.QtWidgets import QApplication
from PySide6.QtCore import QPointF, Qt, QEvent
from PySide6.QtGui import QMouseEvent

from annotator.gui.cut_editor import CutEditorDialog, _CutCanvasWidget


@pytest.fixture(scope="session")
def qapp():
    app = QApplication.instance()
    if not app:
        app = QApplication([])
    yield app


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
    from annotator.gui.qt_dialogs import QtDialogService

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

    dialog = None
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
    from annotator.gui.qt_dialogs import QtDialogService

    callback_called = False
    callback_result = None

    def on_save(result):
        nonlocal callback_called, callback_result
        callback_called = True
        callback_result = result

    service = QtDialogService()
    service.show_screen_info(None, screen_name="Product Details", description="Main product info page", on_save=on_save)
    QApplication.processEvents()

    dialog = None
    for widget in reversed(QApplication.topLevelWidgets()):
        if widget.__class__.__name__ == "_ScreenInfoDialog" and widget.isVisible():
            dialog = widget
            break

    assert dialog is not None

    # Simulate saving/accepting the dialog via its save button action
    dialog._on_save()

    assert callback_called
    assert callback_result == {"screen_name": "Product Details", "description": "Main product info page"}



