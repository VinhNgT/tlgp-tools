"""Tool: finalize — validate + generate .docx in one step.

Combines the logic of validate_analysis and generate_docx into a single
tool call. If validation passes, generates the document automatically.
"""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import ValidationError

from tlgp_doc_generator.doc_builder import build_document
from tlgp_doc_generator.models import AnalysisData


def finalize_impl(
    json_path: str,
    output_path: str | None = None,
) -> dict:
    """Validate analysis.json and generate the .docx if valid.

    If validation fails, returns errors without generating.
    If validation passes, generates the document and returns the result.
    """
    path = Path(json_path).resolve()

    if not path.exists():
        return {
            "valid": False,
            "errors": [f"File not found: {path}"],
            "warnings": [],
        }

    # Parse JSON
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        return {
            "valid": False,
            "errors": [f"Invalid JSON syntax: {e}"],
            "warnings": [],
        }

    # Validate against Pydantic schema
    try:
        analysis = AnalysisData.model_validate(raw)
    except ValidationError as e:
        errors = []
        for err in e.errors():
            loc = " → ".join(str(loc) for loc in err["loc"])
            errors.append(f"{loc}: {err['msg']}")
        return {
            "valid": False,
            "errors": errors,
            "warnings": [],
        }

    # Cross-check images
    errors = []
    warnings = []

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

    for img_file in analysis.screen.imageFiles:
        img = analysis.resolve_image(img_file)
        if not img.exists():
            errors.append(f"Screen image not found: {img}")

    if not analysis.screen.imageFiles:
        warnings.append("No screen-level images specified")

    # Content completeness warnings
    empty_descriptions = [c.label for c in non_leaf if not c.description]
    if empty_descriptions:
        warnings.append(
            f"{len(empty_descriptions)} component(s) have empty descriptions: "
            + ", ".join(empty_descriptions[:5])
        )

    empty_controls = sum(
        1 for comp in non_leaf
        for child in comp.children
        if not child.controlType
    )
    if empty_controls:
        warnings.append(
            f"{empty_controls} child element(s) have empty controlType"
        )

    if not analysis.apis:
        warnings.append("No APIs defined")

    # Discrepancy warnings
    for disc in analysis.discrepancies:
        warnings.append(
            f"⚠️ Discrepancy at '{disc.location}': "
            f"Image shows: {disc.imageObservation} | "
            f"Code shows: {disc.codeObservation}"
            + (f" | Resolution: {disc.resolution}" if disc.resolution else "")
        )

    # If errors, stop here
    if errors:
        return {
            "valid": False,
            "errors": errors,
            "warnings": warnings,
        }

    # Generate .docx
    doc = build_document(analysis)

    if output_path:
        out = Path(output_path).resolve()
    else:
        safe_name = "".join(
            c for c in analysis.screen.name
            if c.isalnum() or c in (" ", "_", "-")
        ).strip().replace(" ", "_")
        out = path.parent / f"{safe_name}.docx"

    out.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(out))

    # Count tables and images
    table_count = len(doc.tables)
    image_count = (
        len(analysis.screen.imageFiles)
        + sum(1 for c in non_leaf if c.imageFile)
    )

    return {
        "valid": True,
        "output_path": str(out),
        "tables": table_count,
        "images": image_count,
        "warnings": warnings,
        "message": (
            f"Generated {out.name} successfully "
            f"({table_count} tables, {image_count} images)."
        ),
    }
