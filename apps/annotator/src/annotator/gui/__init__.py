from tlgp_logger import get_logger

from .app import MainAppWindow
from .controller import AppController
from .gestures import GestureInterpreter
from .state import UIStateStore
from .tkinter_dialog_service import TkinterDialogService
from .transformer import ViewportTransformer

logger = get_logger(__name__)

def start_gui(workspace_manager):
    # Create observable state store
    store = UIStateStore()

    # Create view state helper classes
    transformer = ViewportTransformer()
    gestures = GestureInterpreter(transformer)

    # Create dialog service
    dialog_service = TkinterDialogService()

    # Create passive main window view
    view = MainAppWindow(transformer, gestures)

    # Instantiate controller linking workspace, state store, and views
    _controller = AppController(workspace_manager, store, view, dialog_service)

    # Wire workspace events to main thread
    def on_workspace_changed(patch, new_state):
        view.after(0, lambda: _controller._apply_state_sync())  # noqa: SLF001

    workspace_manager.subscribe(on_workspace_changed)

    # Start GUI main loop
    view.mainloop()
