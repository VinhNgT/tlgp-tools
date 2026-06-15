"""FastMCP server — tools and prompts for the TLGP toolchain.

Exposes tools for screenshot annotation and .docx specification document generation.
"""

from __future__ import annotations

import json

from mcp.server.fastmcp import Context, FastMCP
from tlgp_logger import get_logger

from mcp_server.client import WorkspaceClient
from mcp_server.manager import DaemonManager
from mcp_server.prompts import SPEC_WORKFLOW_PROMPT, get_prompt_section
from mcp_server.services import SpecGeneratorService

logger = get_logger(__name__)

# ============================================================
# Core Services & Clients
# ============================================================

client = WorkspaceClient()
daemon_manager = DaemonManager()
spec_service = SpecGeneratorService()

# Automatically clean up daemon processes on program exit
daemon_manager.register_exit_handlers()


# ============================================================
# Server Instance
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
# Resources
# ============================================================


@mcp.resource("tlgp://workspace/state")
async def get_workspace_state_resource() -> str:
    """Read-only access to the latest flat-map JSON WorkspaceState."""
    state = await client.get_workspace_state()
    return json.dumps(state, indent=2, ensure_ascii=False)


@mcp.resource("tlgp://workspace/components/{comp_id}/image")
async def get_component_image_resource(comp_id: str) -> bytes:
    """Fetch the raw image bytes for a specific component from the Engine."""
    return await client.get_image_bytes(comp_id)


@mcp.resource("tlgp://daemons/logs/{daemon_name}")
def get_daemon_logs_resource(daemon_name: str) -> str:
    """Read the recent log lines from engine or gui daemon.

    Args:
        daemon_name: The daemon name ('engine' or 'gui').
    """
    res = daemon_manager.read_daemon_logs(daemon_name, lines=100)
    return res.get("logs", "")


@mcp.resource("tlgp://spec/schema")
def get_spec_schema_resource() -> str:
    """Read-only access to the analysis.json Schema Reference."""
    return get_prompt_section("analysis.json Schema Reference")


@mcp.resource("tlgp://spec/classification-guide")
def get_spec_classification_guide_resource() -> str:
    """Read-only access to the UI Control Type Classification Guide."""
    return get_prompt_section("UI Control Type Classification Guide")


@mcp.resource("tlgp://spec/example-analysis")
def get_spec_example_analysis_resource() -> str:
    """Read-only access to a complete example analysis.json structure."""
    return get_prompt_section("Example: Complete Analysis Dict")


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
    return await daemon_manager.launch_annotator(
        screenshot_path=screenshot_path,
        workspace_zip=workspace_zip,
        client=client.client,
    )


@mcp.tool()
async def get_workspace_state() -> dict:
    """Fetch the current flat-map JSON WorkspaceState from the running Engine.

    Use this tool to read the latest annotation hierarchy automatically,
    instead of relying on local JSON files.
    """
    return await client.get_workspace_state()


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
    return await client.download_image(comp_id, output_path, show_children)


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
    return await client.download_workspace_assets(
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
    return await client.export_workspace(output_path)


@mcp.tool()
async def generate_spec_doc(
    ctx: Context,
    analysis: dict | None = None,
    analysis_path: str | None = None,
    output_path: str | None = None,
    validate_only: bool = False,
) -> dict:
    """Generate a TLGP specification document (.docx).

    Takes completed analysis data and generates a formatted specification
    document. The analysis dict must conform to the AnalysisData schema.

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
    return await spec_service.generate(
        ctx=ctx,
        analysis=analysis,
        analysis_path=analysis_path,
        output_path=output_path,
        validate_only=validate_only,
    )


# ============================================================
# Prompts
# ============================================================


@mcp.prompt()
async def spec_doc_workflow(section_prefix: str = "1.1") -> list:
    """Full workflow for creating a TLGP screen specification document.

    Guides the agent through: annotating screenshots, performing vision
    and codebase analysis, and generating the final .docx.
    Automatically embeds the latest workspace state resource if available.

    Args:
        section_prefix: Section number prefix (default "1.1").
    """
    state_json = "{}"
    try:
        state = await client.get_workspace_state()
        state_json = json.dumps(state, indent=2, ensure_ascii=False)
    except Exception:
        pass

    return [
        SPEC_WORKFLOW_PROMPT.replace("{section_prefix}", section_prefix),
        {
            "role": "user",
            "content": {
                "type": "resource",
                "resource": {
                    "uri": "tlgp://workspace/state",
                    "mimeType": "application/json",
                    "text": state_json,
                }
            }
        }
    ]


@mcp.tool()
def write_analysis_json(data: dict, filename: str = "analysis.json") -> dict:
    """Safely write analysis data structure to analysis.json in the export directory.

    Args:
        data: Complete analysis data dict.
        filename: Name of the output JSON file (defaults to "analysis.json").
    """
    return spec_service.write_analysis_json(data, filename)


@mcp.tool()
async def get_daemon_status() -> dict:
    """Get status of background annotation tool GUI and engine processes."""
    return await daemon_manager.get_status(client=client.client)


@mcp.tool()
def kill_daemons() -> dict:
    """Cleanly terminate all background annotation GUI and engine processes."""
    return daemon_manager.kill_daemons()


@mcp.tool()
def read_daemon_logs(daemon: str = "engine", lines: int = 100) -> dict:
    """Read the recent log lines from engine or gui daemon.

    Args:
        daemon: The daemon name ('engine' or 'gui').
        lines: Max number of tailing log lines to retrieve (default 100).
    """
    return daemon_manager.read_daemon_logs(daemon, lines)


@mcp.tool()
async def set_workspace_readonly(read_only: bool) -> dict:
    """Toggle the engine workspace read-only mode to prevent or allow mutations.

    Args:
        read_only: True to lock workspace in read-only mode, False to allow edits.
    """
    return await client.set_workspace_readonly(read_only)
