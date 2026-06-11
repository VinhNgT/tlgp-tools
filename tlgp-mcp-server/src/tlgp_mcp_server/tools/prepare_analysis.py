"""Tool: prepare_analysis — one-shot workspace discovery, scaffolding, and docs.

Combines the logic of list_exports, parse_annotations, and scaffold_analysis
into a single tool call. Returns the schema docs and control-type guide inline
so the agent gets everything in one response.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from tlgp_mcp_server.resources import ANALYSIS_SCHEMA_TEXT, CONTROL_TYPES_TEXT


# ============================================================
# Annotation discovery (from list_exports)
# ============================================================

_ANNOTATED_IMG_RE = re.compile(r".*_annotated(?:_part\d+)?\.png$", re.IGNORECASE)


def _find_screen_dir(output_dir: Path) -> Path | None:
    """Find the first annotation export subdirectory.

    The annotation tool creates a subfolder named after the screen
    (e.g., Chi_tiet_san_pham/) containing {name}.json + images.
    """
    for child in sorted(output_dir.iterdir()):
        if child.is_dir():
            json_file = child / f"{child.name}.json"
            if json_file.exists():
                return child

    # Check if output_dir itself is a screen dir
    json_candidate = output_dir / f"{output_dir.name}.json"
    if json_candidate.exists():
        return output_dir

    return None


# ============================================================
# Scaffolding (from scaffold_analysis)
# ============================================================


def _find_image_file(export_dir: Path, safe_name: str, comp_path: str) -> str | None:
    """Find the annotated image for a component by its hierarchy path."""
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
    return sorted(
        f.name for f in export_dir.iterdir()
        if f.is_file() and pattern.match(f.name)
    )


def _build_children(components: list[dict]) -> list[dict]:
    """Build children entries with sequential STT numbering."""
    children = []
    for i, comp in enumerate(components):
        children.append({
            "stt": i + 1,
            "label": comp.get("label", f"Item {i + 1}"),
            "controlType": "",
            "required": "",
            "maxLength": "",
            "editable": "",
            "description": "",
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
        "description": "",
        "isLeaf": is_leaf,
        "imageFile": None,
        "children": [],
        "interactions": [],
    }

    if not is_leaf:
        result["imageFile"] = _find_image_file(export_dir, safe_name, comp_path)
        result["children"] = _build_children(children)

    return result


def _scaffold(
    annotation_data: dict,
    export_dir: Path,
    section_prefix: str,
) -> dict:
    """Build the analysis.json structure from annotation data."""
    safe_name = export_dir.name
    screen_name = annotation_data.get("screen_name", "Unknown")
    components = annotation_data.get("components", [])

    processed_components = [
        _process_component(comp, export_dir, safe_name)
        for comp in components
    ]

    root_images = _find_root_images(export_dir, safe_name)
    top_level_children = _build_children(components)

    return {
        "sectionPrefix": section_prefix,
        "exportDir": str(export_dir),
        "components": processed_components,
        "screen": {
            "name": screen_name,
            "description": annotation_data.get("description", ""),
            "imageFiles": root_images,
            "topLevelChildren": top_level_children,
            "interactions": [],
        },
        "apis": [],
        "discrepancies": [],
    }


# ============================================================
# Component summary builder
# ============================================================


def _build_component_summary(components: list[dict]) -> list[dict]:
    """Build a concise summary of components for agent context."""
    summaries = []
    for i, comp in enumerate(components):
        if comp.get("isLeaf", False):
            continue
        children = comp.get("children", [])
        summaries.append({
            "index": i,
            "id": comp.get("id"),
            "label": comp.get("label", ""),
            "isLeaf": False,
            "imageFile": comp.get("imageFile"),
            "children_count": len(children),
            "children_labels": [c.get("label", "") for c in children],
            "has_interactions": len(comp.get("interactions", [])) > 0,
            "has_description": bool(comp.get("description", "")),
        })
    return summaries


# ============================================================
# Public API
# ============================================================


def prepare_analysis_impl(
    output_dir: str,
    section_prefix: str = "1.1",
) -> dict:
    """One-shot preparation: discover → parse → scaffold → return docs.

    Handles all workspace states internally and returns everything
    the agent needs to begin vision + codebase analysis.
    """
    path = Path(output_dir).resolve()

    if not path.exists() or not path.is_dir():
        return {
            "status": "needs_annotation",
            "output_dir": str(path),
            "message": (
                "Output directory does not exist. "
                "Launch the annotator to create annotations."
            ),
        }

    # Find the screen export directory
    screen_dir = _find_screen_dir(path)
    if screen_dir is None:
        return {
            "status": "needs_annotation",
            "output_dir": str(path),
            "message": (
                "No annotation exports found. "
                "Launch the annotator to create annotations."
            ),
        }

    # Load annotation JSON
    annotation_json = screen_dir / f"{screen_dir.name}.json"
    try:
        annotation_data = json.loads(
            annotation_json.read_text(encoding="utf-8")
        )
    except (json.JSONDecodeError, OSError) as e:
        return {
            "status": "error",
            "message": f"Failed to read annotation JSON: {e}",
        }

    # Check for existing analysis.json
    analysis_path = screen_dir / "analysis.json"
    has_docx = any(f.suffix == ".docx" for f in screen_dir.iterdir())

    if analysis_path.exists():
        # Load existing analysis
        try:
            analysis = json.loads(
                analysis_path.read_text(encoding="utf-8")
            )
        except (json.JSONDecodeError, OSError) as e:
            return {
                "status": "error",
                "message": f"Failed to read analysis.json: {e}",
            }

        status = "complete" if has_docx else "ready"
    else:
        # Scaffold a new analysis.json
        analysis = _scaffold(annotation_data, screen_dir, section_prefix)
        analysis_path.write_text(
            json.dumps(analysis, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        status = "ready"

    # Collect all image files for the agent
    image_files = sorted(
        f.name for f in screen_dir.iterdir()
        if f.is_file() and _ANNOTATED_IMG_RE.match(f.name)
    )

    # Build fields-to-fill list
    to_fill = []
    components = analysis.get("components", [])
    for i, comp in enumerate(components):
        if comp.get("isLeaf", False):
            continue
        if not comp.get("description"):
            to_fill.append(f"components[{i}].description")
        for j, child in enumerate(comp.get("children", [])):
            if not child.get("controlType"):
                to_fill.append(f"components[{i}].children[{j}].controlType")
            if not child.get("description"):
                to_fill.append(f"components[{i}].children[{j}].description")
        if not comp.get("interactions"):
            to_fill.append(f"components[{i}].interactions")
    if not analysis.get("apis"):
        to_fill.append("apis")
    if not analysis.get("screen", {}).get("interactions"):
        to_fill.append("screen.interactions")

    return {
        "status": status,
        "analysis_path": str(analysis_path),
        "screen_name": analysis.get("screen", {}).get("name", ""),
        "components": _build_component_summary(components),
        "image_files": image_files,
        "to_fill": to_fill,
        "schema": ANALYSIS_SCHEMA_TEXT,
        "control_types": CONTROL_TYPES_TEXT,
    }
