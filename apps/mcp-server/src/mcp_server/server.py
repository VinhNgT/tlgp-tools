"""FastMCP server — tools and prompts for the TLGP toolchain.

Exposes two tools (one per underlying package) and one orchestration prompt:
- launch_annotator  → tlgp-annotation-tool
- generate_spec_doc → doc-generator
- spec_doc_workflow → prompt that guides the agent through the full workflow
"""

from __future__ import annotations

import os

import httpx
from mcp.server.fastmcp import FastMCP
from tlgp_logger import get_logger

from mcp_server.exceptions import ApiClientError
from mcp_server.prompts import SPEC_WORKFLOW_PROMPT
from mcp_server.tools.workspace_api import (
    download_image_impl,
    download_workspace_assets_impl,
    export_workspace_impl,
    get_workspace_state_impl,
)
from mcp_server.tools.generate_spec_doc import generate_spec_doc_impl
from mcp_server.tools.launch_annotator import launch_annotator_impl

logger = get_logger(__name__)

# ============================================================
# Server instance
# ============================================================

mcp = FastMCP(
    "tlgp-tools",
    instructions=(
        "TLGP Tools MCP server. Provides tools for annotating screenshots "
        "and generating .docx specification documents. "
        "CRITICAL DIRECTIVE: You are in a strict Read-Only mode. You cannot "
        "mutate the Engine state. Your role is to analyze the state and generate "
        "specifications. Do NOT use terminal tools (like curl) to interact "
        "with the Engine REST API. "
        "Use the `spec_doc_workflow` prompt to get the full workflow guide."
    ),
)

# ============================================================
# Tools
# ============================================================


@mcp.tool()
async def launch_annotator(
    screenshot_path: str | None = None,
    workspace_zip: str | None = None,
) -> dict:
    """Launch the TLGP Annotation Tool GUI.

    Spawns the annotation tool as a subprocess. The tool opens a GUI window
    where the user annotates screenshots with component boxes. The process
    runs in the background — the agent should wait for the user to finish.

    Args:
        screenshot_path: Optional path to a raw screenshot image to load initially.
        workspace_zip: Optional path to a previously exported .zip workspace.

    Returns:
        dict with engine_pid and gui_pid.
    """
    return await launch_annotator_impl(screenshot_path, workspace_zip)


@mcp.tool()
async def get_workspace_state() -> dict:
    """Fetch the current flat-map JSON WorkspaceState from the running Engine.

    Use this tool to read the latest annotation hierarchy automatically,
    instead of relying on local JSON files.
    """
    return await get_workspace_state_impl()


@mcp.tool()
async def download_image(
    output_path: str,
    comp_id: str = "root",
    show_children: bool = False,
) -> dict:
    """Download the full root screenshot image or a specific component image from the Engine.

    Args:
        output_path: Path where the image should be saved.
        comp_id: The component ID (UUID) or "root" (default) for the full screenshot.
        show_children: Whether to overlay annotated child component boxes on the image.
    """
    return await download_image_impl(comp_id, output_path, show_children)

@mcp.tool()
async def download_workspace_assets(
    output_dir: str,
    include_state: bool = True,
    include_root: bool = True,
    show_root_children: bool = False,
    component_ids: list[str] | None = None,
    show_component_children: bool = False,
) -> dict:
    """Download the state, root image, and component images for a workspace in a single batch.

    Extracts the downloaded workspace assets directly into output_dir.

    Args:
        output_dir: Directory where the assets should be extracted.
        include_state: Whether to download and extract the workspace state JSON file.
        include_root: Whether to download and extract the root screenshot image.
        show_root_children: Whether to overlay annotated child component boxes on the root image.
        component_ids: Optional list of component UUIDs to download. If not provided, downloads all components.
        show_component_children: Whether to overlay annotated child component boxes on the component images.
    """
    return await download_workspace_assets_impl(
        output_dir=output_dir,
        include_state=include_state,
        include_root=include_root,
        show_root_children=show_root_children,
        component_ids=component_ids,
        show_component_children=show_component_children,
    )


@mcp.tool()
async def export_workspace(output_path: str) -> dict:
    """Export the current Engine workspace to a .zip file.

    Packs the WorkspaceState and the current image into a .zip archive
    that can be re-imported later.

    Args:
        output_path: Path where the .zip file should be saved.

    Returns:
        dict with status and output_path.
    """
    return await export_workspace_impl(output_path)


@mcp.tool()
def generate_spec_doc(
    analysis: dict | None = None,
    analysis_path: str | None = None,
    output_path: str | None = None,
    validate_only: bool = False,
) -> dict:
    """Generate a TLGP specification document (.docx).

    Takes completed analysis data and generates a formatted specification
    document. The analysis dict must conform to the AnalysisData schema
    (documented in the create_spec_doc prompt).

    The tool validates all data and image references, generates the .docx,
    and saves analysis.json alongside it for record-keeping.

    Args:
        analysis: Complete analysis data dict. Must include: sectionPrefix,
            exportDir, components, screen, apis, and discrepancies.
            exportDir must point to the annotation export directory
            containing the annotated images.
        analysis_path: Optional path to analysis JSON file.
        output_path: Where to save the .docx. Defaults to
            <screen_name>.docx in exportDir.
        validate_only: If True, validate the data and check images
            without generating the .docx. Use this to catch errors
            before committing to generation.

    Returns:
        dict with valid, output_path, tables, images, warnings, errors.
    """
    return generate_spec_doc_impl(
        analysis=analysis,
        analysis_path=analysis_path,
        output_path=output_path,
        validate_only=validate_only,
    )


# ============================================================
# Prompts
# ============================================================


@mcp.prompt()
def spec_doc_workflow(section_prefix: str = "1.1") -> str:
    """Full workflow for creating a TLGP screen specification document.

    Guides the agent through: annotating screenshots, performing vision
    and codebase analysis, and generating the final .docx.

    Args:
        section_prefix: Section number prefix (default "1.1").
    """
    return SPEC_WORKFLOW_PROMPT.replace("{section_prefix}", section_prefix)
