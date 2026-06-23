import threading

import uvicorn
from annotator.api.app import _workspace_manager, create_app
from annotator.gui import start_gui
from tlgp_logger import setup_excepthook, setup_logging


def run_api():
    app = create_app()
    uvicorn.run(app, host="127.0.0.1", port=8000, log_level="warning")

def main():
    setup_logging(json_format=False)
    setup_excepthook()

    # Start API in background thread
    api_thread = threading.Thread(target=run_api, daemon=True)
    api_thread.start()

    # Start GUI in main thread (blocks until window closed)
    start_gui(_workspace_manager)

if __name__ == "__main__":
    main()
