"""Entry point for the Annotator application.

Starts the FastAPI server on a background thread and the PySide6 GUI on
the main thread. Both share a single WorkspaceManager instance.
"""

import asyncio
import ctypes
import os
import sys
import threading

import uvicorn
from tlgp_logger import get_logger, setup_excepthook, setup_logging

from annotator.api.app import create_app
from annotator.gui import start_gui
from annotator.workspace import WorkspaceManager

logger = get_logger(__name__)

_SERVER_STARTUP_TIMEOUT = 5  # seconds


def main():
    setup_logging(json_format=(os.environ.get("TLGP_ENV") == "prod"))
    setup_excepthook()

    # When executed under the IDE's agent runtime sandbox, the thread starts
    # on a custom hidden desktop (e.g. 'agy-...'). On Windows, we dynamically
    # switch the thread desktop to 'WinSta0\Default' so that the Qt GUI window
    # is displayed on the user's interactive monitor.
    if sys.platform == "win32":
        hdesk = ctypes.windll.user32.OpenDesktopW("Default", 0, True, 0x01FF)
        if hdesk:
            ctypes.windll.user32.SetThreadDesktop(hdesk)
            logger.info("Switched main thread desktop to WinSta0\\Default")
        else:
            logger.warning("Failed to open WinSta0\\Default desktop")

    # Single domain instance shared by GUI + API
    workspace = WorkspaceManager()

    # Explicit event loop for the server thread.
    # We use server.serve() (not uvicorn.run()) because run() creates its
    # own loop internally.
    server_loop = asyncio.new_event_loop()
    app = create_app(workspace)
    ready_event = threading.Event()

    def run_server():
        asyncio.set_event_loop(server_loop)
        config = uvicorn.Config(
            app, host="127.0.0.1", port=8000, log_config=None,
        )
        server = uvicorn.Server(config)

        # Signal readiness after startup completes
        original_startup = server.startup

        async def startup_with_signal(*args, **kwargs):
            await original_startup(*args, **kwargs)
            ready_event.set()

        server.startup = startup_with_signal
        server_loop.run_until_complete(server.serve())

    server_thread = threading.Thread(target=run_server, daemon=True)
    server_thread.start()

    # Block until server is ready (or timeout)
    if not ready_event.wait(timeout=_SERVER_STARTUP_TIMEOUT):
        logger.error("FastAPI server failed to start within %ds", _SERVER_STARTUP_TIMEOUT)
        sys.exit(1)

    logger.info("FastAPI server ready on http://127.0.0.1:8000")

    # GUI on main thread — server is guaranteed running
    start_gui(workspace)


if __name__ == "__main__":
    main()
