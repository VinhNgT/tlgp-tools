"""Tree traversal and hierarchical data structures for component boundaries."""

from collections.abc import Generator
from uuid import UUID

from .core import Component, WorkspaceState


class TreeUtils:
    """Utility functions for traversing and manipulating the flat map WorkspaceState."""

    @staticmethod
    def get_children(state: WorkspaceState, parent_id: UUID | None) -> list[Component]:
        """Get the direct children of a parent (or root components if parent_id is None)."""
        if parent_id is None:
            child_ids = state.rootComponents
        else:
            parent = state.components.get(parent_id)
            if not parent:
                return []
            child_ids = parent.childrenIds

        return [state.components[cid] for cid in child_ids if cid in state.components]

    @staticmethod
    def walk_dfs(
        state: WorkspaceState, start_id: UUID | None = None
    ) -> Generator[Component]:
        """
        Yields components in depth-first order.
        If start_id is None, walks the entire tree starting from rootComponents.
        """
        children = TreeUtils.get_children(state, start_id)
        for child in children:
            yield child
            yield from TreeUtils.walk_dfs(state, child.id)

    @staticmethod
    def has_children(state: WorkspaceState, component_id: UUID) -> bool:
        """Returns True if the component has any direct children."""
        comp = state.components.get(component_id)
        if not comp:
            return False
        return len(comp.childrenIds) > 0
