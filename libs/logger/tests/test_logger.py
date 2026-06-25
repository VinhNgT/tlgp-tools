import json
import logging
import sys
from io import StringIO
from unittest.mock import MagicMock

import pytest
import tlgp_logger.core
from structlog.testing import capture_logs
from tlgp_logger import get_logger, setup_excepthook, setup_logging


@pytest.fixture(autouse=True)
def reset_logging_initialized():
    tlgp_logger.core._initialized = False
    yield
    tlgp_logger.core._initialized = False


def test_logger_json_format():
    # Capture stderr
    stderr = sys.stderr
    sys.stderr = StringIO()

    setup_logging(log_level="INFO", json_format=True)

    try:
        logger = get_logger("test_logger")
        logger.info("this is a test", user_id=123)

        output = sys.stderr.getvalue()
        log_data = json.loads(output)

        assert log_data["event"] == "this is a test"
        assert log_data["user_id"] == 123
        assert log_data["level"] == "info"
        assert log_data["logger"] == "test_logger"
        assert "timestamp" in log_data
    finally:
        sys.stderr = stderr


def test_standard_logging_interception():
    # Capture stderr
    stderr = sys.stderr
    sys.stderr = StringIO()

    setup_logging(log_level="INFO", json_format=True)

    try:
        std_logger = logging.getLogger("stdlib_logger")
        std_logger.warning("standard log test")

        output = sys.stderr.getvalue()
        log_data = json.loads(output)

        assert log_data["event"] == "standard log test"
        assert log_data["level"] == "warning"
        assert log_data["logger"] == "stdlib_logger"
    finally:
        sys.stderr = stderr


def test_excepthook_interception():
    original_hook = sys.excepthook

    setup_logging(log_level="INFO", json_format=True)
    setup_excepthook()

    try:
        with capture_logs() as captured:
            try:
                raise ValueError("unhandled error test")
            except ValueError as e:
                sys.excepthook(type(e), e, e.__traceback__)

        assert len(captured) == 1
        log_data = captured[0]
        assert log_data["log_level"] == "critical"
        assert "Unhandled exception caught by global hook" in log_data["event"]
    finally:
        sys.excepthook = original_hook


def test_excepthook_keyboard_interrupt():
    original_hook = sys.excepthook
    original_sys_excepthook = sys.__excepthook__

    mock_sys_excepthook = MagicMock()
    sys.__excepthook__ = mock_sys_excepthook

    setup_excepthook()

    try:
        sys.excepthook(KeyboardInterrupt, KeyboardInterrupt(), None)
        mock_sys_excepthook.assert_called_once()
    finally:
        sys.excepthook = original_hook
        sys.__excepthook__ = original_sys_excepthook
