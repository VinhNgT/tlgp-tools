"""Scaffold an analysis.json skeleton from workspace state and exported images.

Derives all structural fields (component hierarchy, DFS ordering, image paths,
isLeaf flags, cross-references) automatically from the annotator's workspace
state and the image export mapping. The AI agent only needs to fill in semantic
fields (Vietnamese labels, descriptions, interactions, APIs).
"""

from __future__ import annotations

import json
from pathlib import Path
from uuid import UUID

from pydantic import BaseModel
from tlgp_contracts import (
    DEFAULT_UNIT_COST_ANNOTATION,
    DEFAULT_UNIT_COST_API,
    DEFAULT_UNIT_LIMIT,
    TreeUtils,
    WorkspaceState,
)
from tlgp_logger import get_logger

logger = get_logger(__name__)


class ScaffoldResult(BaseModel):
    """Structured result from a scaffold operation."""

    analysis_path: str
    components: int = 0
    screen_name: str = ""


class PrepareAnalysisResult(BaseModel):
    """Structured result from a prepare_analysis operation (export + scaffold)."""

    analysis_path: str
    export_path: str = ""
    components: int = 0
    screen_name: str = ""
    annotated_images: int = 0
    raw_images: int = 0


# Placeholder constants for fields the AI must fill via vision analysis
_TODO_LABEL = "[TODO: Descriptive Vietnamese label from vision analysis]"
_TODO_DESCRIPTION = "[TODO: Vietnamese description from vision analysis]"
_TODO_SCREEN_NAME = "[TODO: Vietnamese screen name]"
_TODO_SCREEN_DESC = "[TODO: Vietnamese screen description]"


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
    in the analysis.json components array.
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
    """Build a scaffold analysis.json dict from workspace state and exported images.

    Args:
        state: The annotator's workspace state (flat-map).
        export_dir: Absolute path to the directory created by export_images.
        section_prefix: Section number prefix for the generated document.

    Returns:
        A dict matching the analysis.json schema, with structural fields
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

    # Walk in post-order DFS to get the component ordering
    ordered_uuids = _walk_post_order_dfs(state)

    # Build the components array with sequential IDs
    components: list[dict] = []
    uuid_to_seq_id: dict[UUID, int] = {}
    seq_id = 1

    for uuid in ordered_uuids:
        comp = state.components.get(uuid)
        if comp is None:
            logger.warning("Component UUID %s in DFS order but missing from state", uuid)
            continue

        is_leaf = len(comp.childrenIds) == 0
        uuid_str = str(uuid)
        image_file = annotated_mapping.get(uuid_str)

        uuid_to_seq_id[uuid] = seq_id

        # Build children array referencing annotated children
        component_children = []
        for child_idx, child_uuid in enumerate(comp.childrenIds, start=1):
            if child_uuid in uuid_to_seq_id:
                component_children.append({
                    "stt": child_idx,
                    "componentId": uuid_to_seq_id[child_uuid]
                })

        comp_label = comp.label.strip()
        label = f"[TODO: Descriptive Vietnamese label from vision analysis. Suggestion: {comp_label}]" if comp_label else _TODO_LABEL

        component_entry: dict = {
            "id": seq_id,
            "label": label,
            "description": _TODO_DESCRIPTION,
            "isLeaf": is_leaf,
            "imageFile": image_file if not is_leaf else None,
            "children": component_children,
            "interactions": [],
            "apis": [],
        }
        components.append(component_entry)
        seq_id += 1

    # Build screen.topLevelChildren from rootComponents using componentId
    top_level_children: list[dict] = []
    for stt_idx, root_uuid in enumerate(state.rootComponents, start=1):
        if root_uuid not in uuid_to_seq_id:
            continue
        top_level_children.append({
            "stt": stt_idx,
            "componentId": uuid_to_seq_id[root_uuid]
        })

    # Screen images (retain prefix)
    screen_image_files = list(root_images)

    # Use workspace screen name/description if provided, otherwise placeholder
    screen_name_val = state.screen.name.strip()
    screen_name = f"[TODO: Vietnamese screen name. Suggestion: {screen_name_val}]" if screen_name_val else _TODO_SCREEN_NAME
    
    screen_desc_val = state.screen.description.strip()
    screen_desc = f"[TODO: Vietnamese screen description. Suggestion: {screen_desc_val}]" if screen_desc_val else _TODO_SCREEN_DESC

    scaffold: dict = {
        "sectionPrefix": section_prefix,
        "imageDir": image_dir,
        "unitLimit": {
            "annotationCost": DEFAULT_UNIT_COST_ANNOTATION,
            "apiCost": DEFAULT_UNIT_COST_API,
            "maxUnits": DEFAULT_UNIT_LIMIT,
        },
        "screen": {
            "name": screen_name,
            "description": screen_desc,
            "imageFiles": screen_image_files,
            "topLevelChildren": top_level_children,
            "interactions": [],
            "apis": [],
        },
        "components": components,
        "discrepancies": [],
    }

    return scaffold


def scaffold_and_save(
    state: WorkspaceState,
    export_dir: str,
    section_prefix: str = "1.1",
) -> ScaffoldResult:
    """Build a scaffold and save it as analysis.json in the export directory.

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

    output_path = export_path / "analysis.json"
    output_path.write_text(
        json.dumps(scaffold, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    logger.info(
        "Saved analysis scaffold to %s (%d components)",
        output_path,
        len(scaffold["components"]),
    )

    return ScaffoldResult(
        analysis_path=str(output_path),
        components=len(scaffold["components"]),
        screen_name=scaffold["screen"]["name"],
    )
