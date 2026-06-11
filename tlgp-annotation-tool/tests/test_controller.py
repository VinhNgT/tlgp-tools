"""Tests for SessionController: navigation, selection, box operations, overlaps."""

import pytest
from unittest.mock import MagicMock
from tlgp_annotation_tool.models import AnnotationBox, ScreenSession
from tlgp_annotation_tool.controller import SessionController, NavigationContext


def _box(id, x1=0, y1=0, x2=100, y2=100, children=None):
    return AnnotationBox(
        id=id, label=f"Box {id}",
        x1=x1, y1=y1, x2=x2, y2=y2,
        children=children or [],
    )


def _session(*boxes, cut_lines=None):
    return ScreenSession(
        screen_name="Test",
        components=list(boxes),
        cut_lines=cut_lines or [],
    )


# ── NavigationContext ─────────────────────────────────────────────────


class TestNavigationContext:
    def test_depth_at_root(self):
        nav = NavigationContext()
        assert nav.depth == 0

    def test_current_parent_at_root(self):
        nav = NavigationContext()
        assert nav.current_parent is None

    def test_breadcrumb_at_root(self):
        nav = NavigationContext()
        assert nav.breadcrumb() == "Root"

    def test_depth_after_drill(self):
        box = _box(1)
        nav = NavigationContext(parent_stack=[box])
        assert nav.depth == 1
        assert nav.current_parent is box

    def test_breadcrumb_chain(self):
        b1 = _box(1)
        b1.label = "Header"
        b2 = _box(2)
        b2.label = "Title"
        nav = NavigationContext(parent_stack=[b1, b2])
        assert nav.breadcrumb() == "Header › Title"

    def test_copy_is_independent(self):
        box = _box(1)
        nav = NavigationContext(parent_stack=[box])
        nav_copy = nav.copy()
        nav_copy.parent_stack.clear()
        assert nav.depth == 1  # original unaffected


# ── Active List & Navigation ──────────────────────────────────────────


class TestControllerNavigation:
    def test_active_list_at_root(self):
        b1, b2 = _box(1), _box(2)
        ctrl = SessionController(_session(b1, b2))
        assert ctrl.active_list() == [b1, b2]

    def test_drill_into(self):
        child = _box(1, x1=20, y1=20, x2=80, y2=80)
        parent = _box(1, children=[child])
        ctrl = SessionController(_session(parent))

        ctrl.drill_into(parent)
        assert ctrl.nav.depth == 1
        assert ctrl.active_list() == [child]
        assert ctrl.selected_boxes == []

    def test_drill_out(self):
        child = _box(1)
        parent = _box(1, children=[child])
        ctrl = SessionController(_session(parent))

        ctrl.drill_into(parent)
        ctrl.drill_out()
        assert ctrl.nav.depth == 0
        assert ctrl.selected_boxes == [parent]

    def test_drill_out_at_root_noop(self):
        ctrl = SessionController(_session(_box(1)))
        ctrl.drill_out()  # should not raise
        assert ctrl.nav.depth == 0

    def test_drill_to_root(self):
        gc = _box(1)
        child = _box(1, children=[gc])
        parent = _box(1, children=[child])
        ctrl = SessionController(_session(parent))

        ctrl.drill_into(parent)
        ctrl.drill_into(child)
        assert ctrl.nav.depth == 2

        ctrl.drill_to_root()
        assert ctrl.nav.depth == 0

    def test_navigation_emits_events(self):
        child = _box(1)
        parent = _box(1, children=[child])
        ctrl = SessionController(_session(parent))

        nav_cb = MagicMock()
        sel_cb = MagicMock()
        ctrl.subscribe("navigation_change", nav_cb)
        ctrl.subscribe("selection_change", sel_cb)

        ctrl.drill_into(parent)
        nav_cb.assert_called_once()
        sel_cb.assert_called_once()


# ── Box Operations ────────────────────────────────────────────────────


class TestControllerBoxOps:
    def test_add_box(self):
        ctrl = SessionController(_session())
        box = _box(1)
        ctrl.add_box(box)
        assert box in ctrl.active_list()
        assert ctrl.selected_boxes == [box]

    def test_delete_box(self):
        b1, b2 = _box(1), _box(2)
        ctrl = SessionController(_session(b1, b2))
        ctrl.delete_box(b1)
        assert b1 not in ctrl.active_list()
        # Remaining box renumbered to 1
        assert ctrl.active_list()[0].id == 1

    def test_delete_boxes_renumbers(self):
        boxes = [_box(i) for i in range(1, 6)]
        ctrl = SessionController(_session(*boxes))
        ctrl.delete_boxes([boxes[1], boxes[3]])  # remove #2 and #4
        remaining = ctrl.active_list()
        assert len(remaining) == 3
        assert [b.id for b in remaining] == [1, 2, 3]

    def test_rename_box(self):
        box = _box(1)
        ctrl = SessionController(_session(box))
        ctrl.rename_box(box, "Renamed")
        assert box.label == "Renamed"

    def test_update_box_coords(self):
        box = _box(1, x1=0, y1=0, x2=100, y2=100)
        ctrl = SessionController(_session(box))
        ctrl.update_box_coords(box, 10, 20, 110, 120)
        assert box.x1 == 10
        assert box.y1 == 20
        assert box.x2 == 110
        assert box.y2 == 120

    def test_move_box_order_up(self):
        b1, b2, b3 = _box(1), _box(2), _box(3)
        ctrl = SessionController(_session(b1, b2, b3))
        ctrl.move_box_order(b2, "up")
        assert ctrl.active_list()[0] is b2
        assert ctrl.active_list()[1] is b1

    def test_move_box_order_down(self):
        b1, b2, b3 = _box(1), _box(2), _box(3)
        ctrl = SessionController(_session(b1, b2, b3))
        ctrl.move_box_order(b2, "down")
        assert ctrl.active_list()[1] is b3
        assert ctrl.active_list()[2] is b2

    def test_move_first_box_up_noop(self):
        b1, b2 = _box(1), _box(2)
        ctrl = SessionController(_session(b1, b2))
        ctrl.move_box_order(b1, "up")
        assert ctrl.active_list()[0] is b1

    def test_bring_to_front(self):
        b1, b2, b3 = _box(1), _box(2), _box(3)
        ctrl = SessionController(_session(b1, b2, b3))
        ctrl.bring_to_front(b1)
        assert ctrl.active_list()[-1] is b1

    def test_bring_to_front_already_last_noop(self):
        b1, b2 = _box(1), _box(2)
        ctrl = SessionController(_session(b1, b2))
        cb = MagicMock()
        ctrl.subscribe("stack_reorder", cb)
        ctrl.bring_to_front(b2)
        cb.assert_not_called()


# ── Overlap Detection ─────────────────────────────────────────────────


class TestOverlapDetection:
    def test_no_overlaps(self):
        b1 = _box(1, x1=0, y1=0, x2=50, y2=50)
        b2 = _box(2, x1=60, y1=60, x2=100, y2=100)
        ctrl = SessionController(_session(b1, b2))
        assert ctrl.get_all_overlaps() == []

    def test_overlapping_pair(self):
        b1 = _box(1, x1=0, y1=0, x2=60, y2=60)
        b2 = _box(2, x1=40, y1=40, x2=100, y2=100)
        ctrl = SessionController(_session(b1, b2))
        overlaps = ctrl.get_all_overlaps()
        assert len(overlaps) == 1
        assert overlaps[0] == (b1, b2)

    def test_touching_edges_no_overlap(self):
        b1 = _box(1, x1=0, y1=0, x2=50, y2=50)
        b2 = _box(2, x1=50, y1=0, x2=100, y2=50)
        ctrl = SessionController(_session(b1, b2))
        assert ctrl.get_all_overlaps() == []

    def test_nested_children_overlaps_detected(self):
        c1 = _box(1, x1=0, y1=0, x2=60, y2=60)
        c2 = _box(2, x1=40, y1=40, x2=100, y2=100)
        parent = _box(1, x1=0, y1=0, x2=200, y2=200, children=[c1, c2])
        ctrl = SessionController(_session(parent))
        overlaps = ctrl.get_all_overlaps()
        assert len(overlaps) == 1
        assert overlaps[0] == (c1, c2)


# ── Screen Info ───────────────────────────────────────────────────────


class TestControllerScreenInfo:
    def test_update_screen_info(self):
        ctrl = SessionController(_session())
        ctrl.update_screen_info("New Name", "New Desc")
        assert ctrl.session.screen_name == "New Name"
        assert ctrl.session.description == "New Desc"

    def test_update_screen_info_undoable(self):
        ctrl = SessionController(_session())
        ctrl.update_screen_info("V2", "Desc V2")
        ctrl.undo()
        assert ctrl.session.screen_name == "Test"
        assert ctrl.session.description == ""


# ── Mode ──────────────────────────────────────────────────────────────


class TestControllerMode:
    def test_default_mode(self):
        ctrl = SessionController(_session())
        assert ctrl.mode == "select"

    def test_set_mode(self):
        ctrl = SessionController(_session())
        cb = MagicMock()
        ctrl.subscribe("mode_change", cb)
        ctrl.set_mode("draw")
        assert ctrl.mode == "draw"
        cb.assert_called_once_with("draw")


# ── Boundary ──────────────────────────────────────────────────────────


class TestControllerBoundary:
    def test_root_boundary(self):
        ctrl = SessionController(_session())
        assert ctrl.get_boundary(800, 600) == (0, 0, 800, 600)

    def test_drilled_boundary(self):
        parent = _box(1, x1=50, y1=100, x2=300, y2=400)
        ctrl = SessionController(_session(parent))
        ctrl.drill_into(parent)
        assert ctrl.get_boundary() == (50, 100, 300, 400)
