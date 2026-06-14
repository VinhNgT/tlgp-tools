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

    def show_welcome_screen(self):
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

    def move_component(self, comp_id, x, y):
        pass

    def update_component(self, comp_id, **kwargs):
        pass

    def delete_component(self, comp_id):
        pass


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


def test_controller_active_interaction_bounds_matching():
    from uuid import uuid4
    from models import Component, Bounds, Style, Visibility

    store = UIStateStore()
    client = MockEngineClient()
    view = MockAppWindow()

    class MockGestures:
        def __init__(self):
            self.is_dragging = False

    view.canvas.gestures = MockGestures()
    view.canvas.image_item_id = None
    view.canvas.full_pil_img = None
    dialogs = MockDialogService()

    controller = AppController(client, store, view, dialogs)

    comp_id = uuid4()
    transient_bounds = Bounds(x=200, y=200, w=100, h=100)
    store.update_state("selection", active_interaction={comp_id: transient_bounds})

    comp_match = Component(
        id=comp_id,
        number="1",
        label="Comp",
        bounds=Bounds(x=200, y=200, w=100, h=100),
        style=Style(),
        visibility=Visibility()
    )
    ws_match = WorkspaceState(
        sessionId=uuid4(),
        components={comp_id: comp_match}
    )
    client.state = ws_match

    # Scenario 1: Dragging is active. active_interaction should be preserved even if bounds match.
    view.canvas.gestures.is_dragging = True
    controller._apply_state_sync()
    assert store.state.active_interaction == {comp_id: transient_bounds}

    # Scenario 2: Dragging is inactive. Bounds match. active_interaction should be cleared.
    view.canvas.gestures.is_dragging = False
    controller._apply_state_sync()
    assert store.state.active_interaction is None


def test_controller_properties_input_preservation():
    from models import Component, Bounds, Style, Visibility
    from uuid import uuid4

    store = UIStateStore()
    client = MockEngineClient()
    view = MockAppWindow()

    # Mock the passive view interface of the properties panel
    class MockPropertiesPanel:
        def __init__(self):
            self.focused_fields = set()
            self.values = {}
            self.panel_updated = False
            self.disabled = False

        def update_properties_panel(self, box):
            self.panel_updated = True

        def disable_properties_fields(self):
            self.disabled = True

        def is_field_focused(self, field_name):
            return field_name in self.focused_fields

        def update_field_value(self, field_name, value):
            self.values[field_name] = value

    mock_properties = MockPropertiesPanel()
    view.properties = mock_properties

    controller = AppController(client, store, view, MockDialogService())

    comp_id = uuid4()
    comp = Component(
        id=comp_id,
        number="1",
        label="Initial Label",
        bounds=Bounds(x=10, y=20, w=100, h=200),
        style=Style(),
        visibility=Visibility()
    )
    ws = WorkspaceState(
        sessionId=uuid4(),
        components={comp_id: comp}
    )
    client.state = ws
    store.update_state("workspace", workspace_state=ws)
    store.update_state("selection", selected_component_ids=[comp_id])

    # Scenario 1: Focus is not on any field. All fields should be updated.
    controller._sync_properties_panel()
    assert mock_properties.panel_updated is True
    assert mock_properties.values["name"] == "Initial Label"
    assert mock_properties.values["x"] == "10"

    # Scenario 2: Focus is on 'name'. Only name field should be preserved (not updated).
    mock_properties.focused_fields.add("name")
    mock_properties.values["name"] = "User Typed Name"  # simulate what user typed

    # Update workspace state with new server bounds/label
    comp_updated = Component(
        id=comp_id,
        number="1",
        label="New Server Label",
        bounds=Bounds(x=15, y=20, w=100, h=200),
        style=Style(),
        visibility=Visibility()
    )
    ws_updated = WorkspaceState(
         sessionId=uuid4(),
         components={comp_id: comp_updated}
    )
    client.state = ws_updated
    store.update_state("workspace", workspace_state=ws_updated)

    controller._sync_properties_panel()
    assert mock_properties.values["name"] == "User Typed Name"  # preserved!
    assert mock_properties.values["x"] == "15"  # updated!
