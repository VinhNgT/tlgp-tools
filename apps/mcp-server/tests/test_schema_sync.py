"""Structural sync test: validates schema_reference.md documents all Pydantic model fields.

The doc-generator's models.py is the source of truth for the analysis.json schema.
The MCP server's schema_reference.md is a hand-written agent-facing reference document.
This test ensures they stay in sync — if a field is added to a model but not documented,
the test fails with a clear error message.
"""

from __future__ import annotations

import inspect

from doc_generator import models as docgen_models
from mcp_server.prompts import get_schema_reference

# Models to check and their expected section headers in the markdown
_MODEL_SECTION_MAP: dict[type, str] = {
    docgen_models.AnalysisData: "Root Fields",
    docgen_models.AnalysisComponent: "Component Fields",
    docgen_models.ChildElement: "ChildElement Fields",
    docgen_models.Interaction: "Interaction Fields",
    docgen_models.Screen: "Screen Fields",
    docgen_models.Api: "Api Fields",
    docgen_models.SubDto: "SubDto Fields",
    docgen_models.ApiParam: "ApiParam Fields",
    docgen_models.Discrepancy: "Discrepancy Fields",
}

# Fields intentionally omitted from the schema reference (e.g. internal/computed)
_EXCLUDED_FIELDS: set[str] = set()


def test_all_model_classes_have_schema_sections():
    """Every Pydantic model class must have a corresponding section in schema_reference.md."""
    schema_md = get_schema_reference()

    model_classes = [
        cls
        for _, cls in inspect.getmembers(docgen_models, inspect.isclass)
        if issubclass(cls, docgen_models.AnalysisData.__class__.__bases__[0])
        and cls.__module__ == docgen_models.__name__
    ]

    for cls in model_classes:
        section = _MODEL_SECTION_MAP.get(cls)
        assert section is not None, (
            f"Model class {cls.__name__} has no entry in _MODEL_SECTION_MAP. "
            f"Add it and create a corresponding section in schema_reference.md."
        )
        assert section in schema_md, (
            f"Section '{section}' for model {cls.__name__} not found in schema_reference.md"
        )


def test_all_model_fields_documented():
    """Every field in every model must appear as a backtick-quoted entry in schema_reference.md."""
    schema_md = get_schema_reference()

    missing = []
    for cls, section in _MODEL_SECTION_MAP.items():
        for field_name in cls.model_fields:
            if field_name in _EXCLUDED_FIELDS:
                continue
            if f"`{field_name}`" not in schema_md:
                missing.append(f"{cls.__name__}.{field_name} (section: {section})")

    assert not missing, (
        "The following model fields are not documented in schema_reference.md:\n"
        + "\n".join(f"  - {m}" for m in missing)
    )
