"""Scaffold a spec.json skeleton from workspace state and exported images.

Derives all structural fields (component hierarchy, image paths,
cross-references) automatically from the annotator's workspace
state and the image export mapping. The AI agent only needs to fill in semantic
fields (Vietnamese labels, descriptions, interactions, APIs).
"""

from __future__ import annotations

import json
from pathlib import Path
from uuid import UUID

from pydantic import BaseModel
from tlgp_contracts import (
    TreeUtils,
    WorkspaceState,
)
from tlgp_logger import get_logger

logger = get_logger(__name__)


class ScaffoldResult(BaseModel):
    """Structured result from a scaffold operation."""

    spec_path: str
    components: int = 0
    screen_name: str = ""


class PrepareAnalysisResult(BaseModel):
    """Structured result from a prepare_analysis operation (export + scaffold)."""

    spec_path: str
    export_path: str = ""
    components: int = 0
    screen_name: str = ""
    annotated_images: int = 0
    raw_images: int = 0


# Placeholder constants for fields the AI must fill via vision analysis
_TODO_LABEL = "[TODO: Descriptive Vietnamese label from vision analysis]"
_TODO_DESCRIPTION = "[TODO: Vietnamese description (high-level summary) from vision analysis - NOT a list/restatement of UI elements]"
_TODO_SCREEN_NAME = "[TODO: Vietnamese screen name]"
_TODO_SCREEN_DESC = "[TODO: Vietnamese screen description (high-level summary) - NOT a list/restatement of UI elements]"


def _load_mapping(export_dir: Path) -> dict:
    """Load the mapping.json from an image export directory."""
    mapping_path = export_dir / "mapping.json"
    if not mapping_path.exists():
        raise FileNotFoundError(
            f"mapping.json not found in {export_dir}. "
            f"Run export_images first to export cropped images."
        )
    return json.loads(mapping_path.read_text(encoding="utf-8"))


def _walk_post_order_dfs(
    state: WorkspaceState,
    parent_id: UUID | None = None,
) -> list[UUID]:
    """Walk the component tree in post-order DFS (children before parents).

    Returns a flat list of component UUIDs in the order they should appear
    in the spec.json nodes array.
    """
    result: list[UUID] = []
    children = TreeUtils.get_children(state, parent_id)
    for child in children:
        result.extend(_walk_post_order_dfs(state, child.id))
        result.append(child.id)
    return result


def build_scaffold(
    state: WorkspaceState,
    export_dir: Path,
    section_prefix: str = "1.1",
) -> dict:
    """Build a scaffold spec.json dict from workspace state and exported images.

    Args:
        state: The annotator's workspace state (flat-map).
        export_dir: Absolute path to the directory created by export_images.
        section_prefix: Section number prefix for the generated document.

    Returns:
        A dict matching the ScreenSpec schema, with structural fields
        pre-filled and semantic fields set to TODO placeholders.
    """
    mapping = _load_mapping(export_dir)

    image_dir = str(export_dir.resolve())

    # Build UUID → image filename lookup
    annotated_mapping: dict[str, str] = {}
    raw_mapping: dict[str, str] = {}
    if "annotated" in mapping:
        # "both" mode export
        annotated_mapping = mapping["annotated"].get("components", {})
        annotated_root_images = mapping["annotated"].get("root", [])
        raw_mapping = mapping["raw"].get("components", {})
        raw_root_images = mapping["raw"].get("root", [])
    else:
        # single-mode export (annotated only)
        annotated_mapping = mapping.get("components", {})
        annotated_root_images = mapping.get("root", [])
        raw_mapping = {}
        raw_root_images = []

    # Build UUID -> integer ID mapping based on component number
    uuid_to_id = {}
    assigned_ids = {0}  # 0 is reserved for Screen root
    for uuid, comp in state.components.items():
        if comp.number and comp.number.isdigit():
            val = int(comp.number)
            uuid_to_id[uuid] = val
            assigned_ids.add(val)

    next_id = 1
    for uuid in state.components:
        if uuid not in uuid_to_id:
            while next_id in assigned_ids:
                next_id += 1
            uuid_to_id[uuid] = next_id
            assigned_ids.add(next_id)
            next_id += 1

    # Walk in post-order DFS to get the component ordering (for readable ordering in JSON)
    ordered_uuids = _walk_post_order_dfs(state)

    nodes = []

    # 1. Add the Screen node (always 0)
    screen_name_val = state.screen.name.strip()
    screen_name = f"[TODO: Vietnamese screen name. Suggestion: {screen_name_val}]" if screen_name_val else _TODO_SCREEN_NAME

    screen_desc_val = state.screen.description.strip()
    screen_desc = f"[TODO: Vietnamese screen description (high-level summary) - NOT a list/restatement of UI elements. Suggestion: {screen_desc_val}]" if screen_desc_val else _TODO_SCREEN_DESC

    screen_children_ids = [uuid_to_id[rid] for rid in state.rootComponents if rid in state.components and rid in uuid_to_id]

    raw_screen_image_rel = raw_root_images[0] if raw_root_images else (annotated_root_images[0] if annotated_root_images else "raw/root.png")
    annotated_screen_images_rel = list(annotated_root_images) if annotated_root_images else (list(raw_root_images) if raw_root_images else [])

    raw_screen_image = str(export_dir / raw_screen_image_rel)
    annotated_screen_images = [str(export_dir / img) for img in annotated_screen_images_rel]

    nodes.append({
        "id": 0,
        "absoluteBounds": {
            "x": 0,
            "y": 0,
            "w": state.image.width if state.image else 375,
            "h": state.image.height if state.image else 812,
        },
        "label": screen_name,
        "controlType": "Screen",
        "description": screen_desc,
        "rawImage": raw_screen_image,
        "annotatedImages": annotated_screen_images,
        "required": False,
        "editable": False,
        "childrenIds": screen_children_ids,
        "interactions": [],
        "apis": [],
    })

    # 2. Add each component node
    for uuid in ordered_uuids:
        comp = state.components.get(uuid)
        if comp is None:
            logger.warning("Component UUID %s in DFS order but missing from state", uuid)
            continue

        uuid_str = str(uuid)
        comp_label = comp.label.strip()
        label = f"[TODO: Descriptive Vietnamese label from vision analysis. Suggestion: {comp_label}]" if comp_label else _TODO_LABEL

        # If it has no children, it's a leaf node (element), otherwise it's a container/sub-component
        is_leaf = len(comp.childrenIds) == 0
        if is_leaf:
            control_type = "[TODO: Widget Type (e.g. Button, Text, Icon, Input, Tabbar)]"
        else:
            control_type = "Component"

        raw_comp_img_rel = raw_mapping.get(uuid_str) or annotated_mapping.get(uuid_str) or f"raw/{uuid_str}.png"
        ann_comp_img_rel = annotated_mapping.get(uuid_str) or raw_mapping.get(uuid_str)
        annotated_comp_images_rel = [ann_comp_img_rel] if ann_comp_img_rel else []

        raw_comp_img = str(export_dir / raw_comp_img_rel)
        annotated_comp_images = [str(export_dir / img) for img in annotated_comp_images_rel]

        comp_node = {
            "id": uuid_to_id[uuid],
            "absoluteBounds": {
                "x": comp.bounds.x if comp.bounds else 0,
                "y": comp.bounds.y if comp.bounds else 0,
                "w": comp.bounds.w if comp.bounds else 0,
                "h": comp.bounds.h if comp.bounds else 0,
            },
            "label": label,
            "controlType": control_type,
            "required": False,
            "maxLength": None,
            "editable": False,
            "description": _TODO_DESCRIPTION,
            "rawImage": raw_comp_img,
            "annotatedImages": annotated_comp_images,
            "childrenIds": [uuid_to_id[cid] for cid in comp.childrenIds if cid in state.components and cid in uuid_to_id],
            "interactions": [],
            "apis": [],
        }
        nodes.append(comp_node)

    return {
        "$schema": "schema.json",
        "sectionPrefix": section_prefix,
        "rootId": 0,
        "nodes": nodes,
    }


def scaffold_and_save(
    state: WorkspaceState,
    export_dir: str,
    section_prefix: str = "1.1",
) -> ScaffoldResult:
    """Build a scaffold and save it as spec.json in the export directory.

    Args:
        state: The annotator's workspace state.
        export_dir: Absolute path to the directory created by export_images.
        section_prefix: Section number prefix for the generated document.

    Returns:
        ScaffoldResult with the path to the saved file and summary stats.
    """
    export_path = Path(export_dir).resolve()
    if not export_path.is_dir():
        raise FileNotFoundError(f"Export directory does not exist: {export_dir}")

    scaffold = build_scaffold(state, export_path, section_prefix)

    # Write the JSON schema file to the export directory
    from tlgp_contracts import ScreenSpec
    schema_path = export_path / "schema.json"
    schema_path.write_text(
        json.dumps(ScreenSpec.model_json_schema(), indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    output_path = export_path / "spec.json"
    output_path.write_text(
        json.dumps(scaffold, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    components_count = len(scaffold["nodes"]) - 1  # excluding screen

    logger.info(
        "Saved spec scaffold to %s (%d components)",
        output_path,
        components_count,
    )

    # Find screen node name
    screen_node = next(n for n in scaffold["nodes"] if n["id"] == scaffold["rootId"])

    return ScaffoldResult(
        spec_path=str(output_path),
        components=components_count,
        screen_name=screen_node["label"],
    )
