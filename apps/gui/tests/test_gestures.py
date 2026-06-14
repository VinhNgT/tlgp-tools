from uuid import uuid4

from gui.state import UIStateStore
from gui.views.gestures import GestureInterpreter
from gui.views.transformer import ViewportTransformer
from models import Bounds, Component, Style, Visibility


def test_hit_box_empty():
    store = UIStateStore()
    transformer = ViewportTransformer()
    gestures = GestureInterpreter(store, transformer)

    hit = gestures.hit_box(100.0, 100.0, [], [], 1.0, [], [])
    assert hit is None


def test_hit_box_contains_pointer():
    store = UIStateStore()
    transformer = ViewportTransformer()
    transformer.update_image_size(1000, 1000)
    transformer.rebuild_segments([])
    gestures = GestureInterpreter(store, transformer)

    comp = Component(
        id=uuid4(),
        number="1",
        label="Test Button",
        bounds=Bounds(x=50, y=50, w=100, h=100),
        style=Style(),
        visibility=Visibility(visible=True, locked=False),
    )

    # Pointer is inside bounds (zoom=1.0)
    hit = gestures.hit_box(100.0, 100.0, [comp], [], 1.0, [], [])
    assert hit is not None
    assert hit.id == comp.id

    # Pointer is outside bounds (zoom=1.0)
    hit_outside = gestures.hit_box(200.0, 200.0, [comp], [], 1.0, [], [])
    assert hit_outside is None


def test_hit_handle_when_selected():
    store = UIStateStore()
    transformer = ViewportTransformer()
    transformer.update_image_size(1000, 1000)
    transformer.rebuild_segments([])
    gestures = GestureInterpreter(store, transformer)

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
    handle = gestures.hit_handle(51.0, 51.0, [comp], 1.0, [], [])
    assert handle == "nw"

    # NE handle is at (150, 50). Close to it: (149.0, 50.0)
    handle_ne = gestures.hit_handle(149.0, 50.0, [comp], 1.0, [], [])
    assert handle_ne == "ne"

    # Far away -> no handle hit
    handle_none = gestures.hit_handle(100.0, 75.0, [comp], 1.0, [], [])
    assert handle_none is None


def test_gesture_zoom():
    from PIL import Image
    class MockCanvas:
        def __init__(self):
            self.full_pil_img = Image.new("RGB", (1000, 1000))
        def winfo_width(self):
            return 800
        def winfo_height(self):
            return 600

    store = UIStateStore()
    transformer = ViewportTransformer()
    transformer.update_image_size(1000, 1000)
    gestures = GestureInterpreter(store, transformer)

    canvas = MockCanvas()
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
    from PIL import Image
    from uuid import uuid4
    from models import WorkspaceState, ImageInfo
    class MockCanvas:
        def __init__(self):
            self.full_pil_img = Image.new("RGB", (1000, 1000))
            self._space_pan_active = False
            self.rect_coords = None
        def winfo_width(self):
            return 800
        def winfo_height(self):
            return 600
        def coords(self, item_id, *coords):
            self.rect_coords = coords
        def create_rectangle(self, *args, **kwargs):
            return 1
        def delete(self, item_id):
            pass
        def _active_boxes(self):
            return []

    store = UIStateStore()
    ws = WorkspaceState(
        sessionId=uuid4(),
        image=ImageInfo(filename="test.png", width=1000, height=1000)
    )
    store.update_state("workspace", workspace_state=ws)

    transformer = ViewportTransformer()
    transformer.update_image_size(1000, 1000)
    gestures = GestureInterpreter(store, transformer)

    canvas = MockCanvas()
    store.update_state("viewport", zoom_factor=1.0, pan_offset=(0.0, 0.0), current_mode="draw")

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


def test_gesture_on_release_create():
    from PIL import Image
    from uuid import uuid4
    from models import WorkspaceState, ImageInfo

    events_generated = []

    class MockCanvas:
        def __init__(self):
            self.full_pil_img = Image.new("RGB", (1000, 1000))
            self._space_pan_active = False
            self.rect_coords = None
            self.last_created_component = None
        def winfo_width(self): return 800
        def winfo_height(self): return 600
        def coords(self, item_id, *coords): self.rect_coords = coords
        def create_rectangle(self, *args, **kwargs): return 1
        def delete(self, item_id): pass
        def draw_boxes(self): pass
        def _active_boxes(self): return []
        def event_generate(self, event_name):
            events_generated.append(event_name)

    store = UIStateStore()
    ws = WorkspaceState(
        sessionId=uuid4(),
        image=ImageInfo(filename="test.png", width=1000, height=1000)
    )
    store.update_state("workspace", workspace_state=ws)

    transformer = ViewportTransformer()
    transformer.update_image_size(1000, 1000)
    gestures = GestureInterpreter(store, transformer)

    canvas = MockCanvas()
    store.update_state("viewport", zoom_factor=1.0, pan_offset=(0.0, 0.0), current_mode="draw")

    class MockEvent:
        def __init__(self, x, y, state=0):
            self.x = x
            self.y = y
            self.state = state

    gestures.on_click(canvas, MockEvent(10, 10), 10.0, 10.0)
    gestures.on_drag(canvas, MockEvent(110, 110), 110.0, 110.0)
    gestures.on_release(canvas, MockEvent(110, 110), 110.0, 110.0)

    assert "<<ComponentCreated>>" in events_generated
    assert canvas.last_created_component == {"x": 10, "y": 10, "w": 100, "h": 100}


def test_gesture_on_release_move_and_resize():
    from PIL import Image
    from uuid import uuid4
    from models import WorkspaceState, ImageInfo, Component, Bounds, Style, Visibility

    events_generated = []

    class MockCanvas:
        def __init__(self):
            self.full_pil_img = Image.new("RGB", (1000, 1000))
            self._space_pan_active = False
            self.last_moved_component = None
            self.last_resized_component = None
            self._selection = []
        def winfo_width(self): return 800
        def winfo_height(self): return 600
        def delete(self, item_id): pass
        def draw_boxes(self): pass
        def event_generate(self, event_name):
            events_generated.append(event_name)
        def _active_boxes(self):
            return self._selection
        def set_selection(self, sel):
            self._selection = sel
        def _get_children_bounds_union(self, box):
            return None

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
        components={comp.id: comp}
    )
    store.update_state("workspace", workspace_state=ws)
    store.update_state("viewport", selected_component_ids=[comp.id], current_mode="select")

    transformer = ViewportTransformer()
    transformer.update_image_size(1000, 1000)
    gestures = GestureInterpreter(store, transformer)

    canvas = MockCanvas()
    canvas._selection = [comp]

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

    assert "<<ComponentMoved>>" in events_generated
    assert canvas.last_moved_component == (comp, 150, 150)

    # Update component bounds to simulate the controller/backend applying the move
    comp.bounds.x = 150
    comp.bounds.y = 150

    # Resize simulation
    events_generated.clear()
    gestures.on_click(canvas, MockEvent(250, 200), 250.0, 200.0)
    assert gestures.is_dragging
    assert gestures.resize_handle == "e"

    gestures.on_drag(canvas, MockEvent(300, 200), 300.0, 200.0)
    gestures.on_release(canvas, MockEvent(300, 200), 300.0, 200.0)

    assert "<<ComponentResized>>" in events_generated
    assert canvas.last_resized_component == (comp, {"x": 150, "y": 150, "w": 150, "h": 100})


def test_double_click_cycles_overlapping_boxes():
    from PIL import Image
    from uuid import uuid4
    from models import WorkspaceState, ImageInfo, Component, Bounds, Style, Visibility
    import time

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
    store.update_state("viewport", selected_component_ids=[], current_mode="select", zoom_factor=1.0, pan_offset=(0.0, 0.0))

    transformer = ViewportTransformer()
    transformer.update_image_size(1000, 1000)
    gestures = GestureInterpreter(store, transformer)

    class MockCanvas:
        def __init__(self):
            self.full_pil_img = Image.new("RGB", (1000, 1000))
            self._space_pan_active = False
            self._selection = []
        def winfo_width(self): return 800
        def winfo_height(self): return 600
        def delete(self, item_id): pass
        def draw_boxes(self): pass
        def _active_boxes(self):
            return [comp1, comp2]
        def set_selection(self, sel):
            self._selection = sel
            store.update_state("selection", selected_component_ids=[b.id for b in sel])

    canvas = MockCanvas()

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

