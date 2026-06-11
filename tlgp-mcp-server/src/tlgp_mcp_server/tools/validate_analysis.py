"""Tool: validate_analysis — check analysis.json against the generator schema."""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import ValidationError

from tlgp_doc_generator.models import AnalysisData


def validate_analysis_impl(json_path: str) -> dict:
    """Validate an analysis.json file against the doc generator schema.

    Checks:
    1. JSON syntax
    2. Pydantic schema conformance (AnalysisData model)
    3. Image file existence for all referenced images
    4. Non-empty required content fields
    """
    path = Path(json_path).resolve()

    if not path.exists():
        return {
            "valid": False,
            "errors": [f"File not found: {path}"],
            "warnings": [],
            "summary": {},
        }

    # Parse JSON
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        return {
            "valid": False,
            "errors": [f"Invalid JSON syntax: {e}"],
            "warnings": [],
            "summary": {},
        }

    # Validate against Pydantic schema
    try:
        analysis = AnalysisData.model_validate(raw)
    except ValidationError as e:
        errors = []
        for err in e.errors():
            loc = " → ".join(str(l) for l in err["loc"])
            errors.append(f"{loc}: {err['msg']}")
        return {
            "valid": False,
            "errors": errors,
            "warnings": [],
            "summary": {},
        }

    # Cross-check images
    errors = []
    warnings = []

    # Check component images
    non_leaf = [c for c in analysis.components if not c.isLeaf]
    for comp in non_leaf:
        if comp.imageFile:
            img = analysis.resolve_image(comp.imageFile)
            if not img.exists():
                errors.append(
                    f"Component '{comp.label}' (id={comp.id}): "
                    f"image not found: {img}"
                )
        else:
            warnings.append(
                f"Component '{comp.label}' (id={comp.id}): "
                f"no imageFile specified (non-leaf should have one)"
            )

    # Check screen images
    for img_file in analysis.screen.imageFiles:
        img = analysis.resolve_image(img_file)
        if not img.exists():
            errors.append(f"Screen image not found: {img}")

    if not analysis.screen.imageFiles:
        warnings.append("No screen-level images specified")

    # Content completeness warnings
    empty_descriptions = [
        c.label for c in non_leaf if not c.description
    ]
    if empty_descriptions:
        warnings.append(
            f"{len(empty_descriptions)} component(s) have empty descriptions: "
            + ", ".join(empty_descriptions[:5])
        )

    empty_controls = 0
    for comp in non_leaf:
        for child in comp.children:
            if not child.controlType:
                empty_controls += 1
    if empty_controls:
        warnings.append(f"{empty_controls} child element(s) have empty controlType")

    if not analysis.apis:
        warnings.append("No APIs defined")

    # Build summary
    summary = {
        "screen_name": analysis.screen.name,
        "section_prefix": analysis.sectionPrefix,
        "total_components": len(analysis.components),
        "non_leaf_components": len(non_leaf),
        "leaf_components": len(analysis.components) - len(non_leaf),
        "total_children": sum(len(c.children) for c in non_leaf),
        "total_interactions": sum(len(c.interactions) for c in non_leaf),
        "screen_interactions": len(analysis.screen.interactions),
        "api_count": len(analysis.apis),
        "image_count": (
            len(analysis.screen.imageFiles)
            + sum(1 for c in non_leaf if c.imageFile)
        ),
    }

    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
        "summary": summary,
    }
