import tkinter as tk
from tkinter import ttk
from uuid import UUID

from models import WorkspaceState


class SidebarTreeView(ttk.Treeview):
    """Passive Treeview layer view component displaying component hierarchies with incremental syncs."""

    def __init__(self, parent, **kwargs):
        super().__init__(parent, selectmode="browse", **kwargs)
        self.heading("#0", text="Components", anchor=tk.W)
        self.bind("<<TreeviewSelect>>", self._on_tree_select)

        self.on_component_selected = None
        self._is_programmatic = False

    def rebuild_tree(self, state: WorkspaceState | None):
        """Diffs and rebuilds Treeview nodes incrementally based on new state updates."""
        if not state:
            self.delete(*self.get_children())
            return

        existing_ids = self._get_all_tree_item_ids()
        synced_ids = set()

        def sync_node(parent_id: str, comp_uuid: UUID, index: int):
            comp = state.components.get(comp_uuid)
            if not comp:
                return

            comp_id_str = str(comp.id)
            synced_ids.add(comp_id_str)
            node_text = f"{comp.number} {comp.label}" if comp.number else comp.label

            suffix = []
            if not getattr(comp.visibility, "visible", True):
                suffix.append("hidden")
            if getattr(comp.visibility, "locked", False):
                suffix.append("locked")
            if suffix:
                node_text += f" ({', '.join(suffix)})"

            if not self.exists(comp_id_str):
                self.insert(
                    parent_id, index, iid=comp_id_str, text=node_text, open=True
                )
            else:
                if self.item(comp_id_str, "text") != node_text:
                    self.item(comp_id_str, text=node_text)

                current_parent = self.parent(comp_id_str)
                current_siblings = self.get_children(current_parent)
                try:
                    current_index = current_siblings.index(comp_id_str)
                except ValueError:
                    current_index = -1

                if current_parent != parent_id or current_index != index:
                    self.move(comp_id_str, parent_id, index)

            for i, child_uuid in enumerate(comp.childrenIds):
                sync_node(comp_id_str, child_uuid, i)

        for i, root_uuid in enumerate(state.rootComponents):
            sync_node("", root_uuid, i)

        to_delete = existing_ids - synced_ids
        for item_id in to_delete:
            if self.exists(item_id):
                self.delete(item_id)

    def select_component(self, comp_id: UUID):
        """Highlights specific component node without triggering selection update feedback loops."""
        comp_id_str = str(comp_id)
        if self.exists(comp_id_str):
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

    def _get_all_tree_item_ids(self) -> set[str]:
        item_ids = set()

        def traverse(item_id):
            children = self.get_children(item_id)
            for child in children:
                item_ids.add(child)
                traverse(child)

        traverse("")
        return item_ids

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
