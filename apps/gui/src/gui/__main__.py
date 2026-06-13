import os

from tlgp_logger import setup_logging

from .app import main as run_gui


def main():
    env = os.environ.get("TLGP_ENV", "dev")
    setup_logging(json_format=(env == "prod"))
    run_gui()


if __name__ == "__main__":
    main()
