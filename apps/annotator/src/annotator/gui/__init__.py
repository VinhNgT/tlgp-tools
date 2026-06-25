"""PySide6 GUI initialization and dependency wiring."""

import ctypes
import os
import sys

from PySide6.QtCore import QObject, Signal
from PySide6.QtGui import QIcon
from PySide6.QtWidgets import QApplication
from tlgp_logger import get_logger

from .app import MainAppWindow
from .controller import AppController
from .qt_dialogs import QtDialogService
from .state import UIStateStore
from .theme import get_theme
from .transformer import ViewportTransformer

logger = get_logger(__name__)


class _WorkspaceSignalBridge(QObject):
    """Thread-safe signal bridge for workspace change notifications.

    Emitting from a worker thread queues the slot on the main thread's event loop.
    """

    workspace_changed = Signal()


def start_gui(workspace_manager, port: int = 8000):
    """Create the Qt application, wire all components, and run the event loop."""
    if sys.platform == "win32":
        try:
            # Set AppUserModelID to ensure taskbar shows the correct application icon on Windows
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID(
                "tlgp.annotator.app.1.0"
            )
        except Exception as e:
            logger.warning("Failed to set AppUserModelID: %s", e)

    app = QApplication.instance() or QApplication(sys.argv)

    # Apply Figma UI/UX theme
    if isinstance(app, QApplication):
        app.setStyleSheet(get_theme())

    if isinstance(app, QApplication):
        icon_path = os.path.join(os.path.dirname(__file__), "icon.png")
        if os.path.exists(icon_path):
            app.setWindowIcon(QIcon(icon_path))

    # Create observable state store
    store = UIStateStore()

    # Create view state helper classes
    transformer = ViewportTransformer()

    # Create dialog service
    dialog_service = QtDialogService()

    # Create main window view
    view = MainAppWindow(transformer, port=port)

    # Instantiate controller linking workspace, state store, and views
    controller = AppController(workspace_manager, store, view, dialog_service)

    # Wire workspace events to main thread via signal bridge
    bridge = _WorkspaceSignalBridge()
    bridge.workspace_changed.connect(controller._apply_state_sync)  # noqa: SLF001

    def on_workspace_changed(*_args):
        bridge.workspace_changed.emit()

    workspace_manager.subscribe(on_workspace_changed)

    app.aboutToQuit.connect(controller.shutdown)

    # Show and run
    view.showMaximized()
    sys.exit(app.exec())
