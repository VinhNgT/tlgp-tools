import copy
from dataclasses import dataclass, field
from typing import List, Callable, Optional, Dict, Tuple
from tlgp_annotation_tool.models import ScreenSession, AnnotationBox
from tlgp_annotation_tool.history import HistoryManager


@dataclass
class NavigationContext:
    """Tracks the current drill-in position within the annotation tree.
    
    The parent_stack holds the chain of ancestor boxes from root to the
    current parent. An empty stack means the user is viewing root-level
    components.
    """
    parent_stack: List[AnnotationBox] = field(default_factory=list)

    @property
    def depth(self) -> int:
        return len(self.parent_stack)

    @property
    def current_parent(self) -> Optional[AnnotationBox]:
        return self.parent_stack[-1] if self.parent_stack else None

    def breadcrumb(self) -> str:
        if not self.parent_stack:
            return "Root"
        return " › ".join(b.label for b in self.parent_stack)

    def copy(self) -> 'NavigationContext':
        return NavigationContext(parent_stack=list(self.parent_stack))


class SessionController:
    def __init__(self, session: ScreenSession):
        self.session = session
        self.history = HistoryManager(session)
        self.listeners: Dict[str, List[Callable]] = {}

        # Navigation state — replaces the old level/selected_l1_box pattern
        self.nav = NavigationContext()
        self.selected_boxes: List[AnnotationBox] = []
        self.mode: str = "select"

    # ── Event System ───────────────────────────────────────────────────

    def subscribe(self, event_type: str, callback: Callable):
        if event_type not in self.listeners:
            self.listeners[event_type] = []
        self.listeners[event_type].append(callback)

    def _notify(self, event_type: str, *args, **kwargs):
        if event_type in self.listeners:
            for cb in self.listeners[event_type]:
                try:
                    cb(*args, **kwargs)
                except Exception as e:
                    print(f"Error executing callback for {event_type}: {e}")

    # ── Mode ───────────────────────────────────────────────────────────

    def set_mode(self, mode: str):
        """Changes the interaction mode and notifies subscribers."""
        self.mode = mode
        self._notify("mode_change", mode)

    # ── Navigation ─────────────────────────────────────────────────────

    def active_list(self) -> List[AnnotationBox]:
        """Returns the list of boxes at the current navigation depth."""
        parent = self.nav.current_parent
        if parent:
            return parent.children
        return self.session.components

    def drill_into(self, box: AnnotationBox):
        """Navigate one level deeper into the given box."""
        self.nav.parent_stack.append(box)
        self.selected_boxes = []
        self._notify("navigation_change")
        self._notify("selection_change", self.nav, [])

    def drill_out(self):
        """Navigate one level up. No-op if already at root."""
        if not self.nav.parent_stack:
            return
        exited_box = self.nav.parent_stack.pop()
        self.selected_boxes = [exited_box]
        self._notify("navigation_change")
        self._notify("selection_change", self.nav, [exited_box])

    def drill_to_root(self):
        """Navigate all the way back to root."""
        if not self.nav.parent_stack:
            return
        self.nav.parent_stack.clear()
        self.selected_boxes = []
        self._notify("navigation_change")
        self._notify("selection_change", self.nav, [])

    # ── Selection ──────────────────────────────────────────────────────

    def set_selection(self, boxes: List[AnnotationBox]):
        """Update the selected boxes at the current navigation depth."""
        self.selected_boxes = boxes
        self._notify("selection_change", self.nav, boxes)

    # ── Box Operations ─────────────────────────────────────────────────

    def add_box(self, box: AnnotationBox):
        """Add a box to the current active list."""
        self.active_list().append(box)
        self.history.save_snapshot()
        self._notify("add", box)
        self.set_selection([box])

    def delete_boxes(self, boxes: List[AnnotationBox]):
        """Delete boxes from the current active list."""
        active = self.active_list()
        deleted_any = False
        for box in boxes:
            if box in active:
                active.remove(box)
                deleted_any = True

        if deleted_any:
            for i, b in enumerate(active):
                b.id = i + 1

            new_sel = [b for b in self.selected_boxes if b not in boxes]
            self.history.save_snapshot()
            self._notify("delete", None)
            self.set_selection(new_sel)

    def delete_box(self, box: AnnotationBox):
        self.delete_boxes([box])

    def update_box_coords(self, box: AnnotationBox, x1: int, y1: int, x2: int, y2: int):
        box.x1 = x1
        box.y1 = y1
        box.x2 = x2
        box.y2 = y2
        self._notify("update_coords", box)

    def _shift_box_descendants(self, box: AnnotationBox, dx: int, dy: int):
        for child in box.children:
            child.x1 += dx
            child.y1 += dy
            child.x2 += dx
            child.y2 += dy
            if child.children:
                self._shift_box_descendants(child, dx, dy)

    def update_boxes_coords(self, coords_list: List[Tuple[AnnotationBox, Tuple[int, int, int, int]]]):
        for box, coords in coords_list:
            new_x1, new_y1, new_x2, new_y2 = coords
            dx = new_x1 - box.x1
            dy = new_y1 - box.y1
            
            box.x1, box.y1, box.x2, box.y2 = new_x1, new_y1, new_x2, new_y2
            
            if dx != 0 or dy != 0:
                self._shift_box_descendants(box, dx, dy)
                
        self._notify("update_coords", None)

    def commit_coords_change(self):
        """Called when a move or resize drag finishes to save the snapshot."""
        self.history.save_snapshot()
        self._notify("coords_committed", None)

    def rename_box(self, box: AnnotationBox, new_label: str):
        box.label = new_label
        self.history.save_snapshot()
        self._notify("rename", box)

    def update_box_pill_corner(self, box: AnnotationBox, corner: str):
        box.pill_corner = corner
        self.history.save_snapshot()
        self._notify("update_coords", box)

    def move_box_order(self, box: AnnotationBox, direction: str):
        """Moves a box up or down in the sequence order."""
        active = self.active_list()
        if box not in active:
            return

        idx = active.index(box)
        if direction == "up" and idx > 0:
            active[idx], active[idx - 1] = active[idx - 1], active[idx]
            active[idx].id, active[idx - 1].id = active[idx - 1].id, active[idx].id
        elif direction == "down" and idx < len(active) - 1:
            active[idx], active[idx + 1] = active[idx + 1], active[idx]
            active[idx].id, active[idx + 1].id = active[idx + 1].id, active[idx].id
        else:
            return

        self.history.save_snapshot()
        self._notify("reorder", box)

    def bring_to_front(self, box: AnnotationBox, save_history: bool = False):
        active = self.active_list()
        if box in active:
            if active[-1] is box:
                return
            active.remove(box)
            active.append(box)
            if save_history:
                self.history.save_snapshot()
            self._notify("stack_reorder", box)

    def move_boxes_to_target(self, src_boxes: List[AnnotationBox],
                             tgt_parent: Optional[AnnotationBox],
                             tgt_box: Optional[AnnotationBox],
                             position: str):
        """Moves/reorders src_boxes relative to a target.
        
        tgt_parent: The parent whose children list is the drop target.
                    None means root (session.components).
        tgt_box: The specific sibling box to position relative to. 
                 None means append to the end.
        position: "before", "after", or "inside"
        """
        if not src_boxes:
            return

        active = self.active_list()
        to_move = [b for b in src_boxes if b in active]
        if not to_move:
            return

        # Determine the target list
        if position == "inside" and tgt_box is not None:
            # Dropping inside a box means moving to its children
            tgt_list = tgt_box.children
            for b in to_move:
                active.remove(b)
            for b in to_move:
                tgt_list.append(b)
        else:
            # Reordering within the same list
            real_tgt_box = tgt_box
            if not real_tgt_box or real_tgt_box not in active:
                return
            if real_tgt_box in to_move:
                return

            for b in to_move:
                active.remove(b)

            idx = active.index(real_tgt_box)
            if position == "before":
                for i, b in enumerate(to_move):
                    active.insert(idx + i, b)
            else:
                for i, b in enumerate(to_move):
                    active.insert(idx + 1 + i, b)

        # Renumber both source and target lists
        for i, b in enumerate(active):
            b.id = i + 1
        if position == "inside" and tgt_box is not None:
            for i, b in enumerate(tgt_box.children):
                b.id = i + 1

        self.history.save_snapshot()
        self.set_selection(to_move)
        self._notify("reorder", None)

    def renumber_all(self):
        """Sort boxes in the entire tree recursively by coordinates and renumber."""
        from tlgp_annotation_tool.layout_sort import sort_and_renumber_recursive
        sort_and_renumber_recursive(self.session.components)
        self.history.save_snapshot()
        self._notify("renumber", None)

    def update_screen_info(self, name: str, description: str):
        self.session.screen_name = name
        self.session.description = description
        self.history.save_snapshot()
        self._notify("screen_info", None)

    def get_cut_lines(self) -> List[int]:
        """Returns the current sorted cut lines."""
        return list(self.session.cut_lines)

    def set_cut_lines(self, lines: List[int]):
        """Replaces the cut lines list (sorted), saves snapshot, notifies."""
        self.session.cut_lines = sorted(lines)
        self.history.save_snapshot()
        self._notify("cuts_change", None)

    # ── Undo / Redo ────────────────────────────────────────────────────

    def undo(self) -> bool:
        if self.history.undo():
            self._revalidate_nav_after_history()
            self.selected_boxes = []
            self._notify("undo_redo", None)
            self._notify("selection_change", self.nav, [])
            return True
        return False

    def redo(self) -> bool:
        if self.history.redo():
            self._revalidate_nav_after_history()
            self.selected_boxes = []
            self._notify("undo_redo", None)
            self._notify("selection_change", self.nav, [])
            return True
        return False

    def _revalidate_nav_after_history(self):
        """After undo/redo, the nav stack may reference stale box objects.
        Walk the restored component tree to re-link or truncate the stack."""
        new_stack = []
        current_list = self.session.components
        for old_parent in self.nav.parent_stack:
            # Find the box in the current list that matches by id
            match = None
            for b in current_list:
                if b.id == old_parent.id:
                    match = b
                    break
            if match is None:
                break  # Can't go deeper, truncate here
            new_stack.append(match)
            current_list = match.children
        self.nav.parent_stack = new_stack

    # ── Overlap Detection ──────────────────────────────────────────────

    def get_all_overlaps(self) -> List[tuple]:
        """Returns a list of (box1, box2) pairs that overlap, checked recursively."""
        overlaps = []
        self._check_overlaps_recursive(self.session.components, overlaps)
        return overlaps

    def _check_overlaps_recursive(self, boxes: List[AnnotationBox], overlaps: List[tuple]):
        for i in range(len(boxes)):
            for j in range(i + 1, len(boxes)):
                b1, b2 = boxes[i], boxes[j]
                if (b1.left < b2.right and b1.right > b2.left and
                    b1.top < b2.bottom and b1.bottom > b2.top):
                    overlaps.append((b1, b2))

        for box in boxes:
            if box.children:
                self._check_overlaps_recursive(box.children, overlaps)

    # ── Boundary ───────────────────────────────────────────────────────

    def get_boundary(self, img_width: int = 99999, img_height: int = 99999) -> Tuple[int, int, int, int]:
        """Returns the drawing boundary for the current navigation depth."""
        parent = self.nav.current_parent
        if parent:
            return parent.left, parent.top, parent.right, parent.bottom
        return 0, 0, img_width, img_height
