"""Tool: generate_docx — build a .docx specification document."""

from __future__ import annotations

import json
from pathlib import Path

from pydantic import ValidationError

from tlgp_doc_generator.doc_builder import build_document
from tlgp_doc_generator.models import AnalysisData


def generate_docx_impl(
    json_path: str,
    output_path: str | None = None,
) -> dict:
    """Generate a .docx from analysis.json.

    Validates the schema, builds the document with all formatting applied
    automatically from spec_format.toml, and saves to disk.
    """
    path = Path(json_path).resolve()

    if not path.exists():
        return {"error": f"File not found: {path}"}

    # Load and validate
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        return {"error": f"Invalid JSON: {e}"}

    try:
        analysis = AnalysisData.model_validate(raw)
    except ValidationError as e:
        errors = []
        for err in e.errors():
            loc = " → ".join(str(l) for l in err["loc"])
            errors.append(f"{loc}: {err['msg']}")
        return {"error": "Schema validation failed", "details": errors}

    # Build document
    doc = build_document(analysis)

    # Determine output path
    if output_path:
        out = Path(output_path).resolve()
    else:
        safe_name = analysis.screen.name.replace(" ", "_")
        out = path.parent / f"{safe_name}.docx"

    out.parent.mkdir(parents=True, exist_ok=True)
    doc.save(str(out))

    # Count tables and images for the summary
    non_leaf = [c for c in analysis.components if not c.isLeaf]
    table_count = 0
    table_count += len(non_leaf)  # info tables
    table_count += sum(1 for c in non_leaf if c.children)  # UI tables
    table_count += sum(1 for c in non_leaf if c.interactions)  # interaction tables
    table_count += 1  # screen info table
    if analysis.screen.topLevelChildren:
        table_count += 1
    if analysis.screen.interactions:
        table_count += 1
    for api in analysis.apis:
        if api.requestParams:
            table_count += 1
        if api.responseFields:
            table_count += 1
        table_count += sum(1 for s in api.subDtos if s.fields)

    image_count = (
        len(analysis.screen.imageFiles)
        + sum(1 for c in non_leaf if c.imageFile)
    )

    return {
        "output_path": str(out),
        "tables": table_count,
        "images": image_count,
        "message": f"Generated {out.name} successfully.",
    }
