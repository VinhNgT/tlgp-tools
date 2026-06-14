import os

from tlgp_logger import setup_excepthook, setup_logging

from .api_client import EngineClient
from .controllers.controller import AppController
from .dialog_service import TkinterDialogService
from .state import UIStateStore
from .views.app import MainAppWindow
from .views.gestures import GestureInterpreter
from .views.transformer import ViewportTransformer


def main():
    env = os.environ.get("TLGP_ENV", "dev")
    setup_logging(json_format=(env == "prod"))
    setup_excepthook()

    # Create observable state store
    store = UIStateStore()

    # Create view state helper classes
    transformer = ViewportTransformer()
    gestures = GestureInterpreter(store, transformer)

    # Create model API client
    client = EngineClient(
        on_state_changed=lambda: None,
        on_error=None,
    )
    client.start()

    # Create dialog service
    dialog_service = TkinterDialogService()

    # Create passive main window view
    view = MainAppWindow(store, transformer, gestures)

    # Instantiate controller linking model client, state store, and views
    _controller = AppController(client, store, view, dialog_service)

    try:
        # Start GUI main loop
        view.mainloop()
    finally:
        client.stop()


if __name__ == "__main__":
    main()
