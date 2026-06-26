"""Validation logic for analysis data.

Performs structural and semantic checks on a parsed AnalysisData object:
image existence, content completeness warnings, discrepancy reporting.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from tlgp_contracts import DocGenResult

from .models import AnalysisData


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
    non_leaf = [c for c in data.components if not c.isLeaf]

    result = ValidationResult(
        components=len(data.components),
        non_leaf=len(non_leaf),
        ui_elements=sum(len(c.children) for c in non_leaf) + len(data.screen.topLevelChildren),
        interactions=sum(len(c.interactions) for c in non_leaf) + len(data.screen.interactions),
        apis=len(data.all_apis),
        discrepancies=len(data.discrepancies),
    )

    # --- Image and structure checks ---
    for comp in non_leaf:
        if comp.imageFile:
            img = data.resolve_image(comp.imageFile)
            if not img.exists():
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
        if not img.exists():
            result.errors.append(f"Screen image not found: {img}")

    if not data.screen.imageFiles:
        result.errors.append("No screen-level images specified")

    # --- Image count ---
    result.images = len(data.screen.imageFiles) + sum(
        1 for c in non_leaf if c.imageFile
    )

    # --- Content completeness warnings ---

    empty_controls = sum(
        1 for comp in non_leaf for child in comp.children if not child.controlType
    )
    if empty_controls:
        result.warnings.append(
            f"{empty_controls} child element(s) have empty controlType"
        )

    if not data.all_apis:
        result.warnings.append("No APIs defined")

    # --- Discrepancy warnings ---
    for disc in data.discrepancies:
        result.warnings.append(
            f"Discrepancy at '{disc.location}': "
            f"Image shows: {disc.imageObservation} | "
            f"Code shows: {disc.codeObservation}"
            + (f" | Resolution: {disc.resolution}" if disc.resolution else "")
        )

    # --- Final validity ---
    if result.errors:
        result.valid = False

    return result
