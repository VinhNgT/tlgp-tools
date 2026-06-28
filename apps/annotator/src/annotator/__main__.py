"""Entry point for the Annotator application.

Starts the FastAPI server on a background thread and the PySide6 GUI on
the main thread. Both share a single WorkspaceManager instance.
"""

import asyncio
import ctypes
import os
import socket
import sys
import threading

import uvicorn
from tlgp_logger import get_logger, setup_excepthook, setup_logging

from annotator.api.app import create_app
from annotator.gui import start_gui
from annotator.workspace import WorkspaceManager

logger = get_logger(__name__)

_SERVER_STARTUP_TIMEOUT = 5  # seconds


def is_port_free(port: int) -> bool:
    """Check if the given localhost port is free to bind."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.bind(("127.0.0.1", port))
            return True
    except Exception:
        return False


def get_free_port() -> int:
    """Find a free port on localhost dynamically."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        s.bind(("127.0.0.1", 0))
        return s.getsockname()[1]


def main():
    # Redirect stdout to stderr to prevent log pollution from third-party libraries
    original_stdout = sys.stdout
    sys.stdout = sys.stderr

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

    # Resolve dynamic port
    env_port = os.environ.get("TLGP_PORT")
    port = None
    if env_port:
        try:
            parsed_port = int(env_port)
            if is_port_free(parsed_port):
                port = parsed_port
        except ValueError:
            pass

    if port is None:
        port = get_free_port()

    # Immediately write the selected port to the original stdout and flush
    original_stdout.write(f"PORT={port}\n")
    original_stdout.flush()

    def run_server():
        asyncio.set_event_loop(server_loop)
        config = uvicorn.Config(
            app,
            host="127.0.0.1",
            port=port,
            log_config=None,
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
        logger.error(
            "FastAPI server failed to start within %ds", _SERVER_STARTUP_TIMEOUT
        )
        sys.exit(1)

    logger.info("FastAPI server ready on http://127.0.0.1:%s", port)

    # Load workspace session or raw image on startup if passed as CLI argument
    if len(sys.argv) > 1:
        path = sys.argv[1]
        if os.path.exists(path):
            try:
                with open(path, "rb") as f:
                    file_bytes = f.read()
                if path.lower().endswith(".zip"):
                    workspace.import_zip(file_bytes)
                    logger.info("Loaded workspace session from %s", path)
                else:
                    workspace.import_image(file_bytes, os.path.basename(path))
                    logger.info("Loaded background image from %s", path)
            except Exception as e:
                logger.error("Failed to load startup path %s: %s", path, e)
        else:
            logger.error("Startup path does not exist: %s", path)

    # GUI on main thread — server is guaranteed running
    exit_code = start_gui(workspace, port)
    if exit_code == 0:
        logger.info("Application closed cleanly by the user")
    else:
        logger.warning("Application closed with exit code %s", exit_code)
    sys.exit(exit_code)


if __name__ == "__main__":
    main()

