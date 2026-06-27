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

    # Build UUID → annotated image filename lookup
    annotated_mapping: dict[str, str] = {}
    if "annotated" in mapping:
        # "both" mode export
        annotated_mapping = mapping["annotated"].get("components", {})
        root_images = mapping["annotated"].get("root", [])
    else:
        # single-mode export (annotated only)
        annotated_mapping = mapping.get("components", {})
        root_images = mapping.get("root", [])

    # Walk in post-order DFS to get the component ordering (for readable ordering in JSON)
    ordered_uuids = _walk_post_order_dfs(state)

    nodes = []

    # 1. Add the Screen node (always "0")
    screen_name_val = state.screen.name.strip()
    screen_name = f"[TODO: Vietnamese screen name. Suggestion: {screen_name_val}]" if screen_name_val else _TODO_SCREEN_NAME

    screen_desc_val = state.screen.description.strip()
    screen_desc = f"[TODO: Vietnamese screen description (high-level summary) - NOT a list/restatement of UI elements. Suggestion: {screen_desc_val}]" if screen_desc_val else _TODO_SCREEN_DESC

    screen_children_ids = [str(rid) for rid in state.rootComponents if rid in state.components]

    nodes.append({
        "id": "0",
        "label": screen_name,
        "description": screen_desc,
        "imageFiles": list(root_images),
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

        # If it has no children, it's a leaf node (element), so we set a TODO controlType
        is_leaf = len(comp.childrenIds) == 0
        control_type = ""
        if is_leaf:
            control_type = "[TODO: Control Type (e.g. Button, Text, Icon, Image)]"

        image_file = annotated_mapping.get(uuid_str)
        image_files = [image_file] if image_file else []

        comp_node = {
            "id": uuid_str,
            "label": label,
            "controlType": control_type,
            "required": "",
            "maxLength": "",
            "editable": "",
            "description": _TODO_DESCRIPTION,
            "imageFiles": image_files,
            "childrenIds": [str(cid) for cid in comp.childrenIds if cid in state.components],
            "interactions": [],
            "apis": [],
        }
        nodes.append(comp_node)

    return {
        "sectionPrefix": section_prefix,
        "imageDir": image_dir,
        "rootId": "0",
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
