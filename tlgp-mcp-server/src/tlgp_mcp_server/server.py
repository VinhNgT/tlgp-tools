"""FastMCP server registration — tools, resources, and prompts.

This module defines the MCP server instance and registers all capabilities.
Each tool, resource, and prompt is implemented in its own submodule and
wired up here via decorators.
"""

from __future__ import annotations

import logging

from mcp.server.fastmcp import FastMCP

from tlgp_mcp_server.tools.launch_annotator import launch_annotator_impl
from tlgp_mcp_server.tools.list_exports import list_exports_impl
from tlgp_mcp_server.tools.parse_annotations import parse_annotations_impl
from tlgp_mcp_server.tools.scaffold_analysis import scaffold_analysis_impl
from tlgp_mcp_server.tools.validate_analysis import validate_analysis_impl
from tlgp_mcp_server.tools.generate_docx import generate_docx_impl
from tlgp_mcp_server.resources import (
    ANALYSIS_SCHEMA_TEXT,
    CONTROL_TYPES_TEXT,
    get_formatting_spec_text,
)
from tlgp_mcp_server.prompts import SPEC_WORKFLOW_PROMPT

logger = logging.getLogger(__name__)

# ============================================================
# Server instance
# ============================================================

mcp = FastMCP(
    "tlgp-tools",
    instructions=(
        "TLGP Tools MCP server. Provides tools for annotating screenshots, "
        "scaffolding analysis data, and generating .docx specification documents. "
        "Use the `create_spec_doc` prompt to get the full workflow guide."
    ),
)

# ============================================================
# Tools
# ============================================================


@mcp.tool()
def launch_annotator(
    output_dir: str,
    screenshot_paths: list[str] | None = None,
) -> dict:
    """Launch the TLGP Annotation Tool GUI.

    Spawns the annotation tool as a subprocess. The tool opens a GUI window
    where the user annotates screenshots with component boxes. The process
    runs in the background — the agent should wait for the user to finish.

    Args:
        output_dir: Directory where the tool will save exported files.
        screenshot_paths: Optional list of screenshot image paths to pre-load.

    Returns:
        dict with pid and output_dir.
    """
    return launch_annotator_impl(output_dir, screenshot_paths)


@mcp.tool()
def list_exports(output_dir: str) -> dict:
    """Inspect an output directory and report its state.

    Discovers annotation JSONs, analysis JSONs, annotated images, and
    generated .docx files. Returns a status indicating what the agent
    should do next.

    Status values:
    - "not_found": Directory doesn't exist. Create it, then launch annotator.
    - "empty": Directory exists but has no recognized files. Launch annotator.
    - "annotations_only": Has annotation JSON + images, no analysis.json yet.
    - "ready": Has analysis.json ready for validation and generation.
    - "complete": Has analysis.json + generated .docx already.
    - "malformed": Has partial data with missing critical files.

    Args:
        output_dir: Path to the output directory to inspect.

    Returns:
        dict with status, file inventory, and any issues found.
    """
    return list_exports_impl(output_dir)


@mcp.tool()
def parse_annotations(json_path: str) -> dict:
    """Parse the annotation tool's exported JSON file.

    Reads the JSON exported by tlgp-annotation-tool and returns the
    validated, structured component hierarchy including screen metadata,
    image dimensions, cut lines, and the full component tree.

    Args:
        json_path: Path to the annotation export JSON file.

    Returns:
        dict with screen_name, description, image dimensions, components tree.
    """
    return parse_annotations_impl(json_path)


@mcp.tool()
def scaffold_analysis(
    annotation_json: str,
    section_prefix: str = "1.1",
    output_path: str | None = None,
) -> dict:
    """Auto-generate an analysis.json template from annotation exports.

    Pre-fills everything that can be derived from the annotation data:
    component IDs, labels, isLeaf flags, image file mappings, child STT
    numbering, and screen metadata. Leaves empty slots for fields that
    require agent intelligence: control types, descriptions, interactions,
    and API data.

    Args:
        annotation_json: Path to the annotation export JSON.
        section_prefix: Section number prefix (default "1.1").
        output_path: Where to save the generated analysis.json.
            Defaults to <export_dir>/analysis.json.

    Returns:
        dict with output_path, list of pre_filled fields, and to_fill fields.
    """
    return scaffold_analysis_impl(annotation_json, section_prefix, output_path)


@mcp.tool()
def validate_analysis(json_path: str) -> dict:
    """Validate a completed analysis.json file.

    Checks the JSON against the doc generator's Pydantic schema and
    cross-references that all referenced image files exist on disk.
    Reports errors (blocking) and warnings (informational).

    Args:
        json_path: Path to the analysis.json file.

    Returns:
        dict with valid (bool), errors, warnings, and summary.
    """
    return validate_analysis_impl(json_path)


@mcp.tool()
def generate_docx(
    json_path: str,
    output_path: str | None = None,
) -> dict:
    """Generate a .docx specification document from analysis.json.

    Reads the validated analysis.json, builds the full document with
    headings, tables, and images using the formatting spec from
    spec_format.toml, and saves the result as a .docx file.

    Args:
        json_path: Path to the analysis.json file.
        output_path: Where to save the .docx. Defaults to
            <screen_name>.docx next to the JSON.

    Returns:
        dict with output_path, table count, and image count.
    """
    return generate_docx_impl(json_path, output_path)


# ============================================================
# Resources
# ============================================================


@mcp.resource("tlgp://schema/analysis-json")
def analysis_schema_resource() -> str:
    """Documented schema for analysis.json — every field and its purpose."""
    return ANALYSIS_SCHEMA_TEXT


@mcp.resource("tlgp://schema/control-types")
def control_types_resource() -> str:
    """UI control classification guide for vision analysis."""
    return CONTROL_TYPES_TEXT


@mcp.resource("tlgp://spec/formatting")
def formatting_spec_resource() -> str:
    """Current formatting configuration from spec_format.toml."""
    return get_formatting_spec_text()


# ============================================================
# Prompts
# ============================================================


@mcp.prompt()
def create_spec_doc(section_prefix: str = "1.1") -> str:
    """Full workflow for creating a TLGP screen specification document.

    Guides the agent through: launching the annotator, scaffolding
    analysis.json, filling in control types and API data from codebase
    analysis, validating, and generating the final .docx.

    Args:
        section_prefix: Section number prefix (default "1.1").
    """
    return SPEC_WORKFLOW_PROMPT.format(section_prefix=section_prefix)
