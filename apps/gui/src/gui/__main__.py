import os

from tlgp_logger import setup_logging


def main():
    env = os.environ.get("TLGP_ENV", "dev")
    setup_logging(json_format=(env == "prod"))
    print("Hello from gui!")


if __name__ == "__main__":
    main()
