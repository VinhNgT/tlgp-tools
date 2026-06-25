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


class SpecGeneratorService:
    """Orchestrates validation, metadata elicitation, and compilation of specification documents."""

    def __init__(self):
        pass

    async def generate(
        self,
        analysis_path: str,
        ctx: Context | None = None,
        output_path: str | None = None,
        validate_only: bool = False,
    ) -> dict:
        """Validate, elicit missing descriptions, and generate the final specification document."""
        if ctx:
            await ctx.report_progress(
                10, 100, "Loading and validating analysis data..."
            )

        try:
            with open(analysis_path, encoding="utf-8") as f:
                analysis = json.load(f)
        except Exception as e:
            logger.error(
                "Failed to load analysis file from %s: %s", analysis_path, e
            )
            return {
                "valid": False,
                "errors": [f"Failed to read analysis_path: {e}"],
                "warnings": [],
            }

        if ctx:
            await ctx.report_progress(60, 100, "Running document generation...")

        result = self.generate_spec_doc_impl(
            analysis=analysis,
            output_path=output_path,
            validate_only=validate_only,
        )

        if not validate_only and result.get("valid"):
            docx_path = Path(result["output_path"])
            workspace_zip_path = docx_path.parent / "workspace.zip"
            if ctx:
                await ctx.log(
                    "info", f"Exporting workspace state to {workspace_zip_path}..."
                )
            try:
                from mcp_server.client import WorkspaceClient  # noqa: PLC0415

                client = WorkspaceClient()
                try:
                    await client.export_workspace(str(workspace_zip_path))
                finally:
                    await client.close()
            except Exception as e:
                logger.error("Failed to export workspace.zip next to docx: %s", e)
                if ctx:
                    await ctx.log(
                        "warning", f"Failed to export workspace.zip next to docx: {e}"
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

        if not data.all_apis:
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
                "apis": len(data.all_apis),
                "images": image_count,
            }

        # Build docx document
        doc = build_document(data)

        if output_path:
            out = Path(output_path).resolve()
        else:
            safe_name = (
                "".join(
                    c for c in data.screen.name if c.isalnum() or c in (" ", "_", "-")
                )
                .strip()
                .replace(" ", "_")
            )
            out = Path(data.imageDir) / f"{safe_name}.docx"

        out.parent.mkdir(parents=True, exist_ok=True)
        doc.save(str(out))

        # Save analysis data JSON alongside the exported docx
        analysis_json_path = out.parent / "analysis.json"
        analysis_json_path.write_text(
            json.dumps(analysis, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )

        table_count = len(doc.tables)
        image_count = len(data.screen.imageFiles) + sum(
            1 for c in non_leaf if c.imageFile
        )

        return {
            "valid": True,
            "output_path": str(out),
            "tables": table_count,
            "images": image_count,
            "warnings": warnings,
        }
