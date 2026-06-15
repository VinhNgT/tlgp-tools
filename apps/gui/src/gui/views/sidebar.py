import tkinter as tk
from tkinter import ttk
from uuid import UUID


class SidebarTreeView(ttk.Frame):
    """Passive Treeview layer view component displaying component hierarchies with incremental syncs."""

    def __init__(self, parent, **kwargs):
        super().__init__(parent, padding=10, **kwargs)

        ttk.Label(self, text="COMPONENTS", font=("", 9, "bold")).pack(
            anchor="w", pady=(0, 8)
        )

        self.tree = ttk.Treeview(self, selectmode="browse", show="tree")

        tree_scroll = ttk.Scrollbar(self, orient=tk.VERTICAL, command=self.tree.yview)
        tree_scroll.pack(side=tk.RIGHT, fill=tk.Y)

        self.tree.configure(yscrollcommand=tree_scroll.set)
        self.tree.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        self.tree.bind("<<TreeviewSelect>>", self._on_tree_select)
        self.tree.tag_configure("hidden", foreground="#999999")

        if self.tk.call('tk', 'windowingsystem') == 'aqua':
            self.tree.bind("<Button-2>", self._on_right_click)
            self.tree.bind("<Control-Button-1>", self._on_right_click)
        else:
            self.tree.bind("<Button-3>", self._on_right_click)

        self.tree.bind("<Double-1>", self._on_double_click)

        self.on_component_selected = None
        self.on_context_menu_request = None
        self.on_rename_request = None
        self._is_programmatic = False
        self._tree_nodes = {}

    def rebuild_tree(self, nodes: list[dict]):
        """Diffs and rebuilds Treeview nodes incrementally based on updated layout tree data."""
        synced_ids = set()

        def sync_node(parent_id: str, node_data: dict, index: int):
            node_id = node_data["id"]
            node_tags = node_data.get("tags", [])
            node_text = node_data["text"]
            node_label = node_data.get("label", "")
            if "locked" in node_tags:
                node_text = "🔒 " + node_text

            synced_ids.add(node_id)

            cached = self._tree_nodes.get(node_id)
            if cached is None:
                self.tree.insert(parent_id, index, iid=node_id, text=node_text, open=True, tags=node_tags)
                self._tree_nodes[node_id] = {
                    "text": node_text,
                    "label": node_label,
                    "tags": node_tags,
                    "parent": parent_id,
                    "index": index,
                }
            else:
                if cached["text"] != node_text or cached.get("tags") != node_tags or cached.get("label") != node_label:
                    self.tree.item(node_id, text=node_text, tags=node_tags)
                    cached["text"] = node_text
                    cached["tags"] = node_tags
                    cached["label"] = node_label

                if cached["parent"] != parent_id or cached["index"] != index:
                    self.tree.move(node_id, parent_id, index)
                    cached["parent"] = parent_id
                    cached["index"] = index

            for i, child_node in enumerate(node_data.get("children", [])):
                sync_node(node_id, child_node, i)

        for i, root_node in enumerate(nodes):
            sync_node("", root_node, i)

        to_delete = set(self._tree_nodes.keys()) - synced_ids
        for item_id in to_delete:
            if self.tree.exists(item_id):
                self.tree.delete(item_id)
            self._tree_nodes.pop(item_id, None)

    def select_component(self, comp_id: UUID):
        """Highlights specific component node without triggering selection update feedback loops."""
        comp_id_str = str(comp_id)
        if comp_id_str in self._tree_nodes:
            self._is_programmatic = True
            try:
                self.tree.selection_set(comp_id_str)
                self.tree.see(comp_id_str)
            except Exception:
                pass
            finally:
                self._is_programmatic = False

    def clear_selection(self):
        """Clears node selection highlighting cleanly."""
        self._is_programmatic = True
        try:
            self.tree.selection_set()
        except Exception:
            pass
        finally:
            self._is_programmatic = False

    def _on_tree_select(self, event):
        if self._is_programmatic:
            return
        item = self.tree.selection()
        if item and self.on_component_selected:
            try:
                comp_id = UUID(item[0])
                self.on_component_selected(comp_id)
            except ValueError:
                pass

    def _on_right_click(self, event):
        item = self.tree.identify_row(event.y)
        if item:
            try:
                comp_id = UUID(item)
                self.select_component(comp_id)
                if self.on_component_selected:
                    self.on_component_selected(comp_id)
                if self.on_context_menu_request:
                    self.on_context_menu_request(comp_id, event.x_root, event.y_root)
            except ValueError:
                pass

    def _on_double_click(self, event):
        item = self.tree.identify_row(event.y)
        if not item:
            return

        cached = self._tree_nodes.get(item)
        if not cached:
            return

        try:
            x, y, w, h = self.tree.bbox(item, "#0")
        except Exception:
            return

        entry = ttk.Entry(self.tree, font=("", 9))
        entry.place(x=x, y=y, width=w, height=h)
        entry.insert(0, cached.get("label", ""))
        entry.focus_set()

        def save_edit(e=None):
            new_label = entry.get().strip()
            if new_label and new_label != cached.get("label"):
                if self.on_rename_request:
                    try:
                        self.on_rename_request(UUID(item), new_label)
                    except ValueError:
                        pass
            entry.destroy()

        def cancel_edit(e=None):
            entry.destroy()

        entry.bind("<Return>", save_edit)
        entry.bind("<FocusOut>", save_edit)
        entry.bind("<Escape>", cancel_edit)
        return "break"
