from uuid import UUID

from models import WorkspaceState


def recalculate_tree(state: WorkspaceState):
    """
    Performs a full top-down pass over the WorkspaceState flat map to:
    1. Sort children visually (top-to-bottom by Y coordinate).
    2. Auto-assign hierarchical numbers (e.g. '1', '1.1', '1.2').
    3. Auto-calculate absoluteBounds based on relative bounds + parent absoluteBounds.

    Because the tree is small (dozens of nodes), doing a full self-healing
    recalculation on every mutation is incredibly fast and avoids edge-case bugs.
    """

    def process_node(
        comp_id: UUID,
        parent_absolute_x: int,
        parent_absolute_y: int,
        number_prefix: str,
    ):
        comp = state.components.get(comp_id)
        if not comp:
            return

        # 1. Update Absolute Bounds
        comp.absoluteBounds.x = comp.bounds.x + parent_absolute_x
        comp.absoluteBounds.y = comp.bounds.y + parent_absolute_y
        comp.absoluteBounds.w = comp.bounds.w
        comp.absoluteBounds.h = comp.bounds.h

        # 2. Assign Number
        comp.number = number_prefix

        # 3. Sort children by Y coordinate (top to bottom)
        valid_children = [cid for cid in comp.childrenIds if cid in state.components]
        sorted_children = sorted(
            valid_children, key=lambda cid: state.components[cid].bounds.y
        )
        comp.childrenIds = sorted_children

        # 4. Recurse into children
        for idx, child_id in enumerate(sorted_children):
            child_number = f"{number_prefix}.{idx + 1}"
            process_node(
                child_id,
                parent_absolute_x=comp.absoluteBounds.x,
                parent_absolute_y=comp.absoluteBounds.y,
                number_prefix=child_number,
            )

    # Clean up root components list
    valid_roots = [rid for rid in state.rootComponents if rid in state.components]
    sorted_roots = sorted(valid_roots, key=lambda rid: state.components[rid].bounds.y)
    state.rootComponents = sorted_roots

    # Process from roots down
    for idx, root_id in enumerate(sorted_roots):
        process_node(
            root_id,
            parent_absolute_x=0,
            parent_absolute_y=0,
            number_prefix=str(idx + 1),
        )
