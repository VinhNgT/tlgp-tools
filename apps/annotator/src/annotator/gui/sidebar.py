from uuid import UUID

from PySide6.QtCore import QEvent, QModelIndex, QObject, Qt
from PySide6.QtGui import QStandardItem, QStandardItemModel
from PySide6.QtWidgets import (
    QAbstractItemView,
    QLabel,
    QLineEdit,
    QTreeView,
    QVBoxLayout,
    QWidget,
)


class SidebarTreeView(QWidget):
    """Treeview layer displaying component hierarchies with incremental syncs."""

    def __init__(self, parent=None):
        super().__init__(parent)

        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(4)

        lbl = QLabel("LAYERS")
        font = lbl.font()
        font.setBold(True)
        font.setPointSize(9)
        lbl.setFont(font)
        lbl.setStyleSheet("color: #888888; padding-bottom: 4px;")

        layout.addWidget(lbl)

        self.model = QStandardItemModel()
        self.tree = QTreeView()
        self.tree.setModel(self.model)
        self.tree.setHeaderHidden(True)
        self.tree.setEditTriggers(QAbstractItemView.EditTrigger.NoEditTriggers)
        self.tree.setSelectionMode(QAbstractItemView.SelectionMode.ExtendedSelection)
        self.tree.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.tree.setAnimated(False)
        self.tree.setIndentation(16)
        layout.addWidget(self.tree)

        self.tree.selectionModel().selectionChanged.connect(self._on_tree_select)
        self.tree.customContextMenuRequested.connect(self._on_right_click)
        self.tree.doubleClicked.connect(self._on_double_click)

        self.on_component_selected = None
        self.on_components_selected = None
        self.on_context_menu_request = None
        self.on_rename_request = None
        self._is_programmatic = False
        self._item_map: dict[str, QStandardItem] = {}

    def rebuild_tree(self, nodes: list[dict]):
        """Diffs and rebuilds tree nodes incrementally based on updated layout tree data."""
        synced_ids: set[str] = set()
        new_ids: set[str] = set()

        def sync_node(parent_item: QStandardItem | None, node_data: dict, index: int):
            node_id = node_data["id"]
            node_text = node_data["text"]

            synced_ids.add(node_id)

            cached_item = self._item_map.get(node_id)
            container = (
                parent_item
                if parent_item is not None
                else self.model.invisibleRootItem()
            )

            if cached_item is None:
                item = QStandardItem(node_text)
                item.setData(node_id, Qt.ItemDataRole.UserRole)
                item.setData(node_data.get("label", ""), Qt.ItemDataRole.UserRole + 1)
                item.setEditable(False)
                container.insertRow(index, item)
                self._item_map[node_id] = item
                cached_item = item
                new_ids.add(node_id)
            else:
                if cached_item.text() != node_text:
                    cached_item.setText(node_text)
                cached_item.setData(
                    node_data.get("label", ""), Qt.ItemDataRole.UserRole + 1
                )

                # Re-parent if needed
                if cached_item.parent() != parent_item:
                    old_parent = cached_item.parent() or self.model.invisibleRootItem()
                    taken = old_parent.takeRow(cached_item.row())
                    if taken:
                        container.insertRow(index, taken)
                elif cached_item.row() != index:
                    taken = container.takeRow(cached_item.row())
                    if taken:
                        container.insertRow(index, taken)

            for i, child_node in enumerate(node_data.get("children", [])):
                sync_node(cached_item, child_node, i)

        for i, root_node in enumerate(nodes):
            sync_node(None, root_node, i)

        # Remove items not present in the new tree
        to_delete = set(self._item_map.keys()) - synced_ids
        for item_id in to_delete:
            item = self._item_map.pop(item_id, None)
            if item:
                try:
                    parent = item.parent() or self.model.invisibleRootItem()
                    parent.removeRow(item.row())
                except RuntimeError:
                    pass

        # Only expand newly inserted items, preserving user's collapse state
        for node_id in new_ids:
            item = self._item_map.get(node_id)
            if item:
                try:
                    self.tree.expand(item.index())
                except RuntimeError:
                    pass

    def select_component(self, comp_id: UUID):
        """Highlights specific component node without triggering selection update feedback loops."""
        comp_id_str = str(comp_id)
        item = self._item_map.get(comp_id_str)
        if item:
            self._is_programmatic = True
            try:
                idx = item.index()
                self.tree.selectionModel().select(
                    idx,
                    self.tree.selectionModel().SelectionFlag.ClearAndSelect,
                )
                self.tree.scrollTo(idx)
            except Exception:
                pass
            finally:
                self._is_programmatic = False

    def select_components(self, comp_ids: list[UUID]):
        """Highlights specific component nodes without triggering selection update feedback loops."""
        self._is_programmatic = True
        try:
            sel_model = self.tree.selectionModel()
            sel_model.clearSelection()
            first_idx = None
            for comp_id in comp_ids:
                comp_id_str = str(comp_id)
                item = self._item_map.get(comp_id_str)
                if item:
                    idx = item.index()
                    sel_model.select(
                        idx,
                        sel_model.SelectionFlag.Select | sel_model.SelectionFlag.Rows,
                    )
                    if first_idx is None:
                        first_idx = idx
            if first_idx is not None:
                self.tree.scrollTo(first_idx)
        except Exception:
            pass
        finally:
            self._is_programmatic = False

    def clear_selection(self):
        """Clears node selection highlighting cleanly."""
        self._is_programmatic = True
        try:
            self.tree.selectionModel().clearSelection()
        except Exception:
            pass
        finally:
            self._is_programmatic = False

    def _on_tree_select(self, selected, deselected):
        if self._is_programmatic:
            return
        indexes = self.tree.selectionModel().selectedRows()
        comp_ids = []
        for index in indexes:
            item = self.model.itemFromIndex(index)
            if item:
                try:
                    comp_id = UUID(item.data(Qt.ItemDataRole.UserRole))
                    comp_ids.append(comp_id)
                except ValueError:
                    pass
        if self.on_components_selected:
            self.on_components_selected(comp_ids)
        elif self.on_component_selected and len(comp_ids) == 1:
            self.on_component_selected(comp_ids[0])

    def _on_right_click(self, pos):
        index = self.tree.indexAt(pos)
        if not index.isValid():
            return
        item = self.model.itemFromIndex(index)
        if not item:
            return
        try:
            comp_id = UUID(item.data(Qt.ItemDataRole.UserRole))
            self.select_component(comp_id)
            if self.on_component_selected:
                self.on_component_selected(comp_id)
            if self.on_context_menu_request:
                global_pos = self.tree.viewport().mapToGlobal(pos)
                self.on_context_menu_request(comp_id, global_pos.x(), global_pos.y())
        except ValueError:
            pass

    def _on_double_click(self, index: QModelIndex):
        item = self.model.itemFromIndex(index)
        if not item:
            return

        node_id = item.data(Qt.ItemDataRole.UserRole)
        if not node_id:
            return

        # Create inline editor
        rect = self.tree.visualRect(index)
        editor = QLineEdit(self.tree.viewport())
        editor.setGeometry(rect)
        label = item.data(Qt.ItemDataRole.UserRole + 1)
        if not isinstance(label, str):
            label = item.text().lstrip("🔒 ")
        editor.setText(label)
        editor.setFocus()
        editor.show()
        editor.selectAll()

        is_saving = False

        def save_edit():
            nonlocal is_saving
            if is_saving:
                return
            is_saving = True
            new_label = editor.text().strip()
            if new_label and self.on_rename_request:
                try:
                    self.on_rename_request(UUID(node_id), new_label)
                except ValueError:
                    pass
            editor.deleteLater()

        def cancel_edit():
            nonlocal is_saving
            is_saving = True
            editor.deleteLater()

        editor.returnPressed.connect(save_edit)
        editor.editingFinished.connect(save_edit)

        class EscapeEventFilter(QObject):
            def __init__(self, callback):
                super().__init__()
                self.callback = callback

            def eventFilter(self, obj, event):
                if (
                    event.type() == QEvent.Type.KeyPress
                    and event.key() == Qt.Key.Key_Escape
                ):
                    self.callback()
                    return True
                return super().eventFilter(obj, event)

        editor.escape_filter = EscapeEventFilter(cancel_edit)
        editor.installEventFilter(editor.escape_filter)
