"""Helper module for programmatically updating node details in spec.json."""

from __future__ import annotations

import json
from pathlib import Path

from tlgp_contracts import ScreenSpec


def update_node_in_spec_file(
    spec_path: str,
    node_id: str,
    label: str | None = None,
    description: str | None = None,
    control_type: str | None = None,
    required: bool | None = None,
    editable: bool | None = None,
    max_length: int | None = None,
    interactions: list[dict] | None = None,
    apis: list[dict] | None = None,
) -> None:
    """Load, update, validate against Pydantic schemas, and write spec.json."""
    path = Path(spec_path).resolve()
    if not path.exists():
        raise FileNotFoundError(f"Spec file not found at {spec_path}")

    with open(path, encoding="utf-8") as f:
        spec_data = json.load(f)

    nodes = spec_data.get("nodes", [])
    node = None
    for n in nodes:
        if n.get("id") == node_id:
            node = n
            break

    if node is None:
        raise ValueError(f"Node with id {node_id} not found in spec file")

    # Update semantic fields if provided
    if label is not None:
        node["label"] = label
    if description is not None:
        node["description"] = description
    if control_type is not None:
        node["controlType"] = control_type

    # Optional leaf elements validations/fields
    if required is not None:
        node["required"] = required
    if editable is not None:
        node["editable"] = editable
    if max_length is not None:
        node["maxLength"] = max_length

    # Arrays
    if interactions is not None:
        node["interactions"] = interactions
    if apis is not None:
        node["apis"] = apis

    # Validate structural correctness and types using Pydantic contract
    ScreenSpec.model_validate(spec_data)

    # Save to disk
    with open(path, "w", encoding="utf-8") as f:
        json.dump(spec_data, f, indent=2, ensure_ascii=False)


