import os

import uvicorn
from tlgp_logger import setup_logging


def main():
    """Starts the Uvicorn server for the FastAPI engine."""
    env = os.environ.get("TLGP_ENV", "dev")
    setup_logging(json_format=(env == "prod"))
    uvicorn.run("engine.app:app", host="127.0.0.1", port=8000)


if __name__ == "__main__":
    main()
