from unittest.mock import MagicMock, patch

import pytest


@pytest.fixture(autouse=True)
def tk_headless():
    """
    Globally mocks Tcl/Tk and tkinter.Canvas initialization to support headless
    test environments (CI/headless runners) across all GUI unit tests.
    """
    def mock_init(self, *args, **kwargs):
        self.tk = MagicMock()

    init_patch = patch("tkinter.Canvas.__init__", mock_init)
    bind_patch = patch("tkinter.Canvas.bind", lambda *args, **kwargs: None)
    bind_all_patch = patch("tkinter.Canvas.bind_all", lambda *args, **kwargs: None)

    init_patch.start()
    bind_patch.start()
    bind_all_patch.start()

    yield

    init_patch.stop()
    bind_patch.stop()
    bind_all_patch.stop()
