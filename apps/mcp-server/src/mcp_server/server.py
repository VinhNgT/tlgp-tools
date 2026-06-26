"""FastMCP server — tools and prompts for the TLGP toolchain.

Exposes tools for screenshot annotation and .docx specification document generation.
"""

from __future__ import annotations

import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import TypedDict

from mcp.server.fastmcp import Context, FastMCP
from tlgp_logger import get_logger

from mcp_server.client import ImageExportResult, WorkspaceClient
from mcp_server.manager import DaemonManager
from mcp_server.prompts import (
    get_prompt_section,
    get_spec_workflow_content,
    get_strict_guidelines_content,
)
from mcp_server.services import DocGenResult, SpecGeneratorService

logger = get_logger(__name__)


# ============================================================
# Lifespan — server-scoped dependency management
# ============================================================


class AppContext(TypedDict):
    client: WorkspaceClient
    daemon_manager: DaemonManager
    spec_service: SpecGeneratorService


@asynccontextmanager
async def app_lifespan(server: FastMCP) -> AsyncIterator[AppContext]:
    """Initialize and tear down shared services for the server's lifetime."""
    client = WorkspaceClient()
    daemon_manager = DaemonManager()
    try:
        yield {
            "client": client,
            "daemon_manager": daemon_manager,
            "spec_service": SpecGeneratorService(client=client),
        }
    finally:
        daemon_manager.cleanup()
        await client.close()


def _get_client(ctx: Context) -> WorkspaceClient:
    """Retrieve the shared WorkspaceClient from the lifespan context."""
    return ctx.request_context.lifespan_context["client"]


def _get_daemon_manager(ctx: Context) -> DaemonManager:
    """Retrieve the shared DaemonManager from the lifespan context."""
    return ctx.request_context.lifespan_context["daemon_manager"]


def _get_spec_service(ctx: Context) -> SpecGeneratorService:
    """Retrieve the shared SpecGeneratorService from the lifespan context."""
    return ctx.request_context.lifespan_context["spec_service"]


# ============================================================
# Server Instance
# ============================================================

mcp = FastMCP(
    "tlgp-tools",
    lifespan=app_lifespan,
    instructions=(
        "TLGP Tools MCP server. Provides tools for annotating screenshots "
        "and compiling .docx specification documents.\n\n"
        "AVAILABLE TOOLS:\n"
        "  - launch_annotator: Start a new annotator GUI instance\n"
        "  - connect_to_annotator: Connect to an already-running annotator\n"
        "  - export_images: Export cropped component images from the workspace\n"
        "  - generate_spec_doc: Validate and generate the .docx specification document\n\n"
        "SYSTEM DIRECTIVES & BOUNDARIES:\n"
        f"{get_strict_guidelines_content()}\n\n"
        "WORKFLOW:\n"
        "You MUST read the resource 'tlgp://spec/workflow' before starting any work. "
        "It contains the complete step-by-step instructions.\n\n"
        "REFERENCE GUIDES:\n"
        "  - 'tlgp://spec/schema' (JSON Schema structure)\n"
        "  - 'tlgp://spec/classification-guide' (UI Control type rules)\n"
        "  - 'tlgp://spec/example-analysis' (Complete example analysis data)\n"
        "  - 'tlgp://workspace/state' (Active annotation hierarchy state)"
    ),
)


# ============================================================
# Resources
# ============================================================


@mcp.resource("tlgp://workspace/state")
async def get_workspace_state_resource(ctx: Context) -> str:
    """Read-only access to the latest flat-map JSON WorkspaceState."""
    state = await _get_client(ctx).get_workspace_state()
    return json.dumps(state.model_dump(mode="json"), indent=2, ensure_ascii=False)


@mcp.resource("tlgp://spec/workflow")
def get_spec_workflow_resource() -> str:
    """End-to-end workflow guide for creating specification documents."""
    return get_spec_workflow_content()


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
    ctx: Context,
    path: str | None = None,
) -> dict:
    """Launch the TLGP Annotation Tool GUI.

    Spawns the annotation tool as a subprocess. The tool opens a GUI window
    where the user annotates screenshots with component boxes. The process
    runs in the background — the agent should wait for the user to finish.

    Args:
        path: Optional path to a raw screenshot image or a previously exported .zip workspace to load.

    Returns:
        dict with annotator_ready, annotator_url.
    """
    client = _get_client(ctx)
    daemon_manager = _get_daemon_manager(ctx)
    res = await daemon_manager.launch_annotator(
        path=path,
        client=client.client,
    )
    if res.get("annotator_ready") and "annotator_url" in res:
        client.base_url = res["annotator_url"]
    return res


@mcp.tool()
async def export_images(
    ctx: Context,
    output_path: str,
) -> ImageExportResult:
    """Export cropped component images (both raw and annotated) from the workspace screenshot to a directory.

    Args:
        output_path: Absolute path to the destination directory.

    Returns:
        dict with output_path, segment/image counts, and root_images (list of filenames of the exported root segments).
    """
    return await _get_client(ctx).export_images(output_path, mode="both")


@mcp.tool()
async def generate_spec_doc(
    ctx: Context,
    analysis_path: str,
    output_path: str | None = None,
    validate_only: bool = False,
) -> DocGenResult:
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
    return await _get_spec_service(ctx).generate(
        analysis_path=analysis_path,
        ctx=ctx,
        output_path=output_path,
        validate_only=validate_only,
    )


@mcp.tool()
async def connect_to_annotator(ctx: Context, url: str) -> dict:
    """Connect the MCP server to a running annotator instance at the specified URL.

    Args:
        url: The URL of the running annotator instance (e.g. 'http://127.0.0.1:55432').
    """
    client = _get_client(ctx)
    client.base_url = url
    _get_daemon_manager(ctx).annotator_url = url
    try:
        is_ok = await client.check_connection()
        if is_ok:
            result: dict = {
                "status": "success",
                "message": f"Successfully connected to the annotator instance at {url}",
                "screen_name": None,
                "components": 0,
            }
            # Fetch workspace summary as debug info
            try:
                state = await client.get_workspace_state()
                result["screen_name"] = state.screen.name or None
                result["components"] = len(state.components)
            except Exception:
                logger.warning(
                    "Connected but failed to fetch workspace summary", exc_info=True
                )
            return result
        else:
            return {
                "status": "error",
                "message": f"Failed to connect to annotator at {url}: health check failed",
                "screen_name": None,
                "components": 0,
            }
    except Exception as e:
        return {
            "status": "error",
            "message": f"Failed to connect to annotator at {url}: {e}",
            "screen_name": None,
            "components": 0,
        }
