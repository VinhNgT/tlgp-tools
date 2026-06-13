import tkinter as tk
from tkinter import ttk

import ttkbootstrap as tb

from tlgp_annotation_tool.controller import NavigationContext, SessionController
from tlgp_annotation_tool.models import AnnotationBox


class ComponentSidebar(tb.Frame):
    def __init__(
        self, parent, controller: SessionController, on_select_callback, **kwargs
    ):
        super().__init__(parent, **kwargs)
        self.controller = controller
        self.session = controller.session
        self.on_select = on_select_callback

        self.selected_boxes: list[AnnotationBox] = []
        self._drag_iids: list[str] = []

        # UI Setup
        tb.Label(self, text="LAYERS", font=("", 9, "bold")).pack(
            anchor="w", padx=10, pady=(10, 5)
        )

        # Scrollable Treeview
        tree_frame = tb.Frame(self)
        tree_frame.pack(fill=tk.BOTH, expand=True, padx=5, pady=5)

        tree_frame.grid_columnconfigure(0, weight=1)
        tree_frame.grid_rowconfigure(0, weight=1)

        scrollbar = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL)

        # Dynamic auto-hiding scrollbar
        def yscroll_set(lo, hi):
            if float(lo) <= 0.0 and float(hi) >= 1.0:
                scrollbar.grid_forget()
            else:
                scrollbar.grid(row=0, column=1, sticky="ns")
            scrollbar.set(lo, hi)

        self.tree = ttk.Treeview(
            tree_frame,
            columns=("id", "label"),
            show="tree headings",
            yscrollcommand=yscroll_set,
        )
        self.tree.heading("#0", text="Layer Structure")
        self.tree.heading("id", text="ID")
        self.tree.heading("label", text="Name")

        self.tree.column("#0", width=120, stretch=True)
        self.tree.column("id", width=55, stretch=False, anchor="center")
        self.tree.column("label", width=140, stretch=True)
        self.tree.grid(row=0, column=0, sticky="nsew")

        scrollbar.config(command=self.tree.yview)

        # Bindings
        self.tree.bind("<<TreeviewSelect>>", self.on_tree_select)
        self.tree.bind("<ButtonPress-1>", self.on_drag_start)
        self.tree.bind("<B1-Motion>", self.on_drag_motion)
        self.tree.bind("<ButtonRelease-1>", self.on_drag_release)
        self.tree.bind("<Double-1>", self.on_double_click)

        # Subscribe to controller events
        self.controller.subscribe(
            "add", lambda box: self.refresh_list(select_boxes=[box] if box else None)
        )
        self.controller.subscribe("delete", lambda box: self.refresh_list())
        self.controller.subscribe("rename", self.on_box_renamed)
        self.controller.subscribe(
            "reorder", lambda box: self.refresh_list(select_boxes=self.selected_boxes)
        )
        self.controller.subscribe(
            "renumber", lambda box: self.refresh_list(select_boxes=self.selected_boxes)
        )
        self.controller.subscribe("undo_redo", lambda box: self.refresh_list())
        self.controller.subscribe(
            "coords_committed",
            lambda arg: self.refresh_list(select_boxes=self.selected_boxes),
        )
        self.controller.subscribe("selection_change", self._on_selection_change)
        self.controller.subscribe("navigation_change", lambda: self.refresh_list())

        # Visual indicators for drag-and-drop
        self._drop_indicator = tk.Frame(self.tree, height=2, bg="#0c8ce9")
        self._drag_ghost = tk.Label(
            self.tree,
            text="",
            bg="#0c8ce9",
            fg="white",
            font=("", 9),
            padx=6,
            pady=3,
            relief="flat",
        )

    # ── IID Scheme ─────────────────────────────────────────────────────
    # Path-based: "N_{id}" for root, "N_{id}_{child_id}" for depth 2, etc.

    def _build_iid(self, path_ids: list[int]) -> str:
        """Build a treeview IID from a list of box IDs representing the path."""
        return "N_" + "_".join(str(i) for i in path_ids)

    def _parse_iid(self, iid: str) -> list[int]:
        """Parse a treeview IID back to a list of box IDs."""
        if not iid.startswith("N_"):
            return []
        parts = iid[2:].split("_")
        try:
            return [int(p) for p in parts]
        except ValueError:
            return []

    def resolve_iid(self, iid: str) -> tuple[list[AnnotationBox], AnnotationBox | None]:
        """Resolves a treeview IID to (ancestor_chain, box).

        ancestor_chain: list of parent boxes from root down (not including the box itself).
        box: the resolved AnnotationBox, or None if not found.
        """
        path_ids = self._parse_iid(iid)
        if not path_ids:
            return [], None

        ancestors = []
        current_list = self.session.components
        box = None

        for depth, box_id in enumerate(path_ids):
            found = None
            for b in current_list:
                if b.id == box_id:
                    found = b
                    break
            if found is None:
                return ancestors, None
            if depth < len(path_ids) - 1:
                ancestors.append(found)
                current_list = found.children
            else:
                box = found

        return ancestors, box

    def _find_iid_for_box(self, target_box: AnnotationBox | None) -> str | None:
        """Find the IID for a given box by walking the tree."""
        if not target_box:
            return None
        return self._search_box_in_list(self.session.components, target_box, [])

    def _search_box_in_list(
        self, boxes: list[AnnotationBox], target: AnnotationBox, path: list[int]
    ) -> str | None:
        for box in boxes:
            current_path = path + [box.id]
            if box is target:
                return self._build_iid(current_path)
            result = self._search_box_in_list(box.children, target, current_path)
            if result:
                return result
        return None

    # ── Tree Population ────────────────────────────────────────────────

    def refresh_list(self, select_boxes: list[AnnotationBox] | None = None):
        for item in self.tree.get_children():
            self.tree.delete(item)

        # Get overlapping boxes for warning indicators
        overlaps = self.controller.get_all_overlaps()
        overlapping_boxes = set()
        for b1, b2 in overlaps:
            overlapping_boxes.add(id(b1))
            overlapping_boxes.add(id(b2))

        # Recursively populate the tree
        self._insert_boxes_recursive(self.session.components, "", [], overlapping_boxes)

        if select_boxes:
            self.select_boxes_in_tree(select_boxes)

    def _insert_boxes_recursive(
        self,
        boxes: list[AnnotationBox],
        parent_iid: str,
        path: list[int],
        overlapping_boxes: set,
    ):
        """Recursively insert boxes into the treeview."""
        sorted_boxes = sorted(boxes, key=lambda x: x.id)
        for box in sorted_boxes:
            current_path = path + [box.id]
            iid = self._build_iid(current_path)

            id_str = str(box.id)
            if id(box) in overlapping_boxes:
                id_str = "⚠️ " + id_str

            icon = "📁" if box.children else "📄"
            node_type = "Group" if box.children else "Item"

            self.tree.insert(
                parent_iid,
                tk.END,
                iid=iid,
                text=f"{icon} {node_type}",
                values=(id_str, box.label),
                open=True,
            )

            if box.children:
                self._insert_boxes_recursive(
                    box.children, iid, current_path, overlapping_boxes
                )

    # ── Selection ──────────────────────────────────────────────────────

    def select_boxes_in_tree(self, boxes: list[AnnotationBox]):
        """Programmatically select multiple boxes in the Treeview."""
        self.selected_boxes = boxes
        self._is_programmatic_selection = True
        try:
            self.tree.selection_remove(self.tree.selection())
            iids = []
            for box in boxes:
                iid = self._find_iid_for_box(box)
                if iid:
                    iids.append(iid)
            if iids:
                self.tree.selection_set(iids)
                self.tree.see(iids[-1])
        finally:
            self._is_programmatic_selection = False

    def select_box_in_tree(self, box: AnnotationBox | None):
        self.select_boxes_in_tree([box] if box else [])

    def on_box_renamed(self, box: AnnotationBox):
        iid = self._find_iid_for_box(box)
        if iid:
            id_val = self.tree.set(iid, "id")
            self.tree.item(iid, values=(id_val, box.label))

    def on_tree_select(self, event):
        if getattr(self, "_is_programmatic_selection", False):
            return
        sel = self.tree.selection()

        matched_boxes = []
        for iid in sel:
            _, box = self.resolve_iid(iid)
            if box:
                matched_boxes.append(box)

        # Prevent infinite event loops
        if {id(b) for b in matched_boxes} == {id(b) for b in self.selected_boxes}:
            return

        if not sel:
            self.controller.set_selection([])
            return

        # All selected items must be siblings (same parent)
        focus_iid = self.tree.focus()
        if not focus_iid or focus_iid not in sel:
            focus_iid = sel[-1]

        focus_ancestors, focus_box = self.resolve_iid(focus_iid)
        focus_parent = focus_ancestors[-1] if focus_ancestors else None

        matched_boxes = []
        matched_iids = []
        for iid in sel:
            ancestors, box = self.resolve_iid(iid)
            item_parent = ancestors[-1] if ancestors else None
            if item_parent is focus_parent and box:
                matched_boxes.append(box)
                matched_iids.append(iid)

        if len(matched_iids) != len(sel):
            self._is_programmatic_selection = True
            try:
                self.tree.selection_set(matched_iids)
            finally:
                self._is_programmatic_selection = False

        if self.controller.nav.parent_stack != focus_ancestors:
            self.controller.nav.parent_stack = list(focus_ancestors)
            self._is_programmatic_selection = True
            try:
                self.controller._notify("navigation_change")
            finally:
                self._is_programmatic_selection = False

        self.selected_boxes = matched_boxes
        self.controller.set_selection(matched_boxes)

    def _on_selection_change(
        self, nav: "NavigationContext", boxes: list[AnnotationBox]
    ):
        self.selected_boxes = boxes
        self.select_boxes_in_tree(boxes)

    def get_selected_box(self) -> AnnotationBox | None:
        return self.selected_boxes[-1] if self.selected_boxes else None

    # ── Double-Click (Drill Into) ──────────────────────────────────────

    def on_double_click(self, event):
        region = self.tree.identify("region", event.x, event.y)
        if region not in ("tree", "cell"):
            return

        column = self.tree.identify_column(event.x)
        iid = self.tree.identify_row(event.y)
        if not iid:
            return

        if column == "#2":  # Label column — inline rename
            _, box = self.resolve_iid(iid)
            if box:
                self.start_inline_rename(iid, column, box)
        else:
            # Double-click on tree/id column — drill into the box
            _, box = self.resolve_iid(iid)
            if box:
                self.controller.drill_into(box)

    # ── Drag and Drop ──────────────────────────────────────────────────

    def on_drag_start(self, event):
        region = self.tree.identify("region", event.x, event.y)
        if region not in ("tree", "cell"):
            return

        iid = self.tree.identify_row(event.y)
        if iid:
            sel = self.tree.selection()
            if iid not in sel:
                self._is_programmatic_selection = True
                try:
                    self.tree.selection_set(iid)
                finally:
                    self._is_programmatic_selection = False
                sel = (iid,)

            self._drag_iids = list(sel)
            self._drag_x = event.x
            self._drag_y = event.y
            self._drag_active = False

            if len(self._drag_iids) > 1:
                self._ghost_text = f"📦 Move {len(self._drag_iids)} items"
            else:
                _, src_box = self.resolve_iid(iid)
                if src_box:
                    icon = "📁" if src_box.children else "📄"
                    self._ghost_text = f"{icon} {src_box.label}"
                else:
                    self._ghost_text = ""

    def on_drag_motion(self, event):
        if not hasattr(self, "_drag_iids") or not self._drag_iids:
            return

        dx = abs(event.x - self._drag_x)
        dy = abs(event.y - self._drag_y)
        if not self._drag_active and (dx > 5 or dy > 5):
            self._drag_active = True
            self.tree.config(cursor="hand2")
            if hasattr(self, "_ghost_text") and self._ghost_text:
                self._drag_ghost.config(text=self._ghost_text)

        if self._drag_active:
            self._drag_ghost.place(x=event.x + 15, y=event.y + 10)

            target_iid = self.tree.identify_row(event.y)
            if target_iid:
                self.tree.focus(target_iid)

                bbox = self.tree.bbox(target_iid)
                if bbox:
                    y_rel = event.y - bbox[1]
                    h = bbox[3]
                    if y_rel < h / 3:
                        target_y = bbox[1]
                        self._drop_indicator.place(
                            x=bbox[0],
                            y=target_y - 1,
                            width=self.tree.winfo_width() - bbox[0] - 20,
                        )
                    elif y_rel > 2 * h / 3:
                        target_y = bbox[1] + h
                        self._drop_indicator.place(
                            x=bbox[0],
                            y=target_y - 1,
                            width=self.tree.winfo_width() - bbox[0] - 20,
                        )
                    else:
                        self._drop_indicator.place_forget()
                else:
                    self._drop_indicator.place_forget()
            else:
                self._drop_indicator.place_forget()

    def on_drag_release(self, event):
        self.tree.config(cursor="")
        self._drop_indicator.place_forget()
        self._drag_ghost.place_forget()

        if hasattr(self, "_drag_active") and self._drag_active:
            target_iid = self.tree.identify_row(event.y)
            if target_iid and target_iid not in self._drag_iids:
                bbox = self.tree.bbox(target_iid)
                if bbox:
                    y_rel = event.y - bbox[1]
                    h = bbox[3]
                    if y_rel < h / 3:
                        position = "before"
                    elif y_rel > 2 * h / 3:
                        position = "after"
                    else:
                        position = "inside"
                else:
                    position = "inside"

                tgt_ancestors, tgt_box = self.resolve_iid(target_iid)
                tgt_parent = tgt_ancestors[-1] if tgt_ancestors else None

                src_boxes = []
                for drag_iid in self._drag_iids:
                    _, box = self.resolve_iid(drag_iid)
                    if box:
                        src_boxes.append(box)

                if src_boxes:
                    self.controller.move_boxes_to_target(
                        src_boxes=src_boxes,
                        tgt_parent=tgt_parent,
                        tgt_box=tgt_box,
                        position=position,
                    )

            sel = self.tree.selection()
            if sel:
                self.tree.focus(sel[0])

        self._drag_iids = []
        self._drag_active = False

    # ── Inline Rename ──────────────────────────────────────────────────

    def start_inline_rename(self, iid: str, column: str, box: AnnotationBox):
        bbox = self.tree.bbox(iid, column)
        if not bbox:
            return

        style = ttk.Style()
        bg = style.lookup("Treeview", "background") or "#222222"
        fg = style.lookup("Treeview", "foreground") or "#ffffff"
        select_bg = "#0c8ce9"
        select_fg = "#ffffff"

        entry = tk.Entry(
            self.tree,
            font=("", 9),
            bd=0,
            highlightthickness=0,
            bg=bg,
            fg=fg,
            selectbackground=select_bg,
            selectforeground=select_fg,
            insertbackground=fg,
        )
        entry.insert(0, box.label)
        entry.select_range(0, tk.END)
        entry.focus_set()

        entry.place(x=bbox[0], y=bbox[1], width=bbox[2], height=bbox[3])

        is_saved = [False]

        def save_edit(event=None):
            if is_saved[0]:
                return
            is_saved[0] = True
            new_name = entry.get().strip()
            entry.destroy()
            if new_name and new_name != box.label:
                self.controller.rename_box(box, new_name)

        def cancel_edit(event=None):
            if is_saved[0]:
                return
            is_saved[0] = True
            entry.destroy()

        entry.bind("<Return>", save_edit)
        entry.bind("<FocusOut>", save_edit)
        entry.bind("<Escape>", cancel_edit)
