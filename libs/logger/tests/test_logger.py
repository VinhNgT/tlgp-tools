import json
import logging
import sys
from io import StringIO

from tlgp_logger import get_logger, setup_logging


def test_logger_json_format():
    # Capture stdout
    stdout = sys.stdout
    sys.stdout = StringIO()

    setup_logging(log_level="INFO", json_format=True)

    try:
        logger = get_logger("test_logger")
        logger.info("this is a test", user_id=123)

        output = sys.stdout.getvalue()
        log_data = json.loads(output)

        assert log_data["event"] == "this is a test"
        assert log_data["user_id"] == 123
        assert log_data["level"] == "info"
        assert log_data["logger"] == "test_logger"
        assert "timestamp" in log_data
    finally:
        sys.stdout = stdout


def test_standard_logging_interception():
    # Capture stdout
    stdout = sys.stdout
    sys.stdout = StringIO()

    setup_logging(log_level="INFO", json_format=True)

    try:
        std_logger = logging.getLogger("stdlib_logger")
        std_logger.warning("standard log test")

        output = sys.stdout.getvalue()
        log_data = json.loads(output)

        assert log_data["event"] == "standard log test"
        assert log_data["level"] == "warning"
        assert log_data["logger"] == "stdlib_logger"
    finally:
        sys.stdout = stdout
