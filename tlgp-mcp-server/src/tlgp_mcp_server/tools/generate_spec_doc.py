"""Tool: generate_spec_doc — validate analysis data and generate .docx.

Accepts a complete analysis dict from the agent, validates it against the
AnalysisData Pydantic schema, cross-checks image references, and generates
a formatted .docx specification document via tlgp-doc-generator.
"""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import ValidationError

from tlgp_doc_generator.doc_builder import build_document
from tlgp_doc_generator.models import AnalysisData


def generate_spec_doc_impl(
    analysis: dict | None = None,
    analysis_path: str | None = None,
    output_path: str | None = None,
    validate_only: bool = False,
) -> dict:
    """Validate analysis data and generate the .docx if valid.

    Args:
        analysis: Complete analysis data dict conforming to AnalysisData.
        analysis_path: Optional path to analysis JSON file.
        output_path: Where to save the .docx. Defaults to
            <screen_name>.docx in exportDir.
        validate_only: If True, validate without generating.

    Returns:
        dict with valid, output_path, tables, images, warnings, errors.
    """
    if analysis_path:
        try:
            with open(analysis_path, "r", encoding="utf-8") as f:
                analysis = json.load(f)
        except Exception as e:
            return {
                "valid": False,
                "errors": [f"Failed to read analysis_path: {e}"],
                "warnings": [],
            }

    if not analysis:
        return {
            "valid": False,
            "errors": ["Either 'analysis' or 'analysis_path' must be provided"],
            "warnings": [],
        }

    # Validate against Pydantic schema
    try:
        data = AnalysisData.model_validate(analysis)
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

    non_leaf = [c for c in data.components if not c.isLeaf]
    for comp in non_leaf:
        if comp.imageFile:
            img = data.resolve_image(comp.imageFile)
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

    for img_file in data.screen.imageFiles:
        img = data.resolve_image(img_file)
        if not img.exists():
            errors.append(f"Screen image not found: {img}")

    if not data.screen.imageFiles:
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

    if not data.apis:
        warnings.append("No APIs defined")

    # Discrepancy warnings
    for disc in data.discrepancies:
        warnings.append(
            f"⚠️ Discrepancy at '{disc.location}': "
            f"Image shows: {disc.imageObservation} | "
            f"Code shows: {disc.codeObservation}"
            + (f" | Resolution: {disc.resolution}" if disc.resolution else "")
        )

    # Stop here if errors found
    if errors:
        return {
            "valid": False,
            "errors": errors,
            "warnings": warnings,
        }

    # Validate-only mode: return summary without generating
    if validate_only:
        image_count = (
            len(data.screen.imageFiles)
            + sum(1 for c in non_leaf if c.imageFile)
        )
        return {
            "valid": True,
            "warnings": warnings,
            "components": len(data.components),
            "non_leaf": len(non_leaf),
            "ui_elements": sum(len(c.children) for c in non_leaf),
            "interactions": sum(len(c.interactions) for c in non_leaf),
            "apis": len(data.apis),
            "images": image_count,
        }

    # Generate .docx
    doc = build_document(data)

    if output_path:
        out = Path(output_path).resolve()
    else:
        safe_name = "".join(
            c for c in data.screen.name
            if c.isalnum() or c in (" ", "_", "-")
        ).strip().replace(" ", "_")
        out = Path(data.exportDir) / f"{safe_name}.docx"

    out.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(out))

    # Save analysis.json for record-keeping
    export_dir = Path(data.exportDir)
    analysis_json_path = export_dir / "analysis.json"
    analysis_json_path.write_text(
        json.dumps(analysis, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    # Count tables and images
    table_count = len(doc.tables)
    image_count = (
        len(data.screen.imageFiles)
        + sum(1 for c in non_leaf if c.imageFile)
    )

    return {
        "valid": True,
        "output_path": str(out),
        "tables": table_count,
        "images": image_count,
        "warnings": warnings,
    }
