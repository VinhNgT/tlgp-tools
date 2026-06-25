"""Validation logic for analysis data.

Performs structural and semantic checks on a parsed AnalysisData object:
image existence, content completeness warnings, discrepancy reporting.
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from doc_generator.models import AnalysisData


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


class DocGenResult(BaseModel):
    """The complete structured JSON output emitted by the doc-gen CLI."""

    valid: bool = True
    errors: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)

    components: int = 0
    non_leaf: int = 0
    ui_elements: int = 0
    interactions: int = 0
    apis: int = 0
    images: int = 0
    discrepancies: int = 0

    output_path: str | None = None
    tables: int | None = None

    @classmethod
    def from_validation(
        cls,
        vr: ValidationResult,
        output_path: str | None = None,
        tables: int | None = None,
    ) -> DocGenResult:
        """Construct from a ValidationResult and generation artifacts."""
        return cls(
            valid=vr.valid,
            errors=vr.errors,
            warnings=vr.warnings,
            components=vr.components,
            non_leaf=vr.non_leaf,
            ui_elements=vr.ui_elements,
            interactions=vr.interactions,
            apis=vr.apis,
            images=vr.images,
            discrepancies=vr.discrepancies,
            output_path=output_path,
            tables=tables,
        )


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
        ui_elements=sum(len(c.children) for c in non_leaf),
        interactions=sum(len(c.interactions) for c in non_leaf),
        apis=len(data.all_apis),
        discrepancies=len(data.discrepancies),
    )

    # --- Image existence checks ---
    for comp in non_leaf:
        if comp.imageFile:
            img = data.resolve_image(comp.imageFile)
            if not img.exists():
                result.errors.append(
                    f"Component '{comp.label}' (id={comp.id}): "
                    f"image not found: {img}"
                )
        else:
            result.warnings.append(
                f"Component '{comp.label}' (id={comp.id}): "
                f"no imageFile specified (non-leaf should have one)"
            )

    for img_file in data.screen.imageFiles:
        img = data.resolve_image(img_file)
        if not img.exists():
            result.errors.append(f"Screen image not found: {img}")

    if not data.screen.imageFiles:
        result.warnings.append("No screen-level images specified")

    # --- Image count ---
    result.images = len(data.screen.imageFiles) + sum(
        1 for c in non_leaf if c.imageFile
    )

    # --- Content completeness warnings ---
    empty_descriptions = [c.label for c in non_leaf if not c.description]
    if empty_descriptions:
        result.warnings.append(
            f"{len(empty_descriptions)} component(s) have empty descriptions: "
            + ", ".join(empty_descriptions[:5])
        )

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
            f"⚠️ Discrepancy at '{disc.location}': "
            f"Image shows: {disc.imageObservation} | "
            f"Code shows: {disc.codeObservation}"
            + (f" | Resolution: {disc.resolution}" if disc.resolution else "")
        )

    # --- Final validity ---
    if result.errors:
        result.valid = False

    return result
