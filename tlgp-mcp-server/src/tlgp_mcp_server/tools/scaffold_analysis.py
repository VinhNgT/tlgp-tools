"""Tool: scaffold_analysis — auto-generate analysis.json from annotations.

Pre-fills everything derivable from the annotation export (component IDs,
labels, isLeaf flags, image file mappings, child STT numbering, screen
metadata). Leaves empty slots for fields requiring agent intelligence.
"""

from __future__ import annotations

import json
import os
import re
from pathlib import Path


def _find_image_file(export_dir: Path, safe_name: str, comp_path: str) -> str | None:
    """Find the annotated image for a component by its path in the hierarchy.

    The annotation tool exports images named:
    - Root: {name}_annotated.png or {name}_annotated_part{N}.png
    - Components: {name}_{path}_annotated.png
    """
    if comp_path:
        candidate = f"{safe_name}_{comp_path}_annotated.png"
    else:
        candidate = f"{safe_name}_annotated.png"

    if (export_dir / candidate).exists():
        return candidate
    return None


def _find_root_images(export_dir: Path, safe_name: str) -> list[str]:
    """Find root-level annotated images (may be split into parts)."""
    pattern = re.compile(
        rf"^{re.escape(safe_name)}_annotated(?:_part\d+)?\.png$",
        re.IGNORECASE,
    )
    images = sorted(
        f.name for f in export_dir.iterdir()
        if f.is_file() and pattern.match(f.name)
    )
    return images


def _build_children(
    components: list[dict],
) -> list[dict]:
    """Build children entries with sequential STT numbering."""
    children = []
    for i, comp in enumerate(components):
        children.append({
            "stt": i + 1,
            "label": comp.get("label", f"Item {i + 1}"),
            "controlType": "",       # Agent fills: vision analysis
            "required": "",
            "maxLength": "",
            "editable": "",
            "description": "",       # Agent fills: vision + context
        })
    return children


def _process_component(
    comp: dict,
    export_dir: Path,
    safe_name: str,
    parent_path: str = "",
) -> dict:
    """Process a single component from the annotation hierarchy."""
    comp_id = comp.get("id", 0)
    comp_path = f"{parent_path}_{comp_id}" if parent_path else str(comp_id)
    children = comp.get("children", [])
    is_leaf = len(children) == 0

    result = {
        "id": comp_id,
        "label": comp.get("label", ""),
        "description": "",          # Agent fills
        "isLeaf": is_leaf,
        "imageFile": None,
        "children": [],
        "interactions": [],          # Agent fills
    }

    if not is_leaf:
        # Non-leaf: find the cropped annotated image
        result["imageFile"] = _find_image_file(export_dir, safe_name, comp_path)
        result["children"] = _build_children(children)

    return result


def scaffold_analysis_impl(
    annotation_json: str,
    section_prefix: str = "1.1",
    output_path: str | None = None,
) -> dict:
    """Generate an analysis.json template from annotation exports."""
    json_path = Path(annotation_json).resolve()

    if not json_path.exists():
        return {"error": f"Annotation JSON not found: {json_path}"}

    try:
        data = json.loads(json_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        return {"error": f"Invalid JSON: {e}"}

    export_dir = json_path.parent
    screen_name = data.get("screen_name", "Unknown")
    safe_name = export_dir.name
    components = data.get("components", [])

    # Process all components
    processed_components = [
        _process_component(comp, export_dir, safe_name)
        for comp in components
    ]

    # Build screen section
    root_images = _find_root_images(export_dir, safe_name)
    top_level_children = _build_children(components)

    analysis = {
        "sectionPrefix": section_prefix,
        "exportDir": str(export_dir),
        "components": processed_components,
        "screen": {
            "name": screen_name,
            "description": data.get("description", ""),
            "imageFiles": root_images,
            "topLevelChildren": top_level_children,
            "interactions": [],          # Agent fills
        },
        "apis": [],                      # Agent fills entirely
        "discrepancies": [],             # Agent fills if found
    }

    # Determine output path
    if output_path:
        out = Path(output_path).resolve()
    else:
        out = export_dir / "analysis.json"

    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(
        json.dumps(analysis, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    # Categorize fields
    pre_filled = [
        "sectionPrefix", "exportDir",
        "components[].id", "components[].label", "components[].isLeaf",
        "components[].imageFile", "components[].children[].stt",
        "components[].children[].label",
        "screen.name", "screen.description", "screen.imageFiles",
        "screen.topLevelChildren[].stt", "screen.topLevelChildren[].label",
    ]
    to_fill = [
        "components[].description",
        "components[].children[].controlType",
        "components[].children[].description",
        "components[].interactions[]",
        "screen.interactions[]",
        "apis[] (all API data)",
        "discrepancies[] (image-vs-code conflicts)",
    ]

    return {
        "output_path": str(out),
        "screen_name": screen_name,
        "component_count": len(processed_components),
        "non_leaf_count": sum(1 for c in processed_components if not c["isLeaf"]),
        "leaf_count": sum(1 for c in processed_components if c["isLeaf"]),
        "pre_filled": pre_filled,
        "to_fill": to_fill,
    }
