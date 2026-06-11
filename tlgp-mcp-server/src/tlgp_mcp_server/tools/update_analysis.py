"""Tool: update_analysis — patch-style JSON updates with validation.

Accepts a list of {path, value} updates and applies them to the
analysis.json file. Validates the result against the Pydantic schema
before writing back.
"""

from __future__ import annotations

import json
import re
from pathlib import Path

from pydantic import ValidationError

from tlgp_doc_generator.models import AnalysisData


# ============================================================
# JSON path resolution
# ============================================================

_PATH_SEGMENT_RE = re.compile(r"^(\w+)(?:\[(\d+)\])?$")


def _resolve_path(data: dict, path: str) -> tuple[dict | list, str | int]:
    """Walk a dotted JSON path and return (parent, key) for the final segment.

    Supports paths like:
      - "components[0].description"
      - "components[0].children[2].controlType"
      - "apis"
      - "screen.interactions"

    Returns the parent container and the key (str or int) needed to
    set the value: parent[key] = value
    """
    segments = path.split(".")
    current = data

    for segment in segments[:-1]:
        match = _PATH_SEGMENT_RE.match(segment)
        if not match:
            raise ValueError(f"Invalid path segment: '{segment}' in '{path}'")

        field, index = match.group(1), match.group(2)
        current = current[field]
        if index is not None:
            current = current[int(index)]

    # Resolve the final segment
    last = segments[-1]
    match = _PATH_SEGMENT_RE.match(last)
    if not match:
        raise ValueError(f"Invalid path segment: '{last}' in '{path}'")

    field, index = match.group(1), match.group(2)

    if index is not None:
        return current[field], int(index)
    return current, field


def _apply_updates(data: dict, updates: list[dict]) -> list[str]:
    """Apply a list of updates to the data dict. Returns list of applied paths."""
    applied = []
    for update in updates:
        path = update["path"]
        value = update["value"]
        parent, key = _resolve_path(data, path)
        parent[key] = value
        applied.append(path)
    return applied


# ============================================================
# Summary builder
# ============================================================


def _build_update_summary(analysis: dict) -> dict:
    """Build a concise summary of the current analysis state."""
    components = analysis.get("components", [])
    non_leaf = [c for c in components if not c.get("isLeaf", False)]

    filled_descriptions = sum(1 for c in non_leaf if c.get("description"))
    filled_controls = sum(
        1 for c in non_leaf
        for child in c.get("children", [])
        if child.get("controlType")
    )
    total_controls = sum(
        len(c.get("children", [])) for c in non_leaf
    )

    return {
        "components_with_description": f"{filled_descriptions}/{len(non_leaf)}",
        "children_with_controlType": f"{filled_controls}/{total_controls}",
        "interactions": sum(len(c.get("interactions", [])) for c in non_leaf),
        "screen_interactions": len(
            analysis.get("screen", {}).get("interactions", [])
        ),
        "apis": len(analysis.get("apis", [])),
        "discrepancies": len(analysis.get("discrepancies", [])),
    }


# ============================================================
# Public API
# ============================================================


def update_analysis_impl(
    json_path: str,
    updates: list[dict],
) -> dict:
    """Apply targeted updates to analysis.json.

    Each update is a dict with:
    - path: JSON path (e.g., "components[0].description")
    - value: the new value to set

    Validates the result against the AnalysisData schema before saving.
    """
    path = Path(json_path).resolve()

    if not path.exists():
        return {"error": f"File not found: {path}"}

    # Load current data
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        return {"error": f"Invalid JSON: {e}"}

    # Validate updates format
    for i, update in enumerate(updates):
        if "path" not in update or "value" not in update:
            return {
                "error": (
                    f"Update [{i}] must have 'path' and 'value' keys. "
                    f"Got: {list(update.keys())}"
                ),
            }

    # Apply updates
    try:
        applied = _apply_updates(data, updates)
    except (KeyError, IndexError, TypeError) as e:
        return {"error": f"Failed to apply updates: {e}"}
    except ValueError as e:
        return {"error": str(e)}

    # Validate against schema
    try:
        AnalysisData.model_validate(data)
    except ValidationError as e:
        errors = []
        for err in e.errors():
            loc = " → ".join(str(loc) for loc in err["loc"])
            errors.append(f"{loc}: {err['msg']}")
        return {
            "error": "Validation failed after applying updates",
            "validation_errors": errors,
            "applied_paths": applied,
        }

    # Write back
    path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    return {
        "success": True,
        "applied_paths": applied,
        "updates_count": len(applied),
        "summary": _build_update_summary(data),
    }
