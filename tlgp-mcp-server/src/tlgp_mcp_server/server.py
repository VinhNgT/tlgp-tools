"""FastMCP server registration — tools, resources, and prompts.

This module defines the MCP server instance and registers all capabilities.
Each tool, resource, and prompt is implemented in its own submodule and
wired up here via decorators.
"""

from __future__ import annotations

import logging

from mcp.server.fastmcp import FastMCP

from tlgp_mcp_server.tools.launch_annotator import launch_annotator_impl
from tlgp_mcp_server.tools.prepare_analysis import prepare_analysis_impl
from tlgp_mcp_server.tools.update_analysis import update_analysis_impl
from tlgp_mcp_server.tools.finalize import finalize_impl
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
def prepare_analysis(
    output_dir: str,
    section_prefix: str = "1.1",
) -> dict:
    """Discover annotations, scaffold analysis.json, and return docs.

    One-shot preparation that handles all workspace states. Discovers
    annotation exports, scaffolds the analysis.json template (or loads
    an existing one), and returns the schema docs + control-type guide
    inline so everything is available in one response.

    Status values:
    - "needs_annotation": No exports found. Launch the annotator first.
    - "ready": analysis.json exists, ready for vision/codebase work.
    - "complete": analysis.json + .docx already exist.
    - "error": Something went wrong (see message).

    Args:
        output_dir: Path to the output directory to inspect.
        section_prefix: Section number prefix (default "1.1").

    Returns:
        dict with status, analysis_path, components summary,
        image_files, to_fill list, schema, and control_types.
    """
    return prepare_analysis_impl(output_dir, section_prefix)


@mcp.tool()
def update_analysis(
    json_path: str,
    updates: list[dict],
) -> dict:
    """Apply targeted updates to analysis.json.

    Each update is a dict with "path" and "value" keys. The path uses
    dot notation with array indices to target specific fields.

    Path examples:
    - "components[0].description" — set a component description
    - "components[0].children[2].controlType" — set a control type
    - "components[0].interactions" — set the interactions list
    - "apis" — replace the entire APIs list
    - "screen.interactions" — set screen-level interactions
    - "discrepancies" — set the discrepancies list

    The file is validated against the schema after updates are applied.
    If validation fails, no changes are saved.

    Args:
        json_path: Path to the analysis.json file.
        updates: List of {"path": "...", "value": ...} dicts.

    Returns:
        dict with success status, applied paths, and current summary.
    """
    return update_analysis_impl(json_path, updates)


@mcp.tool()
def finalize(
    json_path: str,
    output_path: str | None = None,
) -> dict:
    """Validate analysis.json and generate the .docx specification.

    Validates the analysis data, checks all image references, and
    generates the formatted .docx document if everything is valid.
    If validation fails, returns errors without generating.

    Args:
        json_path: Path to the analysis.json file.
        output_path: Where to save the .docx. Defaults to
            <screen_name>.docx next to the JSON.

    Returns:
        dict with valid (bool), output_path, tables, images,
        warnings, and errors if any.
    """
    return finalize_impl(json_path, output_path)


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

    Guides the agent through: preparing the workspace, vision analysis,
    codebase analysis, and generating the final .docx.

    Args:
        section_prefix: Section number prefix (default "1.1").
    """
    return SPEC_WORKFLOW_PROMPT.format(section_prefix=section_prefix)
