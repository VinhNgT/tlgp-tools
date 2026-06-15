"""FastMCP server — tools and prompts for the TLGP toolchain.

Exposes two tools (one per underlying package) and one orchestration prompt:
- launch_annotator  → tlgp-annotation-tool
- generate_spec_doc → doc-generator
- spec_doc_workflow → prompt that guides the agent through the full workflow
"""

from __future__ import annotations

import json

from mcp.server.fastmcp import Context, FastMCP
from tlgp_logger import get_logger

from mcp_server.prompts import SPEC_WORKFLOW_PROMPT, get_prompt_section
from mcp_server.tools.daemon_control import (
    get_daemon_status_impl,
    kill_daemons_impl,
    read_daemon_logs_impl,
    register_exit_handlers,
    set_workspace_readonly_impl,
)
from mcp_server.tools.generate_spec_doc import (
    generate_spec_doc_impl,
    write_analysis_json_impl,
)
from mcp_server.tools.launch_annotator import launch_annotator_impl
from mcp_server.tools.workspace_api import (
    download_image_impl,
    download_workspace_assets_impl,
    export_workspace_impl,
    get_image_bytes_impl,
    get_workspace_state_impl,
)

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

register_exit_handlers()


# ============================================================
# Resources
# ============================================================


@mcp.resource("tlgp://workspace/state")
async def get_workspace_state_resource() -> str:
    """Read-only access to the latest flat-map JSON WorkspaceState."""
    state = await get_workspace_state_impl()
    return json.dumps(state, indent=2, ensure_ascii=False)


@mcp.resource("tlgp://workspace/components/{comp_id}/image")
async def get_component_image_resource(comp_id: str) -> bytes:
    """Fetch the raw image bytes for a specific component from the Engine."""
    return await get_image_bytes_impl(comp_id)


@mcp.resource("tlgp://daemons/logs/{daemon_name}")
def get_daemon_logs_resource(daemon_name: str) -> str:
    """Read the recent log lines from engine or gui daemon.

    Args:
        daemon_name: The daemon name ('engine' or 'gui').
    """
    res = read_daemon_logs_impl(daemon_name, lines=100)
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
async def generate_spec_doc(
    ctx: Context,
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
    await ctx.report_progress(10, 100, "Loading and validating analysis data...")

    if analysis_path:
        try:
            with open(analysis_path, encoding="utf-8") as f:
                analysis = json.load(f)
        except Exception as e:
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

    # If not in validate_only mode, run description elicitation
    if not validate_only:
        try:
            from doc_generator.models import AnalysisData
            from pydantic import BaseModel, Field

            class ComponentDescription(BaseModel):
                description: str = Field(..., description="A brief 1-sentence UX description of the component")

            data = AnalysisData.model_validate(analysis)
            non_leaf = [c for c in data.components if not c.isLeaf]

            updated = False
            for comp in non_leaf:
                if not comp.description:
                    await ctx.report_progress(30, 100, f"Eliciting description for '{comp.label}'...")
                    await ctx.log("info", f"Eliciting description for component '{comp.label}'...")
                    try:
                        result = await ctx.elicit(
                            message=f"The component '{comp.label}' (id={comp.id}) has an empty description. Please provide a UX description.",
                            schema=ComponentDescription
                        )
                        if result.action == "accept":
                            comp.description = result.data.description
                            # Update the dict structure
                            for c_dict in analysis.get("components", []):
                                if c_dict.get("id") == comp.id:
                                    c_dict["description"] = comp.description
                                    updated = True
                                    break
                    except Exception as e:
                        await ctx.log("error", f"Elicitation failed for component '{comp.label}': {e}")

            if updated and analysis_path:
                try:
                    with open(analysis_path, "w", encoding="utf-8") as f:
                        json.dump(analysis, f, indent=2, ensure_ascii=False)
                except Exception as e:
                    await ctx.log("warning", f"Failed to write updated analysis back to {analysis_path}: {e}")

        except Exception:
            # Let the main generator function handle parsing/validation error output
            pass

    await ctx.report_progress(60, 100, "Running document generation...")

    result = generate_spec_doc_impl(
        analysis=analysis,
        analysis_path=None,
        output_path=output_path,
        validate_only=validate_only,
    )

    await ctx.report_progress(100, 100, "Spec generation complete.")
    return result



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
        state = await get_workspace_state_impl()
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
    return write_analysis_json_impl(data, filename)


@mcp.tool()
async def get_daemon_status() -> dict:
    """Get status of background annotation tool GUI and engine processes."""
    return await get_daemon_status_impl()


@mcp.tool()
def kill_daemons() -> dict:
    """Cleanly terminate all background annotation GUI and engine processes."""
    return kill_daemons_impl()


@mcp.tool()
def read_daemon_logs(daemon: str = "engine", lines: int = 100) -> dict:
    """Read the recent log lines from engine or gui daemon.

    Args:
        daemon: The daemon name ('engine' or 'gui').
        lines: Max number of tailing log lines to retrieve (default 100).
    """
    return read_daemon_logs_impl(daemon, lines)


@mcp.tool()
async def set_workspace_readonly(read_only: bool) -> dict:
    """Toggle the engine workspace read-only mode to prevent or allow mutations.

    Args:
        read_only: True to lock workspace in read-only mode, False to allow edits.
    """
    return await set_workspace_readonly_impl(read_only)

