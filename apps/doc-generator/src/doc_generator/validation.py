"""Validation logic for spec data.

Performs structural and semantic checks on a parsed ScreenSpec object:
image existence, content completeness warnings, bottom-up DFS traversal order.
"""

from __future__ import annotations

from pydantic import BaseModel, Field
from tlgp_contracts import (
    DEFAULT_UNIT_COST_ANNOTATION,
    DEFAULT_UNIT_COST_API,
    DEFAULT_UNIT_LIMIT,
    ScreenSpec,
)


class ValidationResult(BaseModel):
    """Structured outcome of spec data validation."""

    valid: bool = True
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    # Summary statistics (populated regardless of validity)
    components: int = 0
    non_leaf: int = 0
    ui_elements: int = 0
    interactions: int = 0
    apis: int = 0
    images: int = 0
    discrepancies: int = 0


def validate_spec(data: ScreenSpec, skip_image_validation: bool = False) -> ValidationResult:
    """Run all validation checks against parsed spec data.

    This is the single source of truth for validation logic, consumed by
    both the CLI and any external caller.
    """
    # Ensure exactly one root screen node exists
    screens = [n for n in data.nodes if n.id == data.rootId]
    if len(screens) != 1:
        result = ValidationResult(valid=False)
        result.errors.append(
            f"Screen component (id == {data.rootId}) must be defined exactly once. Found: {len(screens)}"
        )
        return result

    # Check for duplicate IDs in the nodes list
    seen_ids = set()
    for n in data.nodes:
        if n.id in seen_ids:
            result = ValidationResult(valid=False)
            result.errors.append(f"Duplicate node ID defined in nodes list: {n.id}")
            return result
        seen_ids.add(n.id)

    screen = data.screen
    non_leaf = [n for n in data.nodes if n.id != data.rootId and len(n.childrenIds) > 0]
    all_components = [screen, *non_leaf]

    result = ValidationResult(
        components=len(all_components),
        non_leaf=len(non_leaf),
        ui_elements=sum(len(c.childrenIds) for c in all_components),
        interactions=sum(len(c.interactions) for c in all_components),
        apis=len(data.all_apis),
    )



    # --- Structural integrity checks (Parent-child references) ---
    nodes_dict = data.nodes_map
    referenced_child_ids = set()
    parent_map = {}

    for parent in all_components:
        for cid in parent.childrenIds:
            if cid not in nodes_dict:
                result.errors.append(
                    f"Component '{parent.label}' (id={parent.id}) references non-existent child ID: '{cid}'"
                )
                continue

            # Check for multiple parents
            if cid in parent_map:
                result.errors.append(
                    f"Child ID '{cid}' has multiple parents: '{parent_map[cid]}' and '{parent.id}'"
                )
            else:
                parent_map[cid] = parent.id

            referenced_child_ids.add(cid)

    # --- Cycle detection ---
    visited = set()
    path = set()

    def check_cycle(node_id: str) -> bool:
        if node_id in path:
            return True
        if node_id in visited:
            return False

        path.add(node_id)
        node = nodes_dict.get(node_id)
        if node:
            for cid in node.childrenIds:
                if check_cycle(cid):
                    return True
        path.remove(node_id)
        visited.add(node_id)
        return False

    if check_cycle(data.rootId):
        result.errors.append("Cyclic reference detected in components tree hierarchy")

    # --- Reachability and Orphan validation ---
    reachable = set()
    def traverse(node_id: str):
        if node_id in reachable:
            return
        reachable.add(node_id)
        node = nodes_dict.get(node_id)
        if node:
            for cid in node.childrenIds:
                traverse(cid)
    traverse(data.rootId)

    # Warn about unreachable orphan nodes
    for node in data.nodes:
        if node.id != data.rootId and node.id not in reachable:
            node_type = "Component" if len(node.childrenIds) > 0 else "Element"
            result.warnings.append(
                f"{node_type} '{node.label}' (id={node.id}) is defined in nodes list but never referenced in the tree hierarchy"
            )

    # --- Image checks ---
    if not skip_image_validation:
        # 1. Check annotatedImages for components
        for comp in all_components:
            is_screen = (comp.id == data.rootId)
            if not comp.annotatedImages:
                if is_screen:
                    result.errors.append("No screen-level images specified")
                else:
                    result.errors.append(
                        f"Component '{comp.label}' (id={comp.id}): no annotatedImages specified"
                    )
            for img_file in comp.annotatedImages:
                if img_file:
                    img = data.resolve_annotated_image(img_file)
                    if not img.exists():
                        err_msg = (
                            f"Screen image not found: {img}"
                            if is_screen
                            else f"Component '{comp.label}' (id={comp.id}): image not found: {img}"
                        )
                        result.errors.append(err_msg)

        # 2. Check rawImage exists for all nodes
        for node in data.nodes:
            is_screen = (node.id == data.rootId)
            if node.rawImage and node.rawImage != "dummy.png":
                raw_img = data.resolve_raw_image(node.rawImage)
                if not raw_img.exists():
                    err_msg = (
                        f"Screen raw image not found: {raw_img}"
                        if is_screen
                        else f"Node '{node.label}' (id={node.id}): raw image not found: {raw_img}"
                    )
                    result.errors.append(err_msg)

    # --- Structure checks ---
    for comp in all_components:
        is_screen = (comp.id == data.rootId)
        if not comp.childrenIds:
            if is_screen:
                result.errors.append("Screen has no children")
            else:
                result.errors.append(
                    f"Component '{comp.label}' (id={comp.id}): "
                    f"no children specified (must have at least one child)"
                )

    # Update summary images count
    result.images = sum(len(c.annotatedImages) for c in all_components)

    for comp in non_leaf:
        if comp.id in reachable:
            if not comp.label.strip():
                result.warnings.append(f"Component (id={comp.id}) has an empty label")
            # Non-leaf components must specify controlType (container/screen type), so we no longer warn about controlType on non-leaf nodes.

    # Check for empty interaction actions/reactions
    for node in data.nodes:
        if node.id in reachable:
            for i, inter in enumerate(node.interactions):
                if not inter.action.strip() or not inter.reaction.strip():
                    result.warnings.append(
                        f"Node '{node.label}' (id={node.id}) has an Interaction at index {i} with empty action or reaction"
                    )

    # Empty labels on children checks
    for parent in all_components:
        if parent.id in reachable:
            for i, cid in enumerate(parent.childrenIds):
                child = nodes_dict.get(cid)
                if child and not child.label.strip():
                    if parent.id == data.rootId:
                        result.warnings.append(
                            f"Child element in Screen '{parent.label}' has an empty label"
                        )
                    else:
                        result.warnings.append(
                            f"Child element {i + 1} in Component '{parent.label}' has an empty label"
                        )



    # --- Unit limit complexity checks ---
    def _check_unit_limit(annotations: int, apis: int, owner: str) -> None:
        units = (
            annotations * DEFAULT_UNIT_COST_ANNOTATION + apis * DEFAULT_UNIT_COST_API
        )
        if units > DEFAULT_UNIT_LIMIT:
            result.errors.append(
                f"{owner} exceeds the unit limit: {units}/{DEFAULT_UNIT_LIMIT} units "
                f"({annotations} annotations × {DEFAULT_UNIT_COST_ANNOTATION} + "
                f"{apis} APIs × {DEFAULT_UNIT_COST_API} = {units})"
            )

    if screen.id in reachable:
        _check_unit_limit(
            len(screen.childrenIds),
            len(screen.apis),
            f"Screen '{screen.label}'",
        )

    for comp in non_leaf:
        if comp.id in reachable:
            _check_unit_limit(
                len(comp.childrenIds),
                len(comp.apis),
                f"Component '{comp.label}' (id={comp.id})",
            )

    # --- Strict controlType validations ---
    for node in data.nodes:
        is_screen = (node.id == data.rootId)
        is_leaf = (len(node.childrenIds) == 0)

        if is_leaf:
            if node.controlType in {"Screen", "Component"}:
                result.errors.append(
                    f"Leaf node '{node.label}' (id={node.id}) has invalid controlType '{node.controlType}'. "
                    f"Must not be 'Screen' or 'Component'."
                )
        else:
            if is_screen:
                if node.controlType != "Screen":
                    result.errors.append(
                        f"Root screen node '{node.label}' (id={node.id}) has invalid controlType '{node.controlType}'. "
                        f"Must be 'Screen'."
                    )
            else:
                if node.controlType != "Component":
                    result.errors.append(
                        f"Non-root container node '{node.label}' (id={node.id}) has invalid controlType '{node.controlType}'. "
                        f"Must be 'Component'."
                    )

    # --- Check for TODO placeholders ---
    for node in data.nodes:
        if node.id in reachable:
            if "TODO" in node.label:
                result.errors.append(
                    f"Placeholder detected in label of node '{node.label}' (id={node.id})"
                )
            if "TODO" in node.description:
                result.errors.append(
                    f"Placeholder detected in description of node '{node.label}' (id={node.id})"
                )
            if "TODO" in node.controlType:
                result.errors.append(
                    f"Placeholder detected in controlType of node '{node.label}' (id={node.id})"
                )
            for i, inter in enumerate(node.interactions):
                if "TODO" in inter.action:
                    result.errors.append(
                        f"Placeholder detected in interaction {i + 1} action of node '{node.label}' (id={node.id})"
                    )
                if "TODO" in inter.reaction:
                    result.errors.append(
                        f"Placeholder detected in interaction {i + 1} reaction of node '{node.label}' (id={node.id})"
                    )
            for api in node.apis:
                if "TODO" in api.name:
                    result.errors.append(
                        f"Placeholder detected in API name '{api.name}' of node '{node.label}' (id={node.id})"
                    )
                if "TODO" in api.url:
                    result.errors.append(
                        f"Placeholder detected in API URL '{api.url}' of node '{node.label}' (id={node.id})"
                    )
                for payload in api.request:
                    for field in payload.fields:
                        if "TODO" in field.name:
                            result.errors.append(
                                f"Placeholder detected in API Request payload field name '{field.name}' of node '{node.label}' (id={node.id})"
                            )
                        if "TODO" in field.description:
                            result.errors.append(
                                f"Placeholder detected in API Request payload field description of '{field.name}' on node '{node.label}' (id={node.id})"
                            )
                for payload in api.response:
                    for field in payload.fields:
                        if "TODO" in field.name:
                            result.errors.append(
                                f"Placeholder detected in API Response payload field name '{field.name}' of node '{node.label}' (id={node.id})"
                            )
                        if "TODO" in field.description:
                            result.errors.append(
                                f"Placeholder detected in API Response payload field description of '{field.name}' on node '{node.label}' (id={node.id})"
                            )

    # --- Check for API payloads with missing root types ---
    for api in data.all_apis:
        if api.request and not api.requestRootType:
            result.warnings.append(
                f"API '{api.name}' has defined request payload fields but 'requestRootType' is missing. "
                "The request parameter table will be omitted."
            )
        if api.response and not api.responseRootType:
            result.warnings.append(
                f"API '{api.name}' has defined response payload fields but 'responseRootType' is missing. "
                "The response payload table will be omitted."
            )

    # --- Final validity ---
    if result.errors:
        result.valid = False

    return result

