"""FastMCP server — tools and prompts for the TLGP toolchain.

Exposes tools for screenshot annotation and .docx specification document generation.
"""

from __future__ import annotations

import json

from mcp.server.fastmcp import Context, FastMCP
from tlgp_logger import get_logger

from mcp_server.client import WorkspaceClient
from mcp_server.manager import DaemonManager
from mcp_server.prompts import (
    get_prompt_section,
    get_spec_workflow_prompt,
    get_strict_guidelines_content,
)
from mcp_server.services import SpecGeneratorService

logger = get_logger(__name__)

# ============================================================
# Core Services & Clients
# ============================================================

_client: WorkspaceClient | None = None
_daemon_manager: DaemonManager | None = None
_spec_service: SpecGeneratorService | None = None


def get_client() -> WorkspaceClient:
    """Lazily construct and return the workspace client."""
    global _client
    if _client is None:
        _client = WorkspaceClient()
    return _client


def get_daemon_manager() -> DaemonManager:
    """Lazily construct and return the daemon manager, registering exit handlers."""
    global _daemon_manager
    if _daemon_manager is None:
        _daemon_manager = DaemonManager()
        _daemon_manager.register_exit_handlers()
    return _daemon_manager


def get_spec_service() -> SpecGeneratorService:
    """Lazily construct and return the specification service."""
    global _spec_service
    if _spec_service is None:
        _spec_service = SpecGeneratorService()
    return _spec_service


# ============================================================
# Server Instance
# ============================================================

mcp = FastMCP(
    "tlgp-tools",
    instructions=(
        "TLGP Tools MCP server. Provides tools for annotating screenshots and compiling .docx specification documents.\n\n"
        "SYSTEM DIRECTIVES & BOUNDARIES:\n"
        f"{get_strict_guidelines_content()}\n\n"
        "REQUIRED REFERENCE GUIDES & DATA:\n"
        "Prior to performing any analysis or constructing parameters, read the resource guides:\n"
        "   - 'tlgp://spec/schema' (JSON Schema structure)\n"
        "   - 'tlgp://spec/classification-guide' (UI Control type rules)\n"
        "   - 'tlgp://spec/example-analysis' (Complete example analysis data structure)\n"
        "   - 'tlgp://workspace/state' (Active annotation hierarchy state)"
    ),
)


# ============================================================
# Resources
# ============================================================


@mcp.resource("tlgp://workspace/state")
async def get_workspace_state_resource() -> str:
    """Read-only access to the latest flat-map JSON WorkspaceState."""
    state = await get_client().get_workspace_state()
    return json.dumps(state, indent=2, ensure_ascii=False)


@mcp.resource("tlgp://workspace/components/{comp_id}/image")
async def get_component_image_resource(comp_id: str) -> bytes:
    """Fetch the raw image bytes for a specific component from the Engine."""
    return await get_client().get_image_bytes(comp_id)


@mcp.resource("tlgp://daemons/logs/{daemon_name}")
def get_daemon_logs_resource(daemon_name: str) -> str:
    """Read the recent log lines from engine or gui daemon.

    Args:
        daemon_name: The daemon name ('engine' or 'gui').
    """
    res = get_daemon_manager().read_daemon_logs(daemon_name, lines=100)
    return res.get("logs", "")


@mcp.resource("tlgp://daemons/status")
async def get_daemon_status_resource() -> str:
    """Read-only access to the running status of Engine and GUI daemons."""
    status = await get_daemon_manager().get_status(client=get_client().client)
    return json.dumps(status, indent=2, ensure_ascii=False)


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
    return await get_daemon_manager().launch_annotator(
        screenshot_path=screenshot_path,
        workspace_zip=workspace_zip,
        client=get_client().client,
    )


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
    return await get_client().download_image(comp_id, output_path, show_children)


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
    return await get_client().download_workspace_assets(
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
    return await get_client().export_workspace(output_path)


@mcp.tool()
async def generate_spec_doc(
    ctx: Context,
    analysis: dict | None = None,
    analysis_path: str | None = None,
    output_path: str | None = None,
    validate_only: bool = False,
) -> dict:
    """Generate a TLGP specification document (.docx).

    CRITICAL REQUIREMENTS:
    1. Vietnamese Translation: All component labels, descriptions, and outputs inside the analysis payload must be written in Vietnamese.
    2. Parameter Payload Limitation: If the analysis dictionary is large (e.g., over 10KB), passing it directly via the 'analysis' parameter may corrupt the JSON-RPC transport middleware. You MUST call `write_analysis_json` first to save it to disk, and pass the resulting absolute path via the 'analysis_path' parameter.
    3. Strict Validation Workflow: Always run `generate_spec_doc(validate_only=True)` first to validate the payload structure and component images. Address any warnings or errors before proceeding to document generation with `validate_only=False`.
    4. Guidelines: Read resources `tlgp://spec/classification-guide` and `tlgp://spec/schema` before preparing the payload.
    5. Output Location: When generating the document (validate_only=False), the analysis JSON payload is always saved as `analysis.json` in the same directory as the generated `.docx` file.

    Args:
        analysis: Complete analysis data dict.
        analysis_path: Path to saved analysis.json file (highly recommended for large payloads to bypass size limits).
        output_path: Where to save the .docx. Defaults to <screen_name>.docx in exportDir. The analysis.json file will be written to the same directory.
        validate_only: If True, validates structure and checks files without compiling.

    Returns:
        dict with valid, output_path, tables, images, warnings, errors.
    """
    return await get_spec_service().generate(
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
        state = await get_client().get_workspace_state()
        state_json = json.dumps(state, indent=2, ensure_ascii=False)
    except Exception:
        pass

    return [
        get_spec_workflow_prompt().replace("{section_prefix}", section_prefix),
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
    """Safely write the analysis dictionary to a JSON file in the export directory.

    This tool is the primary payload size limit bypass. If your analysis data is large 
    (e.g., >10KB), call this tool first to persist the payload and get an absolute path, 
    which you then pass to the generate/validate tool.

    Args:
        data: Complete analysis data dict.
        filename: Name of the output JSON file (defaults to "analysis.json").
    """
    return get_spec_service().write_analysis_json(data, filename)


@mcp.tool()
def kill_daemons() -> dict:
    """Cleanly terminate all background annotation GUI and engine processes."""
    return get_daemon_manager().kill_daemons()


@mcp.tool()
async def set_workspace_readonly(read_only: bool) -> dict:
    """Toggle the engine workspace read-only mode to prevent or allow mutations.

    Args:
        read_only: True to lock workspace in read-only mode, False to allow edits.
    """
    return await get_client().set_workspace_readonly(read_only)
