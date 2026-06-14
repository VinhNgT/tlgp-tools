import tkinter as tk
from tkinter import ttk
from uuid import UUID


class SidebarTreeView(ttk.Treeview):
    """Passive Treeview layer view component displaying component hierarchies with incremental syncs."""

    def __init__(self, parent, **kwargs):
        super().__init__(parent, selectmode="browse", **kwargs)
        self.heading("#0", text="Components", anchor=tk.W)
        self.bind("<<TreeviewSelect>>", self._on_tree_select)

        self.on_component_selected = None
        self._is_programmatic = False
        self._tree_nodes = {}

    def rebuild_tree(self, nodes: list[dict]):
        """Diffs and rebuilds Treeview nodes incrementally based on updated layout tree data."""
        synced_ids = set()

        def sync_node(parent_id: str, node_data: dict, index: int):
            node_id = node_data["id"]
            node_text = node_data["text"]
            synced_ids.add(node_id)

            cached = self._tree_nodes.get(node_id)
            if cached is None:
                self.insert(parent_id, index, iid=node_id, text=node_text, open=True)
                self._tree_nodes[node_id] = {
                    "text": node_text,
                    "parent": parent_id,
                    "index": index,
                }
            else:
                if cached["text"] != node_text:
                    self.item(node_id, text=node_text)
                    cached["text"] = node_text

                if cached["parent"] != parent_id or cached["index"] != index:
                    self.move(node_id, parent_id, index)
                    cached["parent"] = parent_id
                    cached["index"] = index

            for i, child_node in enumerate(node_data.get("children", [])):
                sync_node(node_id, child_node, i)

        for i, root_node in enumerate(nodes):
            sync_node("", root_node, i)

        to_delete = set(self._tree_nodes.keys()) - synced_ids
        for item_id in to_delete:
            self.delete(item_id)
            self._tree_nodes.pop(item_id, None)

    def select_component(self, comp_id: UUID):
        """Highlights specific component node without triggering selection update feedback loops."""
        comp_id_str = str(comp_id)
        if comp_id_str in self._tree_nodes:
            self._is_programmatic = True
            try:
                self.selection_set(comp_id_str)
                self.see(comp_id_str)
            except Exception:
                pass
            finally:
                self._is_programmatic = False

    def clear_selection(self):
        """Clears node selection highlighting cleanly."""
        self._is_programmatic = True
        try:
            self.selection_set()
        except Exception:
            pass
        finally:
            self._is_programmatic = False

    def _on_tree_select(self, event):
        if self._is_programmatic:
            return
        item = self.selection()
        if item and self.on_component_selected:
            try:
                comp_id = UUID(item[0])
                self.on_component_selected(comp_id)
            except ValueError:
                pass
