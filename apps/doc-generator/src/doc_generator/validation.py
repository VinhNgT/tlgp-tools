"""Validation logic for spec data.

Performs structural and semantic checks on a parsed ScreenSpec object:
image existence, content completeness warnings, bottom-up DFS traversal order.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field
from tlgp_contracts import (
    DEFAULT_UNIT_COST_ANNOTATION,
    DEFAULT_UNIT_COST_API,
    DEFAULT_UNIT_LIMIT,
)

from .models import ScreenSpec, Api


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
    non_leaf = [n for n in data.nodes if n.id != data.rootId and (len(n.childrenIds) > 0 or len(n.imageFiles) > 0)]
    all_components = [screen] + non_leaf

    result = ValidationResult(
        components=len(all_components),
        non_leaf=len(non_leaf),
        ui_elements=sum(len(c.childrenIds) for c in all_components),
        interactions=sum(len(c.interactions) for c in all_components),
        apis=len(data.all_apis),
    )

    base_dir = Path(data.imageDir).resolve()

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
            node_type = "Component" if (len(node.childrenIds) > 0 or len(node.imageFiles) > 0) else "Element"
            result.warnings.append(
                f"{node_type} '{node.label}' (id={node.id}) is defined in nodes list but never referenced in the tree hierarchy"
            )

    # --- Image checks ---
    for comp in all_components:
        is_screen = (comp.id == data.rootId)
        if not skip_image_validation:
            if not comp.imageFiles:
                if is_screen:
                    result.errors.append("No screen-level images specified")
                else:
                    result.errors.append(
                        f"Component '{comp.label}' (id={comp.id}): no imageFiles specified"
                    )
            for img_file in comp.imageFiles:
                if img_file:
                    img = data.resolve_image(img_file)
                    if not img.resolve().is_relative_to(base_dir):
                        err_msg = (
                            f"Screen image path escapes imageDir: {img_file}"
                            if is_screen
                            else f"Component '{comp.label}' (id={comp.id}): image path escapes imageDir: {img_file}"
                        )
                        result.errors.append(err_msg)
                    elif not img.exists():
                        err_msg = (
                            f"Screen image not found: {img}"
                            if is_screen
                            else f"Component '{comp.label}' (id={comp.id}): image not found: {img}"
                        )
                        result.errors.append(err_msg)

        if not comp.description:
            if is_screen:
                result.errors.append("Screen description is empty")
            else:
                result.errors.append(
                    f"Component '{comp.label}' (id={comp.id}): empty description"
                )

        if not comp.childrenIds:
            if is_screen:
                result.errors.append("Screen has no children")
            else:
                result.errors.append(
                    f"Component '{comp.label}' (id={comp.id}): "
                    f"no children specified (must have at least one child)"
                )

    # Update summary images count
    result.images = sum(len(c.imageFiles) for c in all_components)

    # --- Content completeness warnings ---
    # Check for empty controlType in Element (leaf) nodes that are reachable
    empty_controls = 0
    for node_id in reachable:
        node = nodes_dict.get(node_id)
        if node and node_id != data.rootId and len(node.childrenIds) == 0:
            control_type = node.controlType or ""
            if not control_type.strip():
                empty_controls += 1
    if empty_controls:
        result.warnings.append(
            f"{empty_controls} child element(s) have empty controlType"
        )

    if screen.description and len(screen.description) < 10:
        result.warnings.append(
            f"Screen description is suspiciously short (< 10 chars): '{screen.description}'"
        )

    for comp in non_leaf:
        if comp.id in reachable:
            if comp.description and len(comp.description) < 10:
                result.warnings.append(
                    f"Component '{comp.label}' (id={comp.id}) description is suspiciously short (< 10 chars)"
                )
            if not comp.label.strip():
                result.warnings.append(f"Component (id={comp.id}) has an empty label")
            control_type = comp.controlType or ""
            if len(comp.childrenIds) > 0 and control_type.strip():
                result.warnings.append(
                    f"Component '{comp.label}' (id={comp.id}) has children but also specifies a controlType ('{control_type}'). controlType should only be used on leaf elements."
                )

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

    # Check for structural errors in API parameters
    for api in data.all_apis:
        def _validate_dto_list(dtos: list[ApiPayload], root_type: str | None, side: str, api_name: str) -> None:
            if not dtos:
                if root_type:
                    result.errors.append(
                        f"API '{api_name}' {side}RootType '{root_type}' is specified but {side} list is empty"
                    )
                return

            seen_ids = set()
            dto_map = {}
            for payload in dtos:
                obj_type = (payload.type or "").strip()
                if not obj_type:
                    result.errors.append(
                        f"API '{api_name}' has a DTO with an empty type in {side}"
                    )
                    continue

                lower_id = obj_type.lower()
                if lower_id in seen_ids:
                    result.errors.append(
                        f"API '{api_name}' has duplicate DTO type '{payload.type}' in {side}"
                    )
                seen_ids.add(lower_id)
                dto_map[lower_id] = payload

            if not root_type:
                result.warnings.append(
                    f"API '{api_name}' has DTOs defined in {side} but no {side}RootType is specified"
                )
                return

            lower_root = root_type.strip().lower()
            if lower_root not in dto_map:
                result.errors.append(
                    f"API '{api_name}' {side}RootType '{root_type}' not found in {side} DTOs"
                )
                return

            visited = set()
            rec_stack = set()

            def dfs(dto_id: str):
                lower_id = dto_id.strip().lower()
                if lower_id in rec_stack:
                    result.errors.append(
                        f"API '{api_name}' {side} DTO cycle detected at '{dto_id}'"
                    )
                    return
                if lower_id in visited:
                    return
                
                visited.add(lower_id)
                rec_stack.add(lower_id)
                
                payload = dto_map.get(lower_id)
                if payload:
                    for field in payload.fields:
                        if field.type:
                            field_lower_type = field.type.strip().lower()
                            if field_lower_type in dto_map:
                                dfs(field.type)
                
                rec_stack.remove(lower_id)

            dfs(root_type)

            # Warn about unreachable DTOs
            for lower_id, payload in dto_map.items():
                if lower_id not in visited:
                    result.warnings.append(
                        f"API '{api_name}' {side} DTO '{payload.type}' is defined but unreachable from root '{root_type}'"
                    )

        _validate_dto_list(api.request, api.requestRootType, "request", api.name)
        _validate_dto_list(api.response, api.responseRootType, "response", api.name)

        all_params = []
        for payload in api.request:
            all_params.extend(payload.fields)
        for payload in api.response:
            all_params.extend(payload.fields)

        for param in all_params:
            param_name = param.name or ""
            param_desc = param.description or ""
            if not param_name.strip() or not param_desc.strip():
                result.warnings.append(
                    f"API '{api.name}' has an ApiParam with empty name or description"
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

    # --- Final validity ---
    if result.errors:
        result.valid = False

    return result
