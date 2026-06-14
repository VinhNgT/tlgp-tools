import time
from uuid import uuid4

import pytest
from gui.domain.transformer import ViewportTransformer
from gui.state import UIStateStore
from gui.views.gestures import GestureInterpreter
from models import Bounds, Component, ImageInfo, Style, Visibility, WorkspaceState
from PIL import Image


class MockCanvasContext:
    def __init__(self, store):
        self.store = store
        self.full_pil_img = Image.new("RGB", (1000, 1000))
        self.space_pan_active = False
        self.rect_coords = None
        self.temp_rect_id = None
        self.cursor_name = None
        self.active_boxes_list = []
        self._selection = []
        self.mock_precise_deltas = (0.0, 0.0)

        # Callbacks & signals recorded
        self.created_bounds = None
        self.moved_comp = None
        self.resized_comp = None
        self.drill_into_id = None
        self.context_menu_event = None
        self.context_menu_clicked = None

    @property
    def zoom_factor(self):
        return self.store.state.zoom_factor

    @property
    def pan_offset(self):
        return self.store.state.pan_offset

    @property
    def parent_stack(self):
        return self.store.state.parent_stack

    @property
    def selected_component_ids(self):
        return self.store.state.selected_component_ids

    @property
    def active_interaction(self):
        return self.store.state.active_interaction

    @property
    def workspace_state(self):
        return self.store.state.workspace_state

    @property
    def current_mode(self):
        return self.store.state.current_mode

    def get_active_boxes(self):
        return self.active_boxes_list

    def get_children_bounds_union(self, box):
        return None

    def set_cursor(self, cursor_type: str):
        self.cursor_name = cursor_type

    def create_rectangle(self, x1, y1, x2, y2, **kwargs):
        self.temp_rect_id = 1
        self.rect_coords = (x1, y1, x2, y2)
        return self.temp_rect_id

    def coords(self, item_id, x1, y1, x2, y2):
        self.rect_coords = (x1, y1, x2, y2)

    def delete(self, item_id):
        self.temp_rect_id = None

    def draw_boxes(self):
        pass

    def set_selection(self, boxes):
        self._selection = boxes
        self.store.update_state(
            "selection", selected_component_ids=[b.id for b in boxes]
        )

    def unfocus_properties_panel(self):
        self.set_selection([])

    def winfo_width(self):
        return 800

    def winfo_height(self):
        return 600

    def PreciseScrollDeltas(self, delta):
        return self.mock_precise_deltas

    def __str__(self):
        return "mock_canvas"

    # Callbacks
    def on_viewport_change_request(self, zoom, pan):
        self.store.update_state("viewport", zoom_factor=zoom, pan_offset=pan)

    def on_active_interaction_changed(self, active_int):
        self.store.update_state("selection", active_interaction=active_int)

    def on_component_created(self, bounds):
        self.created_bounds = bounds

    def on_component_resized(self, comp_id, bounds):
        self.resized_comp = (comp_id, bounds)

    def on_component_moved(self, comp_id, x, y):
        self.moved_comp = (comp_id, x, y)

    def on_request_context_menu(self, event, clicked):
        self.context_menu_event = event
        self.context_menu_clicked = clicked

    def drill_into(self, comp_id):
        self.drill_into_id = comp_id


def test_hit_box_empty():
    transformer = ViewportTransformer()
    gestures = GestureInterpreter(transformer)

    hit = gestures.hit_box(100.0, 100.0, [], [], 1.0, [], [], (0.0, 0.0))
    assert hit is None


def test_hit_box_contains_pointer():
    transformer = ViewportTransformer()
    transformer.update_image_size(1000, 1000)
    transformer.rebuild_segments([])
    gestures = GestureInterpreter(transformer)

    comp = Component(
        id=uuid4(),
        number="1",
        label="Test Button",
        bounds=Bounds(x=50, y=50, w=100, h=100),
        style=Style(),
        visibility=Visibility(visible=True, locked=False),
    )

    # Pointer is inside bounds (zoom=1.0)
    hit = gestures.hit_box(100.0, 100.0, [comp], [], 1.0, [], [], (0.0, 0.0))
    assert hit is not None
    assert hit.id == comp.id

    # Pointer is outside bounds (zoom=1.0)
    hit_outside = gestures.hit_box(200.0, 200.0, [comp], [], 1.0, [], [], (0.0, 0.0))
    assert hit_outside is None


def test_hit_handle_when_selected():
    transformer = ViewportTransformer()
    transformer.update_image_size(1000, 1000)
    transformer.rebuild_segments([])
    gestures = GestureInterpreter(transformer)

    comp = Component(
        id=uuid4(),
        number="1",
        label="Test Button",
        bounds=Bounds(
            x=50, y=50, w=100, h=50
        ),  # Top-left at (50, 50), Bottom-right at (150, 100)
        style=Style(),
        visibility=Visibility(visible=True, locked=False),
    )

    # NW handle is at (50, 50). Let's test close to it: (51.0, 51.0)
    handle = gestures.hit_handle(51.0, 51.0, [comp], 1.0, [], [], (0.0, 0.0))
    assert handle == "nw"

    # NE handle is at (150, 50). Close to it: (149.0, 50.0)
    handle_ne = gestures.hit_handle(149.0, 50.0, [comp], 1.0, [], [], (0.0, 0.0))
    assert handle_ne == "ne"

    # Far away -> no handle hit
    handle_none = gestures.hit_handle(100.0, 75.0, [comp], 1.0, [], [], (0.0, 0.0))
    assert handle_none is None


def test_gesture_zoom():

    store = UIStateStore()
    transformer = ViewportTransformer()
    transformer.update_image_size(1000, 1000)
    gestures = GestureInterpreter(transformer)

    canvas = MockCanvasContext(store)
    # Initial state
    store.update_state("viewport", zoom_factor=1.0, pan_offset=(0.0, 0.0))

    # Zoom in by 0.5 focusing on mouse at (400, 300)
    gestures.zoom(canvas, 0.5, mouse_pos=(400, 300))

    state = store.state
    assert state.zoom_factor == 1.5
    # The mouse point (400, 300) should remain at visual (400, 300).
    # Since initial zoom was 1.0 and pan was 0.0, absolute coordinate under mouse was (400, 300).
    # Under new zoom 1.5, absolute (400, 300) maps to:
    # 400 * 1.5 + pan_x = 400 => pan_x = 400 - 600 = -200
    # 300 * 1.5 + pan_y = 300 => pan_y = 300 - 450 = -150
    assert state.pan_offset == (-200.0, -150.0)


def test_gesture_draw_clamped():

    store = UIStateStore()
    ws = WorkspaceState(
        sessionId=uuid4(), image=ImageInfo(filename="test.png", width=1000, height=1000)
    )
    store.update_state("workspace", workspace_state=ws)

    transformer = ViewportTransformer()
    transformer.update_image_size(1000, 1000)
    gestures = GestureInterpreter(transformer)

    canvas = MockCanvasContext(store)
    store.update_state(
        "viewport", zoom_factor=1.0, pan_offset=(0.0, 0.0), current_mode="draw"
    )

    class MockEvent:
        def __init__(self, x, y, state=0):
            self.x = x
            self.y = y
            self.state = state

    gestures.on_click(canvas, MockEvent(-50, -50), -50.0, -50.0)
    assert gestures.temp_rect_id is not None

    # Drag to 1200, 1200 (well outside image bounds 0..1000)
    gestures.on_drag(canvas, MockEvent(1200, 1200), 1200.0, 1200.0)

    # Coords of guide rectangle should be clamped to image boundary: 0, 0, 1000, 1000
    assert canvas.rect_coords == (0.0, 0.0, 1000.0, 1000.0)


def test_gesture_on_release_draw():

    store = UIStateStore()
    ws = WorkspaceState(
        sessionId=uuid4(), image=ImageInfo(filename="test.png", width=1000, height=1000)
    )
    store.update_state("workspace", workspace_state=ws)

    transformer = ViewportTransformer()
    transformer.update_image_size(1000, 1000)
    gestures = GestureInterpreter(transformer)

    canvas = MockCanvasContext(store)
    store.update_state(
        "viewport", zoom_factor=1.0, pan_offset=(0.0, 0.0), current_mode="draw"
    )

    class MockEvent:
        def __init__(self, x, y, state=0):
            self.x = x
            self.y = y
            self.state = state

    gestures.on_click(canvas, MockEvent(10, 10), 10.0, 10.0)
    gestures.on_drag(canvas, MockEvent(110, 110), 110.0, 110.0)
    gestures.on_release(canvas, MockEvent(110, 110), 110.0, 110.0)

    assert canvas.created_bounds == {"x": 10, "y": 10, "w": 100, "h": 100}


def test_gesture_on_release_move_and_resize():

    store = UIStateStore()
    comp = Component(
        id=uuid4(),
        number="1",
        label="Comp",
        bounds=Bounds(x=100, y=100, w=100, h=100),
        style=Style(),
        visibility=Visibility(visible=True, locked=False),
    )
    ws = WorkspaceState(
        sessionId=uuid4(),
        image=ImageInfo(filename="test.png", width=1000, height=1000),
        components={comp.id: comp},
    )
    store.update_state("workspace", workspace_state=ws)
    store.update_state(
        "viewport", selected_component_ids=[comp.id], current_mode="select"
    )

    transformer = ViewportTransformer()
    transformer.update_image_size(1000, 1000)
    gestures = GestureInterpreter(transformer)

    canvas = MockCanvasContext(store)
    canvas._selection = [comp]
    canvas.active_boxes_list = [comp]

    class MockEvent:
        def __init__(self, x, y, state=0):
            self.x = x
            self.y = y
            self.state = state

    # Move simulation
    gestures.on_click(canvas, MockEvent(150, 150), 150.0, 150.0)
    assert gestures.is_dragging
    assert gestures.resize_handle is None

    gestures.on_drag(canvas, MockEvent(200, 200), 200.0, 200.0)
    gestures.on_release(canvas, MockEvent(200, 200), 200.0, 200.0)

    assert canvas.moved_comp == (str(comp.id), 150, 150)

    # Update component bounds to simulate the controller/backend applying the move
    comp.bounds.x = 150
    comp.bounds.y = 150

    # Resize simulation
    gestures.on_click(canvas, MockEvent(250, 200), 250.0, 200.0)
    assert gestures.is_dragging
    assert gestures.resize_handle == "e"

    gestures.on_drag(canvas, MockEvent(300, 200), 300.0, 200.0)
    gestures.on_release(canvas, MockEvent(300, 200), 300.0, 200.0)

    assert canvas.resized_comp == (
        str(comp.id),
        {"x": 150, "y": 150, "w": 150, "h": 100},
    )


def test_double_click_cycles_overlapping_boxes():

    store = UIStateStore()

    # Create two overlapping components
    # Comp 1: (50, 50) to (150, 150)
    comp1 = Component(
        id=uuid4(),
        number="1",
        label="Comp 1",
        bounds=Bounds(x=50, y=50, w=100, h=100),
        style=Style(),
        visibility=Visibility(visible=True, locked=False),
    )
    # Comp 2: (80, 80) to (180, 180) - drawn second (top-most)
    comp2 = Component(
        id=uuid4(),
        number="2",
        label="Comp 2",
        bounds=Bounds(x=80, y=80, w=100, h=100),
        style=Style(),
        visibility=Visibility(visible=True, locked=False),
    )

    ws = WorkspaceState(
        sessionId=uuid4(),
        image=ImageInfo(filename="test.png", width=1000, height=1000),
        components={comp1.id: comp1, comp2.id: comp2},
        rootComponents=[comp1.id, comp2.id],
    )
    store.update_state("workspace", workspace_state=ws)
    store.update_state(
        "viewport",
        selected_component_ids=[],
        current_mode="select",
        zoom_factor=1.0,
        pan_offset=(0.0, 0.0),
    )

    transformer = ViewportTransformer()
    transformer.update_image_size(1000, 1000)
    gestures = GestureInterpreter(transformer)

    canvas = MockCanvasContext(store)
    canvas.active_boxes_list = [comp1, comp2]

    class MockEvent:
        def __init__(self, x, y, state=0):
            self.x = x
            self.y = y
            self.state = state

    # Click in the overlap region (100, 100)
    # 1. First Click (Selection Click)
    gestures.on_click(canvas, MockEvent(100, 100), 100.0, 100.0)
    # Comp 2 is top-most (last in active_boxes list), so it should be selected first.
    assert len(canvas._selection) == 1
    assert canvas._selection[0].id == comp2.id
    assert store.state.selected_component_ids == [comp2.id]

    # 2. Second Click (Double Click relative to click 1)
    # No cycling should occur because click 1 was a selection click.
    gestures.on_click(canvas, MockEvent(100, 100), 100.0, 100.0)
    assert len(canvas._selection) == 1
    assert canvas._selection[0].id == comp2.id

    # 3. Third Click (Double Click relative to click 2)
    # Cycling should occur because click 2 was not a selection click.
    gestures.last_click_time = time.time() - 0.1
    gestures.on_click(canvas, MockEvent(100, 100), 100.0, 100.0)
    # Selection should cycle to comp1
    assert len(canvas._selection) == 1
    assert canvas._selection[0].id == comp1.id
    assert store.state.selected_component_ids == [comp1.id]
    # It should also start dragging the newly selected box
    assert gestures.is_dragging
    assert gestures.drag_orig_bounds == (50, 50, 150, 150)

    # 4. Fourth Click (Double Click relative to click 3)
    # No cycling should occur because click 3 was a selection click (changed from comp2 to comp1).
    gestures.last_click_time = time.time() - 0.1
    gestures.on_click(canvas, MockEvent(100, 100), 100.0, 100.0)
    assert len(canvas._selection) == 1
    assert canvas._selection[0].id == comp1.id

    # 5. Fifth Click (Double Click relative to click 4)
    # Cycling should occur because click 4 was not a selection click.
    gestures.last_click_time = time.time() - 0.1
    gestures.on_click(canvas, MockEvent(100, 100), 100.0, 100.0)
    # Selection cycles back to comp2
    assert len(canvas._selection) == 1
    assert canvas._selection[0].id == comp2.id


def test_gesture_on_scroll_vertical_and_horizontal():
    store = UIStateStore()
    transformer = ViewportTransformer()
    transformer.update_image_size(1000, 1000)
    gestures = GestureInterpreter(transformer)

    canvas = MockCanvasContext(store)
    store.update_state("viewport", zoom_factor=1.0, pan_offset=(0.0, 0.0))

    class MockEvent:
        def __init__(self, delta=0, num=0, state=0, x=400, y=300):
            self.delta = delta
            self.num = num
            self.state = state
            self.x = x
            self.y = y

    # Vertical mouse wheel scroll (delta=120)
    gestures.on_scroll(canvas, MockEvent(delta=120))
    assert store.state.pan_offset == (0.0, -120.0)

    # Horizontal mouse wheel scroll (Shift + delta=120)
    store.update_state("viewport", pan_offset=(0.0, 0.0))
    gestures.on_scroll(canvas, MockEvent(delta=120, state=0x0001))  # Shift
    assert store.state.pan_offset == (-120.0, 0.0)

    # Linux scroll up (Button-4)
    store.update_state("viewport", pan_offset=(0.0, 0.0))
    gestures.on_scroll(canvas, MockEvent(num=4))
    assert store.state.pan_offset == (0.0, -40.0)

    # Linux scroll down (Button-5)
    store.update_state("viewport", pan_offset=(0.0, 0.0))
    gestures.on_scroll(canvas, MockEvent(num=5))
    assert store.state.pan_offset == (0.0, 40.0)


def test_gesture_on_scroll_zoom():
    store = UIStateStore()
    transformer = ViewportTransformer()
    transformer.update_image_size(1000, 1000)
    gestures = GestureInterpreter(transformer)

    canvas = MockCanvasContext(store)
    store.update_state("viewport", zoom_factor=1.0, pan_offset=(0.0, 0.0))

    class MockEvent:
        def __init__(self, delta=0, num=0, state=0, x=400, y=300):
            self.delta = delta
            self.num = num
            self.state = state
            self.x = x
            self.y = y

    # Ctrl + scroll wheel zoom in (delta=120)
    gestures.on_scroll(canvas, MockEvent(delta=120, state=0x0004))  # Ctrl
    # delta / 1200.0 = 0.1 zoom delta. Zoom increases from 1.0 to 1.1.
    assert store.state.zoom_factor == pytest.approx(1.1)
    # Zoom focus center shift math:
    # new_pan_x = 400 - 400 * 1.1 = -40
    # new_pan_y = 300 - 300 * 1.1 = -30
    assert store.state.pan_offset == pytest.approx((-40.0, -30.0))


def test_gesture_on_touchpad_scroll():
    store = UIStateStore()
    transformer = ViewportTransformer()
    transformer.update_image_size(1000, 1000)
    gestures = GestureInterpreter(transformer)

    canvas = MockCanvasContext(store)
    canvas.mock_precise_deltas = (15.5, -20.0)
    store.update_state("viewport", zoom_factor=1.0, pan_offset=(100.0, 100.0))

    class MockEvent:
        def __init__(self, widget, delta=0, state=0, x=400, y=300):
            self.widget = widget
            self.delta = delta
            self.state = state
            self.x = x
            self.y = y

    # Touchpad scroll (standard pan)
    # Event widget must match canvas to process touchpad scroll
    event = MockEvent(widget=canvas, delta=-120)
    res = gestures.on_touchpad_scroll(canvas, event)
    assert res == "break"
    assert store.state.pan_offset == pytest.approx((115.5, 80.0))

    # Touchpad scroll (pinch to zoom)
    store.update_state("viewport", zoom_factor=1.0, pan_offset=(0.0, 0.0))
    canvas.mock_precise_deltas = (
        0.0,
        10.0,
    )  # delta_y = 10.0 -> zoom delta = 10 * 0.01 = 0.1
    event_zoom = MockEvent(widget=canvas, delta=120, state=0x0004)  # Ctrl
    res_zoom = gestures.on_touchpad_scroll(canvas, event_zoom)
    assert res_zoom == "break"
    assert store.state.zoom_factor == pytest.approx(1.1)
