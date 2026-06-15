"""Services for managing spec doc generation, validation, and elicitation."""

from __future__ import annotations

import json
from pathlib import Path
from typing import TYPE_CHECKING

from doc_generator.doc_builder import build_document
from doc_generator.models import AnalysisData
from pydantic import BaseModel, Field, ValidationError
from tlgp_logger import get_logger

if TYPE_CHECKING:
    from mcp.server.fastmcp import Context

logger = get_logger(__name__)


class ComponentDescription(BaseModel):
    """Schema for eliciting component descriptions from the user."""

    description: str = Field(..., description="A brief 1-sentence UX description of the component")


class SpecGeneratorService:
    """Orchestrates validation, metadata elicitation, and compilation of specification documents."""

    def __init__(self):
        pass

    async def generate(
        self,
        ctx: Context | None = None,
        analysis: dict | None = None,
        analysis_path: str | None = None,
        output_path: str | None = None,
        validate_only: bool = False,
    ) -> dict:
        """Validate, elicit missing descriptions, and generate the final specification document."""
        if ctx:
            await ctx.report_progress(10, 100, "Loading and validating analysis data...")

        if analysis_path:
            try:
                with open(analysis_path, encoding="utf-8") as f:
                    analysis = json.load(f)
            except Exception as e:
                logger.error("Failed to load analysis file from %s: %s", analysis_path, e)
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

        # Handle description elicitation for non-leaf components
        if not validate_only and ctx is not None:
            try:
                data = AnalysisData.model_validate(analysis)
                non_leaf = [c for c in data.components if not c.isLeaf]

                updated = False
                for comp in non_leaf:
                    if not comp.description:
                        await ctx.report_progress(30, 100, f"Eliciting description for '{comp.label}'...")
                        logger.info("Eliciting description for empty component '%s' (ID: %s)", comp.label, comp.id)
                        try:
                            result = await ctx.elicit(
                                message=f"The component '{comp.label}' (id={comp.id}) has an empty description. Please provide a UX description.",
                                schema=ComponentDescription,
                            )
                            if result.action == "accept":
                                comp.description = result.data.description
                                for c_dict in analysis.get("components", []):
                                    if c_dict.get("id") == comp.id:
                                        c_dict["description"] = comp.description
                                        updated = True
                                        break
                        except Exception as e:
                            logger.error("Description elicitation failed for component '%s': %s", comp.label, e)
                            await ctx.log("error", f"Elicitation failed for component '{comp.label}': {e}")

                if updated and analysis_path:
                    try:
                        with open(analysis_path, "w", encoding="utf-8") as f:
                            json.dump(analysis, f, indent=2, ensure_ascii=False)
                    except Exception as e:
                        logger.warning("Failed to save updated analysis data to %s: %s", analysis_path, e)
                        await ctx.log("warning", f"Failed to write updated analysis back to {analysis_path}: {e}")

            except ValidationError:
                # Fall through to let strict validation function capture and report structured errors
                pass

        if ctx:
            await ctx.report_progress(60, 100, "Running document generation...")

        result = self.generate_spec_doc_impl(
            analysis=analysis,
            output_path=output_path,
            validate_only=validate_only,
        )

        if ctx:
            await ctx.report_progress(100, 100, "Spec generation complete.")

        return result

    def generate_spec_doc_impl(
        self,
        analysis: dict,
        output_path: str | None = None,
        validate_only: bool = False,
    ) -> dict:
        """Validate analysis schema structure, verify visual asset references, and write document."""
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

        errors = []
        warnings = []

        non_leaf = [c for c in data.components if not c.isLeaf]
        for comp in non_leaf:
            if comp.imageFile:
                img = data.resolve_image(comp.imageFile)
                if not img.exists():
                    errors.append(
                        f"Component '{comp.label}' (id={comp.id}): image not found: {img}"
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

        # Content warning details
        empty_descriptions = [c.label for c in non_leaf if not c.description]
        if empty_descriptions:
            warnings.append(
                f"{len(empty_descriptions)} component(s) have empty descriptions: "
                + ", ".join(empty_descriptions[:5])
            )

        empty_controls = sum(
            1 for comp in non_leaf for child in comp.children if not child.controlType
        )
        if empty_controls:
            warnings.append(f"{empty_controls} child element(s) have empty controlType")

        if not data.apis:
            warnings.append("No APIs defined")

        for disc in data.discrepancies:
            warnings.append(
                f"⚠️ Discrepancy at '{disc.location}': "
                f"Image shows: {disc.imageObservation} | "
                f"Code shows: {disc.codeObservation}"
                + (f" | Resolution: {disc.resolution}" if disc.resolution else "")
            )

        if errors:
            return {
                "valid": False,
                "errors": errors,
                "warnings": warnings,
            }

        if validate_only:
            image_count = len(data.screen.imageFiles) + sum(
                1 for c in non_leaf if c.imageFile
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

        # Build docx document
        doc = build_document(data)

        if output_path:
            out = Path(output_path).resolve()
        else:
            safe_name = (
                "".join(c for c in data.screen.name if c.isalnum() or c in (" ", "_", "-"))
                .strip()
                .replace(" ", "_")
            )
            out = Path(data.exportDir) / f"{safe_name}.docx"

        out.parent.mkdir(parents=True, exist_ok=True)
        doc.save(str(out))

        # Save analysis data JSON inside export folder
        export_dir = Path(data.exportDir)
        analysis_json_path = export_dir / "analysis.json"
        analysis_json_path.write_text(
            json.dumps(analysis, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        table_count = len(doc.tables)
        image_count = len(data.screen.imageFiles) + sum(1 for c in non_leaf if c.imageFile)

        return {
            "valid": True,
            "output_path": str(out),
            "tables": table_count,
            "images": image_count,
            "warnings": warnings,
        }

    def write_analysis_json(self, data: dict, filename: str = "analysis.json") -> dict:
        """Safely write analysis data structure to analysis.json in the export directory."""
        export_dir_str = data.get("exportDir")
        if not export_dir_str:
            return {
                "success": False,
                "error": "Missing 'exportDir' key in the analysis data.",
            }

        export_dir = Path(export_dir_str)
        if not export_dir.is_dir():
            return {
                "success": False,
                "error": f"The exportDir '{export_dir_str}' is not a valid directory.",
            }

        try:
            out_path = export_dir / filename
            out_path.write_text(
                json.dumps(data, indent=2, ensure_ascii=False),
                encoding="utf-8",
            )
            return {
                "success": True,
                "analysis_path": str(out_path.resolve()),
            }
        except Exception as e:
            logger.error("Failed to write analysis JSON file to export directory: %s", e)
            return {
                "success": False,
                "error": f"Failed to write analysis JSON file: {e}",
            }
