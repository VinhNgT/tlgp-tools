import tkinter as tk
from uuid import uuid4
from unittest.mock import patch
import pytest
from PIL import Image

from gui.state import UIStateStore
from gui.dialog_service import DialogService
from gui.controllers.controller import AppController
from models import WorkspaceState, ImageInfo


@pytest.fixture(autouse=True)
def mock_tkinter_menu():
    with patch("tkinter.Menu") as mock:
        yield mock


class MockWidget:
    def config(self, **kwargs):
        pass

    def entryconfig(self, *args, **kwargs):
        pass

    def bind(self, event, callback):
        pass


class MockAppWindow:
    def __init__(self):
        self.canvas = MockWidget()
        self.tree = MockWidget()
        self.properties = MockWidget()
        self.lbl_status = MockWidget()
        self.lbl_zoom = MockWidget()
        self.btn_back = MockWidget()
        self.btn_mode_select = MockWidget()
        self.btn_mode_draw = MockWidget()
        self.btn_mode_pan = MockWidget()
        self.btn_zoom_out = MockWidget()
        self.btn_zoom_in = MockWidget()
        self.btn_zoom_focus = MockWidget()
        self.btn_cut_lines = MockWidget()
        self.btn_screen_info = MockWidget()
        self.file_menu = MockWidget()
        self.edit_menu = MockWidget()
        self.lbl_breadcrumb = MockWidget()
        self.report_callback_exception = None

    def config(self, **kwargs):
        pass

    def set_ui_interactive(self, enabled):
        pass

    def after(self, ms, func):
        func()


class MockDialogService(DialogService):
    def __init__(self):
        self.errors = []
        self.warnings = []
        self.infos = []
        self.importing_dialog_shown = False
        self.cut_editor_shown = False
        self.screen_info_shown = False
        self.mock_file_path = "mock_session.zip"
        self.mock_save_path = "mock_output.zip"
        self.mock_cut_lines = [100, 200]
        self.mock_screen_info = {"screen_name": "Login", "description": "Login page"}

    def ask_open_filename(self, parent, title, filetypes):
        return self.mock_file_path

    def ask_save_as_filename(self, parent, title, filetypes, defaultextension):
        return self.mock_save_path

    def show_error(self, parent, title, message):
        self.errors.append((title, message))

    def show_warning(self, parent, title, message):
        self.warnings.append((title, message))

    def show_info(self, parent, title, message):
        self.infos.append((title, message))

    def show_importing_dialog(self, parent, message):
        self.importing_dialog_shown = True
        class MockDialog:
            def destroy(self):
                pass
        return MockDialog()

    def show_cut_editor(self, parent, image, initial_cuts, components):
        self.cut_editor_shown = True
        return self.mock_cut_lines

    def show_screen_info(self, parent, screen_name, description):
        self.screen_info_shown = True
        return self.mock_screen_info


class MockEngineClient:
    def __init__(self):
        self.state = None
        self.on_state_changed = None
        self.on_error = None
        self.imported_zip = None
        self.imported_image = None
        self.exported = False
        self.updated_cut_lines = None
        self.updated_screen_info = None

    def import_zip(self, path, on_complete):
        self.imported_zip = path
        on_complete(None)

    def import_image(self, path, on_complete):
        self.imported_image = path
        on_complete(None)

    def export_zip_data(self, on_complete):
        self.exported = True
        on_complete(None, b"mock zip bytes")

    def update_cut_lines(self, lines):
        self.updated_cut_lines = lines

    def update_screen_info(self, name, description):
        self.updated_screen_info = (name, description)


def test_controller_import_zip():
    store = UIStateStore()
    client = MockEngineClient()
    view = MockAppWindow()
    dialogs = MockDialogService()

    controller = AppController(client, store, view, dialogs)
    controller._on_import_zip_request()

    assert client.imported_zip == "mock_session.zip"
    assert dialogs.importing_dialog_shown is True
    assert len(dialogs.errors) == 0


def test_controller_export_zip(tmp_path):
    store = UIStateStore()
    client = MockEngineClient()
    view = MockAppWindow()
    # Mock loaded image on canvas
    view.canvas.full_pil_img = Image.new("RGB", (100, 100))
    dialogs = MockDialogService()
    dialogs.mock_save_path = str(tmp_path / "mock_output.zip")

    controller = AppController(client, store, view, dialogs)
    controller._on_export_zip_request()

    assert client.exported is True
    assert dialogs.importing_dialog_shown is True
    assert len(dialogs.infos) == 1
    assert dialogs.infos[0][0] == "Success"


def test_controller_open_cut_editor():
    store = UIStateStore()
    client = MockEngineClient()
    view = MockAppWindow()
    # Mock image info in workspace state
    ws = WorkspaceState(
        sessionId=uuid4(),
        image=ImageInfo(filename="test.png", width=1000, height=1000)
    )
    store.update_state("workspace", workspace_state=ws)
    view.canvas.full_pil_img = Image.new("RGB", (1000, 1000))

    dialogs = MockDialogService()

    controller = AppController(client, store, view, dialogs)
    controller._on_open_cut_editor_request()

    assert dialogs.cut_editor_shown is True
    assert client.updated_cut_lines == [100, 200]
