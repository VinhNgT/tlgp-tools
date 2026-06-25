"""FastMCP server — tools and prompts for the TLGP toolchain.

Exposes tools for screenshot annotation and .docx specification document generation.
"""

from __future__ import annotations

import json
import re

from typing import Literal

from mcp.server.fastmcp import Context, FastMCP
from tlgp_logger import get_logger

from mcp_server.client import WorkspaceClient
from mcp_server.manager import DaemonManager
from mcp_server.prompts import (
    get_prompt_section,
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
    """Lazily construct and return the daemon manager."""
    global _daemon_manager
    if _daemon_manager is None:
        _daemon_manager = DaemonManager()
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
    path: str | None = None,
) -> dict:
    """Launch the TLGP Annotation Tool GUI.

    Spawns the annotation tool as a subprocess. The tool opens a GUI window
    where the user annotates screenshots with component boxes. The process
    runs in the background — the agent should wait for the user to finish.

    Args:
        path: Optional path to a raw screenshot image or a previously exported .zip workspace to load.

    Returns:
        dict with annotator_pid and annotator_ready.
    """
    res = await get_daemon_manager().launch_annotator(
        path=path,
        client=get_client().client,
    )
    if res.get("annotator_ready") and "port" in res:
        get_client().base_url = f"http://127.0.0.1:{res['port']}"
    return res






@mcp.tool()
async def export_images(
    output_path: str,
) -> dict:
    """Export cropped component images (both raw and annotated) from the workspace screenshot to a directory.

    Args:
        output_path: Absolute path to the destination directory.
    """
    return await get_client().export_images(output_path, mode="both")




@mcp.tool()
async def generate_spec_doc(
    ctx: Context,
    analysis_path: str,
    output_path: str | None = None,
    validate_only: bool = False,
) -> dict:
    """Generate a TLGP specification document (.docx).

    CRITICAL REQUIREMENTS:
    1. Vietnamese Translation: All component labels, descriptions, and outputs inside the analysis payload must be written in Vietnamese.
    2. Strict Validation Workflow: Always run `generate_spec_doc(validate_only=True)` first to validate the payload structure and component images. Address any warnings or errors before proceeding to document generation with `validate_only=False`.
    3. Guidelines: Read resources `tlgp://spec/classification-guide` and `tlgp://spec/schema` before preparing the payload.
    4. Output Location: When generating the document (validate_only=False), the analysis JSON payload is always saved as `analysis.json` in the same directory as the generated `.docx` file.

    Args:
        analysis_path: Path to the saved analysis.json file on disk.
        output_path: Where to save the .docx. Defaults to <screen_name>.docx in imageDir. The analysis.json file will be written to the same directory.
        validate_only: If True, validates structure and checks files without compiling.

    Returns:
        dict with valid, output_path, tables, images, warnings, errors.
    """
    return await get_spec_service().generate(
        analysis_path=analysis_path,
        ctx=ctx,
        output_path=output_path,
        validate_only=validate_only,
    )


@mcp.tool()
async def connect_to_annotator(url: str) -> dict:
    """Connect the MCP server to a running annotator instance at the specified URL.

    Args:
        url: The URL of the running annotator instance (e.g. 'http://127.0.0.1:55432').
    """
    client = get_client()
    client.base_url = url
    get_daemon_manager().annotator_url = url
    try:
        is_ok = await client.check_connection()
        if is_ok:
            return {
                "status": "success",
                "message": f"Successfully connected to the annotator instance at {url}",
            }
        else:
            return {
                "status": "error",
                "message": f"Failed to connect to annotator at {url}: health check failed",
            }
    except Exception as e:
        return {
            "status": "error",
            "message": f"Failed to connect to annotator at {url}: {e}",
        }


