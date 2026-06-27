"""Validation logic for analysis data.

Performs structural and semantic checks on a parsed AnalysisData object:
image existence, content completeness warnings, discrepancy reporting.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field
from tlgp_contracts import (
    DEFAULT_UNIT_COST_ANNOTATION,
    DEFAULT_UNIT_COST_API,
    DEFAULT_UNIT_LIMIT,
)

from .models import AnalysisData, Api


class ValidationResult(BaseModel):
    """Structured outcome of analysis data validation."""

    valid: bool = True
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    # Summary statistics (populated regardless of validity)
    components: int = 0
    non_leaf: int = 0
    ui_elements: int = 0
    interactions: int = 0
    apis: int = 0
    images: int = 0
    discrepancies: int = 0


def validate_analysis(data: AnalysisData) -> ValidationResult:
    """Run all validation checks against parsed analysis data.

    This is the single source of truth for validation logic, consumed by
    both the CLI (``--validate-only`` / ``--json``) and any external caller
    that needs to pre-check analysis data before document generation.
    """
    non_leaf = [c for c in data.components.values() if not c.isLeaf]

    result = ValidationResult(
        components=len(data.components),
        non_leaf=len(non_leaf),
        ui_elements=sum(len(c.children) for c in non_leaf)
        + len(data.screen.topLevelChildren),
        interactions=sum(len(c.interactions) for c in non_leaf)
        + len(data.screen.interactions),
        apis=len(data.all_apis),
        discrepancies=len(data.discrepancies),
    )

    base_dir = Path(data.imageDir).resolve()

    # --- Image and structure checks ---
    for comp in non_leaf:
        if comp.imageFile:
            img = data.resolve_image(comp.imageFile)
            if not img.resolve().is_relative_to(base_dir):
                result.errors.append(
                    f"Component '{comp.label}' (id={comp.id}): image path escapes imageDir: {comp.imageFile}"
                )
            elif not img.exists():
                result.errors.append(
                    f"Component '{comp.label}' (id={comp.id}): image not found: {img}"
                )
        else:
            result.errors.append(
                f"Component '{comp.label}' (id={comp.id}): "
                f"no imageFile specified (non-leaf must have one)"
            )

        if not comp.children:
            result.errors.append(
                f"Component '{comp.label}' (id={comp.id}): "
                f"no children specified (non-leaf must have at least one child)"
            )

        if not comp.description:
            result.errors.append(
                f"Component '{comp.label}' (id={comp.id}): empty description"
            )

    if not data.screen.description:
        result.errors.append("Screen description is empty")

    if not data.screen.topLevelChildren:
        result.errors.append("Screen has no top-level children")

    for img_file in data.screen.imageFiles:
        img = data.resolve_image(img_file)
        if not img.resolve().is_relative_to(base_dir):
            result.errors.append(f"Screen image path escapes imageDir: {img_file}")
        elif not img.exists():
            result.errors.append(f"Screen image not found: {img}")

    if not data.screen.imageFiles:
        result.errors.append("No screen-level images specified")

    # --- Image count ---
    result.images = len(data.screen.imageFiles) + sum(
        1 for c in non_leaf if c.imageFile
    )

    # --- Content completeness warnings ---

    empty_controls = sum(
        1
        for comp in non_leaf
        for child in comp.children
        if getattr(child, "type", "") == "primitive" and not child.controlType
    )
    if empty_controls:
        result.warnings.append(
            f"{empty_controls} child element(s) have empty controlType"
        )

    if data.screen.description and len(data.screen.description) < 10:
        result.warnings.append(
            f"Screen description is suspiciously short (< 10 chars): '{data.screen.description}'"
        )

    all_child_labels = {c.label for c in data.screen.topLevelChildren}

    for comp in data.components.values():
        all_child_labels.update(c.label for c in comp.children)
        if comp.description and len(comp.description) < 10:
            result.warnings.append(
                f"Component '{comp.label}' (id={comp.id}) description is suspiciously short (< 10 chars)"
            )
        if not comp.label.strip():
            result.warnings.append(f"Component (id={comp.id}) has an empty label")
        for i, child in enumerate(comp.children):
            if not child.label.strip():
                result.warnings.append(
                    f"Child element {i + 1} in Component '{comp.label}' has an empty label"
                )

    for comp in data.components.values():
        if comp.label not in all_child_labels:
            result.warnings.append(
                f"Component '{comp.label}' (id={comp.id}) is defined but never referenced as a child"
            )

    for child in data.screen.topLevelChildren:
        if not child.label.strip():
            result.warnings.append(
                f"Child element in Screen '{data.screen.name}' has an empty label"
            )

    # Check for structural errors in API parameters and unused schemas
    for api in data.all_apis:
        all_params = api.requestParams + api.responseFields
        for schema in api.schemas.values():
            all_params.extend(schema.fields)

        for param in all_params:
            if not param.name.strip() or not param.meaning.strip():
                result.warnings.append(
                    f"API '{api.title}' has an ApiParam with empty name or meaning"
                )

        if api.schemas:
            referenced_types = {api.requestBodyType, api.responseType}
            for param in api.requestParams:
                referenced_types.add(param.dataType)
            for param in api.responseFields:
                referenced_types.add(param.dataType)
            for schema in api.schemas.values():
                for param in schema.fields:
                    referenced_types.add(param.dataType)

            for schema in api.schemas.values():
                if not any(schema.name in str(t) for t in referenced_types if t):
                    result.warnings.append(
                        f"API '{api.title}' declares schema '{schema.name}', "
                        f"but it is never referenced by any request, response, or other schema."
                    )

    # --- Unit limit checks ---
    def _check_unit_limit(annotations: int, apis: int, owner: str) -> None:
        units = (
            annotations * DEFAULT_UNIT_COST_ANNOTATION + apis * DEFAULT_UNIT_COST_API
        )
        if units > DEFAULT_UNIT_LIMIT:
            result.errors.append(
                f"{owner} exceeds the unit limit: {units}/{DEFAULT_UNIT_LIMIT} units "
                f"({annotations} annotations × {DEFAULT_UNIT_COST_ANNOTATION} + "
                f"{apis} APIs × {DEFAULT_UNIT_COST_API} = {units})"
            )

    _check_unit_limit(
        len(data.screen.topLevelChildren),
        len(data.screen.apis),
        f"Screen '{data.screen.name}'",
    )

    for comp in non_leaf:
        _check_unit_limit(
            len(comp.children),
            len(comp.apis),
            f"Component '{comp.label}' (id={comp.id})",
        )

    # --- Discrepancy warnings ---
    for disc in data.discrepancies:
        result.warnings.append(
            f"Discrepancy at '{disc.location}': "
            f"Image shows: {disc.imageObservation} | "
            f"Code shows: {disc.codeObservation}"
            + (f" | Expected: {disc.expectedBehavior}" if disc.expectedBehavior else "")
        )

    # --- Final validity ---
    if result.errors:
        result.valid = False

    return result
