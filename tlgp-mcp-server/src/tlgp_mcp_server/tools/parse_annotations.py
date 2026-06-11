"""Tool: parse_annotations — read an annotation export JSON."""

from __future__ import annotations

import json
from pathlib import Path


def parse_annotations_impl(json_path: str) -> dict:
    """Read and validate an annotation tool export JSON.

    Returns the full structured data including screen metadata,
    image dimensions, component hierarchy, and cut lines.
    """
    path = Path(json_path).resolve()

    if not path.exists():
        return {"error": f"File not found: {path}"}

    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        return {"error": f"Invalid JSON: {e}"}

    # Validate required fields
    required = ["screen_name", "components"]
    missing = [f for f in required if f not in data]
    if missing:
        return {"error": f"Missing required fields: {', '.join(missing)}"}

    # Build structured response
    def _serialize_component(comp: dict, depth: int = 0) -> dict:
        children = comp.get("children", [])
        return {
            "id": comp.get("id"),
            "label": comp.get("label", ""),
            "bounds": comp.get("bounds", {}),
            "has_children": len(children) > 0,
            "children_count": len(children),
            "depth": depth,
            "children": [
                _serialize_component(c, depth + 1) for c in children
            ],
        }

    components = [
        _serialize_component(c) for c in data.get("components", [])
    ]

    return {
        "json_path": str(path),
        "screen_name": data.get("screen_name", ""),
        "description": data.get("description", ""),
        "original_image": data.get("original_image", ""),
        "image_width": data.get("image_width"),
        "image_height": data.get("image_height"),
        "cut_lines": data.get("cut_lines", []),
        "component_count": len(components),
        "components": components,
    }
