import io
from unittest.mock import MagicMock
from uuid import UUID, uuid4

from gui.controllers.controller import AppController
from gui.dialog_service import DialogService
from gui.state import UIStateStore
from models import Bounds, Component, ImageInfo, Style, Visibility, WorkspaceState
from PIL import Image


class MockCanvasView:
    def __init__(self):
        self.on_import_zip = None
        self.on_import_image = None
        self.on_selection_changed = None
        self.on_drill_into = None
        self.on_drill_out = None
        self.on_component_moved = None
        self.on_component_resized = None
        self.on_component_created = None
        self.on_request_context_menu = None
        self.on_viewport_change_request = None
        self.on_active_interaction_changed = None
        self.on_selection_ids_changed = None
        self.on_viewport_size_changed = None
        self.on_canvas_mode_change_request = None

        self._canvas_image = None
        self._is_canvas_dragging = False
        self.canvas_workspace_state = None
        self.canvas_active_interaction = None
        self.canvas_selected_ids = None
        self.canvas_zoom_factor = 1.0
        self.canvas_pan_offset = (0.0, 0.0)
        self.canvas_parent_stack = []
        self.canvas_current_mode = "select"
        self.canvas_selection = []
        self.drill_into_id = None
        self.drill_out_called = False
        self.zoom_focus_target_called = False
        self.toggle_labels_visibility_called = False

        self.full_pil_img = None
        self.gestures = MagicMock()
        self.gestures.is_dragging = False

    @property
    def canvas_image(self):
        return self._canvas_image

    @canvas_image.setter
    def canvas_image(self, img):
        self._canvas_image = img

    def set_background_image(self, img, unreachable: bool = False):
        self._canvas_image = img
        self.canvas_unreachable = unreachable

    def set_interactive(self, enabled: bool, unreachable: bool = False):
        self.canvas_unreachable = unreachable

    @property
    def is_canvas_dragging(self) -> bool:
        return self._is_canvas_dragging

    @is_canvas_dragging.setter
    def is_canvas_dragging(self, val: bool):
        self._is_canvas_dragging = val
        self.gestures.is_dragging = val

    def fit_to_screen(self):
        pass

    def set_workspace_state(self, state, active_interaction=None):
        self.canvas_workspace_state = state
        self.canvas_active_interaction = active_interaction

    def set_selection_state(self, selected_ids, active_interaction=None):
        self.canvas_selected_ids = selected_ids
        self.canvas_active_interaction = active_interaction

    def set_viewport_state(
        self,
        zoom_factor,
        pan_offset,
        parent_stack,
        current_mode,
        active_interaction=None,
    ):
        self.canvas_zoom_factor = zoom_factor
        self.canvas_pan_offset = pan_offset
        self.canvas_parent_stack = parent_stack
        self.canvas_current_mode = current_mode
        self.canvas_active_interaction = active_interaction

    def set_selection(self, boxes):
        self.canvas_selection = boxes

    def zoom_focus_target(self):
        self.zoom_focus_target_called = True

    def toggle_labels_visibility(self):
        self.toggle_labels_visibility_called = True

    def drill_out(self):
        self.drill_out_called = True

    def drill_into(self, comp_id):
        self.drill_into_id = comp_id


class MockTreeView:
    def __init__(self):
        self.on_component_selected = None
        self.tree_nodes = []
        self.tree_selection = None

    def rebuild_tree(self, nodes):
        self.tree_nodes = nodes

    def select_component(self, comp_id):
        self.tree_selection = comp_id

    def clear_selection(self):
        self.tree_selection = None


class MockPropertiesView:
    def __init__(self):
        self.on_property_changed = None
        self.on_focus_changed = None
        self.properties_box_id = None
        self.properties_label = None
        self.properties_x = None
        self.properties_y = None
        self.properties_w = None
        self.properties_h = None
        self.properties_is_visible = None
        self.properties_is_locked = None
        self.properties_is_effectively_locked = None
        self.properties_pill_corner = None
        self.properties_disabled = False
        self.properties_focused_fields = set()
        self.properties_values = {}

    def update_properties_panel(
        self,
        box_id,
        label,
        x,
        y,
        w,
        h,
        is_visible,
        is_locked,
        is_effectively_locked,
        pill_corner,
    ):
        self.properties_box_id = box_id
        self.properties_label = label
        self.properties_x = x
        self.properties_y = y
        self.properties_w = w
        self.properties_h = h
        self.properties_is_visible = is_visible
        self.properties_is_locked = is_locked
        self.properties_is_effectively_locked = is_effectively_locked
        self.properties_pill_corner = pill_corner

    def is_field_focused(self, field_name):
        return field_name in self.properties_focused_fields

    def update_field_value(self, field_name, value):
        self.properties_values[field_name] = value

    def disable_properties_fields(self):
        self.properties_disabled = True


class MockAppWindow:
    def __init__(self):
        self.canvas = MockCanvasView()
        self.tree = MockTreeView()
        self.properties = MockPropertiesView()

        self.report_callback_exception = None
        self.status_text = ""
        self.zoom_pct_str = ""
        self.breadcrumbs_text = ""
        self.mode_str = "select"
        self.on_mode_change_request = None
        self.on_undo_request = None
        self.on_redo_request = None
        self.on_delete_request = None
        self.on_back_request = None
        self.on_import_zip_request = None
        self.on_import_image_request = None
        self.on_export_zip_request = None
        self.on_open_cut_editor_request = None
        self.on_open_screen_info_request = None
        self.on_enter_pressed = None
        self.on_escape_pressed = None
        self.context_menu_pos = None
        self.context_menu_items = None
        self.ui_interactive_enabled = True
        self.ui_interactive_unreachable = False
        self.status_is_error = False

    def update_status(self, text: str, is_error: bool = False):
        self.status_text = text
        self.status_is_error = is_error

    def update_zoom_display(self, zoom_factor: float):
        zoom_pct = int(zoom_factor * 100)
        self.zoom_pct_str = f"{zoom_pct}%"

    def update_breadcrumbs(self, breadcrumbs: list[str]):
        if breadcrumbs:
            self.breadcrumbs_text = " / ".join(["Root"] + breadcrumbs)
        else:
            self.breadcrumbs_text = "Root"

    def set_canvas_image(self, img, unreachable: bool = False):
        self.canvas.canvas_image = img
        self.canvas.canvas_unreachable = unreachable
        self.set_ui_interactive(img is not None, unreachable=unreachable)

    def set_ui_interactive(self, enabled: bool, unreachable: bool = False):
        self.ui_interactive_enabled = enabled
        self.ui_interactive_unreachable = unreachable

    def after(self, ms, func):
        func()

    def show_context_menu(self, x_root: int, y_root: int, items: list[dict]):
        self.context_menu_pos = (x_root, y_root)
        self.context_menu_items = items

    def set_mode_str(self, mode: str):
        self.mode_str = mode


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

        class MockProgressIndicator:
            def dismiss(self):
                pass

        return MockProgressIndicator()

    def show_cut_editor(self, parent, image, initial_cuts, components):
        self.cut_editor_shown = True
        return self.mock_cut_lines

    def show_screen_info(self, parent, screen_name, description):
        self.screen_info_shown = True
        return self.mock_screen_info


class MockEngineClient:
    def __init__(self):
        self.state = None
        self.api_url = "http://mock_url"
        self.on_state_changed = None
        self.on_error = None
        self.imported_zip = None
        self.imported_image = None
        self.exported = False
        self.updated_cut_lines = None
        self.updated_screen_info = None
        self.connected = True
        self.connection_failed = False

    def import_zip(self, path, on_complete):
        self.imported_zip = path
        on_complete(None)

    def import_image(self, path, on_complete):
        self.imported_image = path
        on_complete(None)

    def export_zip(self, path, on_complete):
        self.exported = True
        with open(path, "wb") as f:
            f.write(b"mock zip bytes")
        on_complete(None)

    def update_cut_lines(self, lines):
        self.updated_cut_lines = lines

    def update_screen_info(self, name, description):
        self.updated_screen_info = (name, description)

    def add_component(self, label: str, bounds: dict, parent_id: str | None = None) -> str:
        return str(uuid4())

    def move_component(self, comp_id, x, y):
        pass

    def update_component(self, comp_id, **kwargs):
        pass

    def delete_component(self, comp_id):
        pass

    def get_raw_image_data(self) -> bytes:
        img = Image.new("RGB", (10, 10))
        buf = io.BytesIO()
        img.save(buf, format="PNG")
        return buf.getvalue()


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
    view.canvas.canvas_image = Image.new("RGB", (100, 100))
    view.canvas.full_pil_img = view.canvas.canvas_image
    dialogs = MockDialogService()
    dialogs.mock_save_path = str(tmp_path / "mock_output.zip")

    controller = AppController(client, store, view, dialogs)
    controller._on_export_zip_request()

    assert client.exported is True
    assert dialogs.importing_dialog_shown is True
    assert len(dialogs.infos) == 1
    assert dialogs.infos[0][0] == "Export Successful"


def test_controller_open_cut_editor():
    store = UIStateStore()
    client = MockEngineClient()
    view = MockAppWindow()
    # Mock image info in workspace state
    ws = WorkspaceState(
        sessionId=uuid4(), image=ImageInfo(filename="test.png", width=1000, height=1000)
    )
    store.update_state("workspace", workspace_state=ws)
    view.canvas.canvas_image = Image.new("RGB", (1000, 1000))
    view.canvas.full_pil_img = view.canvas.canvas_image

    dialogs = MockDialogService()

    controller = AppController(client, store, view, dialogs)
    controller._on_open_cut_editor_request()

    assert dialogs.cut_editor_shown is True
    assert client.updated_cut_lines == [100, 200]


def test_controller_active_interaction_bounds_matching():

    store = UIStateStore()
    client = MockEngineClient()
    view = MockAppWindow()

    view.canvas.is_canvas_dragging = False
    view.canvas.canvas_image = None
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
        visibility=Visibility(),
    )
    ws_match = WorkspaceState(sessionId=uuid4(), components={comp_id: comp_match})
    client.state = ws_match

    # Scenario 1: Dragging is active. active_interaction should be preserved even if bounds match.
    view.canvas.is_canvas_dragging = True
    controller._apply_state_sync()
    assert store.state.active_interaction == {comp_id: transient_bounds}

    # Scenario 2: Dragging is inactive. Bounds match. active_interaction should be cleared.
    view.canvas.is_canvas_dragging = False
    controller._apply_state_sync()
    assert store.state.active_interaction is None


def test_controller_properties_input_preservation():

    store = UIStateStore()
    client = MockEngineClient()
    view = MockAppWindow()

    controller = AppController(client, store, view, MockDialogService())

    comp_id = uuid4()
    comp = Component(
        id=comp_id,
        number="1",
        label="Initial Label",
        bounds=Bounds(x=10, y=20, w=100, h=200),
        style=Style(),
        visibility=Visibility(),
    )
    ws = WorkspaceState(sessionId=uuid4(), components={comp_id: comp})
    client.state = ws
    store.update_state("workspace", workspace_state=ws)
    store.update_state("selection", selected_component_ids=[comp_id])

    # Scenario 1: Focus is not on any field. All fields should be updated.
    controller._on_selection_updated()
    assert view.properties.properties_box_id == str(comp_id)
    assert view.properties.properties_label == "Initial Label"
    assert view.properties.properties_x == 10
    assert view.properties.properties_y == 20
    assert view.properties.properties_w == 100
    assert view.properties.properties_h == 200
    assert view.properties.properties_is_visible is True
    assert view.properties.properties_is_locked is False
    assert view.properties.properties_pill_corner == "top_left"
    assert view.properties.properties_values["name"] == "Initial Label"
    assert view.properties.properties_values["x"] == "10"

    # Scenario 2: Focus is on 'name'. Only name field should be preserved (not updated).
    view.properties.properties_focused_fields.add("name")
    view.properties.properties_values["name"] = (
        "User Typed Name"  # simulate what user typed
    )

    # Update workspace state with new server bounds/label
    comp_updated = Component(
        id=comp_id,
        number="1",
        label="New Server Label",
        bounds=Bounds(x=15, y=20, w=100, h=200),
        style=Style(),
        visibility=Visibility(),
    )
    ws_updated = WorkspaceState(sessionId=uuid4(), components={comp_id: comp_updated})
    client.state = ws_updated
    store.update_state("workspace", workspace_state=ws_updated)

    controller._on_workspace_updated()
    assert view.properties.properties_values["name"] == "User Typed Name"  # preserved!
    assert view.properties.properties_values["x"] == "15"  # updated!


def test_controller_sidebar_tree_structure():

    store = UIStateStore()
    client = MockEngineClient()
    view = MockAppWindow()
    controller = AppController(client, store, view, MockDialogService())

    # Create root component and child component
    root_id = uuid4()
    child_id = uuid4()

    root_comp = Component(
        id=root_id,
        number="1",
        label="Root Comp",
        bounds=Bounds(x=0, y=0, w=100, h=100),
        style=Style(),
        visibility=Visibility(visible=True, locked=False),
        childrenIds=[child_id],
    )

    child_comp = Component(
        id=child_id,
        number="",
        label="Child Comp",
        bounds=Bounds(x=10, y=10, w=50, h=50),
        style=Style(),
        visibility=Visibility(visible=False, locked=True),
        parentId=root_id,
    )

    ws = WorkspaceState(
        sessionId=uuid4(),
        components={root_id: root_comp, child_id: child_comp},
        rootComponents=[root_id],
    )

    client.state = ws
    store.update_state("workspace", workspace_state=ws)

    # Trigger workspace sync, which builds tree nodes
    controller._on_workspace_updated()

    # Check constructed node tree structure passed to the view
    assert view.tree.tree_nodes is not None
    assert len(view.tree.tree_nodes) == 1

    root_node = view.tree.tree_nodes[0]
    assert root_node["id"] == str(root_id)
    assert root_node["text"] == "1 Root Comp"
    assert len(root_node["children"]) == 1

    child_node = root_node["children"][0]
    assert child_node["id"] == str(child_id)
    assert child_node["text"] == "Child Comp"
    assert "hidden" in child_node["tags"]
    assert "locked" in child_node["tags"]
    assert len(child_node["children"]) == 0


def test_controller_properties_focus_decoupling():
    store = UIStateStore()
    client = MockEngineClient()
    view = MockAppWindow()

    # Instantiate controller to bind callback
    _controller = AppController(client, store, view, MockDialogService())

    # Verify initial state of viewport.text_focused is False
    assert store.state.text_focused is False

    # Simulate properties focus event triggering callback
    assert view.properties.on_focus_changed is not None
    view.properties.on_focus_changed(True)
    assert store.state.text_focused is True

    # Simulate properties focus lost
    view.properties.on_focus_changed(False)
    assert store.state.text_focused is False


def test_controller_keyboard_shortcuts_decoupling():
    store = UIStateStore()
    client = MockEngineClient()
    view = MockAppWindow()

    # Instantiate controller
    _controller = AppController(client, store, view, MockDialogService())

    # Set up some state
    comp_id = uuid4()
    comp = Component(
        id=comp_id,
        number="1",
        label="Test Comp",
        bounds=Bounds(x=10, y=20, w=100, h=200),
        style=Style(),
        visibility=Visibility(),
    )
    ws = WorkspaceState(sessionId=uuid4(), components={comp_id: comp})
    store.update_state("workspace", workspace_state=ws)
    store.update_state("selection", selected_component_ids=[comp_id])

    # Trigger enter shortcut callback
    res = view.on_enter_pressed()
    assert res == "break"
    assert view.canvas.drill_into_id == comp_id

    # Verify escape shortcut when parent stack is empty
    assert store.state.parent_stack == []
    res_esc = view.on_escape_pressed()
    assert res_esc is None
    assert view.canvas.drill_out_called is False

    # Verify escape shortcut when parent stack has items
    store.update_state("viewport", parent_stack=[uuid4()])
    res_esc2 = view.on_escape_pressed()
    assert res_esc2 == "break"
    assert view.canvas.drill_out_called is True


def test_controller_active_interaction_decoupling():
    store = UIStateStore()
    client = MockEngineClient()
    view = MockAppWindow()

    # Instantiate controller to bind callbacks
    _controller = AppController(client, store, view, MockDialogService())

    # 1. Verify active interaction changed callback updates store and triggers update_canvas_selection
    comp_id = uuid4()
    bounds = Bounds(x=10, y=20, w=100, h=150)
    active_int = {comp_id: bounds}

    assert view.canvas.on_active_interaction_changed is not None
    view.canvas.on_active_interaction_changed(active_int)

    # The store's active_interaction should be updated
    assert store.state.active_interaction == active_int

    # The update_canvas_selection should have been called with the updated active_interaction
    assert view.canvas.canvas_selected_ids == []
    assert view.canvas.canvas_active_interaction == active_int

    # 2. Verify state sync workspace update triggers update_canvas_workspace with active_interaction
    ws = WorkspaceState(
        sessionId=uuid4(),
        image=ImageInfo(filename="test.png", width=1000, height=1000),
    )
    store.update_state("workspace", workspace_state=ws)

    assert view.canvas.canvas_workspace_state == ws
    assert view.canvas.canvas_active_interaction == active_int


def test_controller_context_menu_generation():
    store = UIStateStore()
    client = MockEngineClient()
    view = MockAppWindow()
    dialogs = MockDialogService()
    controller = AppController(client, store, view, dialogs)

    # Mock canvas image presence
    view.canvas.canvas_image = Image.new("RGB", (100, 100))
    view.canvas.full_pil_img = view.canvas.canvas_image

    comp_id = uuid4()
    clicked = Component(
        id=comp_id,
        number="5",
        label="Test Button",
        bounds=Bounds(x=10, y=10, w=50, h=50),
        style=Style(),
        visibility=Visibility(visible=True, locked=False),
    )

    # Simulate a canvas right click event
    class MockEvent:
        def __init__(self, x, y):
            self.x_root = x
            self.y_root = y

    event = MockEvent(100, 200)
    controller._on_canvas_context_menu(event, clicked)

    assert view.context_menu_pos == (100, 200)
    assert view.context_menu_items is not None

    # Check that expected items are generated
    labels = [
        item.get("label")
        for item in view.context_menu_items
        if not item.get("separator")
    ]
    assert "Drill into Component 5" in labels
    assert "Hide Component" in labels
    assert "Lock Component" in labels
    assert "Delete (Delete)" in labels
    assert "Focus Target" in labels
    assert "Toggle Labels (T)" in labels

def test_controller_state_sync_triggers_updates():
    store = UIStateStore()
    client = MockEngineClient()
    view = MockAppWindow()
    dialogs = MockDialogService()

    controller = AppController(client, store, view, dialogs)

    # Provide an initial state with an image payload
    session_id = uuid4()
    ws = WorkspaceState(
        sessionId=session_id,
        image=ImageInfo(filename="test.png", width=1000, height=1000),
        components={}
    )

    client.state = ws

    # Simulate API client triggering the callback
    controller._on_state_sync_received()

    # Verify Store Updated
    assert store.state.workspace_state == ws

    # Verify Canvas updated (via store subscription)
    assert view.canvas.canvas_workspace_state == ws

    # Verify loaded session id is tracked
    assert controller._loaded_session_id == str(session_id)

    # Verify image fetching triggered (because image is set but canvas image was none)
    # The mock client returns a dummy image byte array in get_raw_image_data
    assert view.canvas.canvas_image is not None
    assert view.canvas.canvas_image.width == 10  # Mock returns 10x10 image

    # Null state handling (disconnect)
    client.state = None
    controller._on_state_sync_received()

    assert store.state.workspace_state is None
    assert controller._loaded_session_id is None


def test_controller_engine_unreachable():
    store = UIStateStore()
    client = MockEngineClient()
    view = MockAppWindow()
    dialogs = MockDialogService()

    # Configure client to be in an unreachable/failed connection state
    client.state = None
    client.connected = False
    client.connection_failed = True

    controller = AppController(client, store, view, dialogs)
    controller._on_state_sync_received()

    # Status should display unreachable text and be set as error
    assert "Engine unreachable" in view.status_text
    assert view.status_is_error is True
    # Canvas image should be cleared and set to unreachable welcome screen
    assert view.canvas.canvas_image is None
    assert view.canvas.canvas_unreachable is True
    assert view.ui_interactive_unreachable is True
    assert view.ui_interactive_enabled is False


def test_controller_on_component_created():
    store = UIStateStore()
    client = MockEngineClient()
    view = MockAppWindow()
    dialogs = MockDialogService()

    generated_uuid_str = None

    def mock_add(label, bounds, parent_id=None):
        nonlocal generated_uuid_str
        generated_uuid_str = str(uuid4())
        return generated_uuid_str

    client.add_component = mock_add

    controller = AppController(client, store, view, dialogs)

    # Trigger component creation
    bounds = {"x": 50, "y": 60, "w": 70, "h": 80}
    controller._on_component_created(bounds)

    # Verify the generated component is selected immediately
    assert generated_uuid_str is not None
    generated_uuid = UUID(generated_uuid_str)
    assert store.state.selected_component_ids == [generated_uuid]
    assert generated_uuid in controller.pending_created_ids
    assert view.mode_str == "select"
