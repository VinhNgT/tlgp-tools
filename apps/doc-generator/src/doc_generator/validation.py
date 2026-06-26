"""Validation logic for analysis data.

Performs structural and semantic checks on a parsed AnalysisData object:
image existence, content completeness warnings, discrepancy reporting.
"""

from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field

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
        1 for comp in non_leaf for child in comp.children if not child.controlType
    )
    if empty_controls:
        result.warnings.append(
            f"{empty_controls} child element(s) have empty controlType"
        )

    if data.screen.description and len(data.screen.description) < 10:
        result.warnings.append(f"Screen description is suspiciously short (< 10 chars): '{data.screen.description}'")

    all_comp_labels = {c.label for c in data.components}
    all_child_labels = {c.label for c in data.screen.topLevelChildren}

    for comp in data.components:
        all_child_labels.update(c.label for c in comp.children)
        if comp.description and len(comp.description) < 10:
            result.warnings.append(f"Component '{comp.label}' (id={comp.id}) description is suspiciously short (< 10 chars)")
        if not comp.label.strip():
            result.warnings.append(f"Component (id={comp.id}) has an empty label")
        for child in comp.children:
            if not child.label.strip():
                result.warnings.append(f"Child element {child.stt} in Component '{comp.label}' has an empty label")
            if child.controlType == "Component" and child.label not in all_comp_labels:
                result.warnings.append(f"Child element {child.stt} in Component '{comp.label}' has controlType 'Component' but references non-existent component '{child.label}'")

    for comp in data.components:
        if comp.label not in all_child_labels:
            result.warnings.append(f"Component '{comp.label}' (id={comp.id}) is defined but never referenced as a child")

    for comp in non_leaf:
        if not comp.interactions:
            result.warnings.append(f"Component '{comp.label}' (id={comp.id}) is non-leaf but has zero interactions")
        for ix in comp.interactions:
            if not ix.action.strip() or not ix.reaction.strip():
                result.warnings.append(f"Component '{comp.label}' (id={comp.id}) has an interaction with empty action/reaction")

    for child in data.screen.topLevelChildren:
        if not child.label.strip():
            result.warnings.append(f"Child element {child.stt} in Screen '{data.screen.name}' has an empty label")
        if child.controlType == "Component" and child.label not in all_comp_labels:
            result.warnings.append(f"Child element {child.stt} in Screen '{data.screen.name}' has controlType 'Component' but references non-existent component '{child.label}'")

    for ix in data.screen.interactions:
        if not ix.action.strip() or not ix.reaction.strip():
            result.warnings.append(f"Screen '{data.screen.name}' has an interaction with empty action/reaction")

    def check_stt_sequence(children, owner_name):
        seen = set()
        stts = []
        for child in children:
            if child.stt in seen:
                result.warnings.append(f"Duplicate stt {child.stt} in {owner_name}")
            else:
                seen.add(child.stt)
                stts.append(child.stt)

        if stts:
            stts.sort()
            if stts[0] != 1:
                result.warnings.append(f"STT numbering in {owner_name} starts at {stts[0]}, expected 1")
            expected = list(range(1, stts[-1] + 1))
            missing = sorted(set(expected) - set(stts))
            if missing:
                missing_str = ", ".join(str(m) for m in missing)
                result.warnings.append(
                    f"STT numbering in {owner_name} is non-contiguous: missing {missing_str}"
                )

    check_stt_sequence(data.screen.topLevelChildren, f"Screen '{data.screen.name}'")
    for comp in data.components:
        check_stt_sequence(comp.children, f"Component '{comp.label}' (id={comp.id})")

    if not data.all_apis:
        result.warnings.append("No APIs defined")
    else:
        # Check API duplicate numbers
        api_numbers_list = [api.number for api in data.all_apis]
        duplicates = {n for n in api_numbers_list if api_numbers_list.count(n) > 1}
        if duplicates:
            result.errors.append(f"Duplicate API numbers found: {', '.join(map(str, duplicates))}")

        # Check API numbering contiguity
        api_numbers = sorted(set(api_numbers_list))
        if api_numbers:
            if api_numbers[0] != 1:
                result.warnings.append(f"API numbering starts at {api_numbers[0]}, expected 1")
            expected = list(range(1, api_numbers[-1] + 1))
            missing = sorted(set(expected) - set(api_numbers))
            if missing:
                missing_str = ", ".join(str(m) for m in missing)
                result.warnings.append(
                    f"API numbering is non-contiguous: missing number(s) {missing_str}. "
                    f"Expected sequential 1..{api_numbers[-1]}."
                )

        # Check for undocumented request bodies and missing DTOs
        for api in data.all_apis:
            def check_dto_reference(type_str: str, source: str):
                if not type_str: return
                if "Dto" in type_str or "DTO" in type_str:
                    has_sub_dto = any(dto.name in type_str for dto in api.subDtos)
                    if not has_sub_dto:
                        result.warnings.append(f"API {api.number} '{api.title}' references custom type '{type_str}' in {source} but it is not defined in subDtos")

            check_dto_reference(api.requestBodyType, "requestBodyType")
            check_dto_reference(api.responseType, "responseType")

            all_params = api.requestParams + api.responseFields
            for dto in api.subDtos:
                all_params.extend(dto.fields)

            for param in all_params:
                if not param.name.strip() or not param.meaning.strip():
                    result.warnings.append(f"API {api.number} '{api.title}' has an ApiParam with empty name or meaning")
                check_dto_reference(param.dataType, f"parameter '{param.name}'")

            if api.requestBodyType and not api.requestParams:
                # Check if there is a subDto documenting this body type
                has_sub_dto = any(dto.name == api.requestBodyType for dto in api.subDtos)
                if not has_sub_dto:
                    result.warnings.append(
                        f"API {api.number} '{api.title}' declares requestBodyType '{api.requestBodyType}' "
                        f"but has no request parameters or subDtos documenting its fields."
                    )

            if api.responseType and not api.responseFields:
                # Check if there is a subDto documenting this response type
                has_sub_dto = any(dto.name == api.responseType for dto in api.subDtos)
                if not has_sub_dto:
                    result.warnings.append(
                        f"API {api.number} '{api.title}' declares responseType '{api.responseType}' "
                        f"but has no response fields or subDtos documenting its fields."
                    )

            if api.subDtos:
                referenced_types = {api.requestBodyType, api.responseType}
                for param in api.requestParams:
                    referenced_types.add(param.dataType)
                for param in api.responseFields:
                    referenced_types.add(param.dataType)
                for dto in api.subDtos:
                    for param in dto.fields:
                        referenced_types.add(param.dataType)

                for dto in api.subDtos:
                    if not any(dto.name in str(t) for t in referenced_types if t):
                        result.warnings.append(
                            f"API {api.number} '{api.title}' declares SubDto '{dto.name}', "
                            f"but it is never referenced by any request, response, or other SubDto."
                        )

    # --- Unit limit checks ---
    cfg = data.unitLimit

    def _check_unit_limit(annotations: int, apis: int, owner: str) -> None:
        units = annotations * cfg.annotationCost + apis * cfg.apiCost
        if units > cfg.maxUnits:
            result.errors.append(
                f"{owner} exceeds the unit limit: {units}/{cfg.maxUnits} units "
                f"({annotations} annotations × {cfg.annotationCost} + "
                f"{apis} APIs × {cfg.apiCost} = {units})"
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
