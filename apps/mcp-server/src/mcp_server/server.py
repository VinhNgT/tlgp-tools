"""FastMCP server — tools and prompts for the TLGP toolchain.

Exposes tools for screenshot annotation and .docx specification document generation.
"""

from __future__ import annotations

from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import TypedDict

from mcp.server.fastmcp import Context, FastMCP
from tlgp_logger import get_logger

from mcp_server.client import WorkspaceClient
from mcp_server.manager import DaemonManager
from mcp_server.prompts import (
    get_example_analysis,
    get_spec_workflow,
    get_validation_guide,
    get_writing_guide,
)
from mcp_server.scaffold import scaffold_and_save
from mcp_server.services import SpecGeneratorService
from mcp_server.spec_editor import update_node_in_spec_file

logger = get_logger(__name__)


class _LifespanState:
    """Module-level state populated by the server lifespan.

    FastMCP resource handlers do not receive Context injection
    (functions with parameters are registered as resource templates).
    Resources that need access to lifespan-scoped services read from
    this state holder instead.

    Tools continue using Context-based DI via _get_client() etc.
    """
    client: WorkspaceClient | None = None
    spec_service: SpecGeneratorService | None = None


_lifespan_state = _LifespanState()


# ============================================================
# Lifespan — server-scoped dependency management
# ============================================================


class AppContext(TypedDict):
    client: WorkspaceClient
    daemon_manager: DaemonManager
    spec_service: SpecGeneratorService


@asynccontextmanager
async def app_lifespan(server: FastMCP) -> AsyncGenerator[AppContext]:
    """Initialize and tear down shared services for the server's lifetime."""
    client = WorkspaceClient()
    daemon_manager = DaemonManager()
    spec_service = SpecGeneratorService(client=client)
    _lifespan_state.client = client
    _lifespan_state.spec_service = spec_service
    try:
        yield {
            "client": client,
            "daemon_manager": daemon_manager,
            "spec_service": spec_service,
        }
    finally:
        _lifespan_state.client = None
        _lifespan_state.spec_service = None
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
        "WORKFLOW:\n"
        "You MUST read the resource 'tlgp://spec/workflow' before starting any work. "
        "It contains the complete step-by-step instructions and rules."
    ),
)


# ============================================================
# Resources
# ============================================================


@mcp.resource("tlgp://spec/workflow")
def get_spec_workflow_resource() -> str:
    """End-to-end workflow guide for creating specification documents."""
    return get_spec_workflow()


@mcp.resource("tlgp://spec/validation-guide")
def get_spec_validation_guide_resource() -> str:
    """Detailed validation rules mapping 1-to-1 to validator checks."""
    return get_validation_guide()


@mcp.resource("tlgp://spec/writing-guide")
def get_spec_writing_guide_resource() -> str:
    """Semantic writing rules and UI control type classification rules."""
    return get_writing_guide()


@mcp.resource("tlgp://spec/example-analysis")
def get_spec_example_analysis_resource() -> str:
    """A complete example analysis.json for reference."""
    return get_example_analysis()


@mcp.resource("tlgp://spec/schema")
async def get_spec_schema_resource() -> str:
    """JSON schema of AnalysisData for analysis.json validation."""
    spec_service = _lifespan_state.spec_service
    if not spec_service:
        raise RuntimeError("Spec generator service not initialized")
    return await spec_service.get_schema()
# ============================================================
# Prompts
# ============================================================


@mcp.prompt()
def generate_spec(
    path: str | None = None,
) -> str:
    """Guide the agent to generate a screen specification document from a screenshot image or previously exported .zip workspace."""
    workflow = get_spec_workflow()
    if path:
        return (
            f"{workflow}\n\n"
            f"Please begin the workflow by launching the annotator with the "
            f"provided path: `{path}`."
        )
    return (
        f"{workflow}\n\n"
        f"Please begin the workflow by launching a fresh annotator session "
        f"without providing any pre-loaded path to start fresh."
    )

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


@mcp.tool()
async def scaffold_spec(
    ctx: Context,
    output_dir: str,
    section_prefix: str = "1.1",
) -> dict:
    """Export component images and scaffold spec.json in one step.

    Call this after the user finishes annotating. It:
    1. Exports cropped component images (both annotated and raw) from the workspace
    2. Reads the workspace state and mapping.json to auto-generate the structural
       skeleton of spec.json (component hierarchy, image paths, cross-references)
    3. Saves spec.json to the output directory with TODO placeholders for
       semantic fields (Vietnamese labels, descriptions, interactions, APIs)

    Args:
        output_dir: Absolute path to the destination directory for exported images and spec.json.
        section_prefix: Section number prefix for component headings in the generated document (default "1.1").

    Returns:
        dict with spec_path, export_path, components, screen_name, annotated_images, raw_images.
    """
    client = _get_client(ctx)

    # Step 1: Export images
    export_result = await client.export_images(output_dir, mode="both")

    # Step 2: Scaffold spec.json from workspace state + exported mapping
    state = await client.get_workspace_state()
    scaffold_result = scaffold_and_save(state, export_result.output_path, section_prefix)

    return {
        "spec_path": scaffold_result.spec_path,
        "export_path": export_result.output_path,
        "components": scaffold_result.components,
        "screen_name": scaffold_result.screen_name,
        "annotated_images": export_result.annotated_images,
        "raw_images": export_result.raw_images,
    }


@mcp.tool()
async def update_spec_node(
    ctx: Context,
    spec_path: str,
    node_id: int,
    label: str | None = None,
    description: str | None = None,
    control_type: str | None = None,
    required: bool | None = None,
    editable: bool | None = None,
    max_length: int | None = None,
    interactions: list[dict] | None = None,
    apis: list[dict] | None = None,
) -> dict:
    """Programmatically update semantic fields of a specific node in spec.json.

    Args:
        spec_path: Absolute path to the spec.json file.
        node_id: The integer ID of the node to update (e.g. 0 for Screen).
        label: Descriptive Vietnamese label for the node.
        description: Vietnamese high-level description/summary of the node.
        control_type: The UI control type (e.g. Button, Text, Icon, Image).
        required: For leaf elements, whether the field is required.
        editable: For leaf elements, whether the field is editable.
        max_length: For leaf elements, maximum character length constraints.
        interactions: List of interaction dicts containing action and reaction.
        apis: List of API dicts documenting endpoints, request and response structures.

    Returns:
        dict with status and message.
    """
    try:
        update_node_in_spec_file(
            spec_path=spec_path,
            node_id=node_id,
            label=label,
            description=description,
            control_type=control_type,
            required=required,
            editable=editable,
            max_length=max_length,
            interactions=interactions,
            apis=apis,
        )
        return {
            "status": "success",
            "message": f"Node {node_id} successfully updated in {spec_path}",
        }
    except Exception as e:
        logger.error("Failed to update node %d: %s", node_id, e)
        return {
            "status": "error",
            "message": f"Failed to update node {node_id}: {e}",
        }


@mcp.tool()
async def validate_spec(
    ctx: Context,
    spec_path: str,
) -> dict:
    """Run validation checks against spec.json using the doc-generator validator.

    Args:
        spec_path: Absolute path to the spec.json file on disk.

    Returns:
        dict with valid, errors, warnings, components, interactions, apis, images.
    """
    res = await _get_spec_service(ctx).validate(spec_path=spec_path, ctx=ctx)
    return {
        "valid": res.valid,
        "errors": res.errors,
        "warnings": res.warnings,
        "components": res.components,
        "interactions": res.interactions,
        "apis": res.apis,
        "images": res.images,
    }


@mcp.tool()
async def compile_spec(
    ctx: Context,
    spec_path: str,
    output_path: str | None = None,
) -> dict:
    """Compile the spec.json into a final specification document (.docx).

    Args:
        spec_path: Absolute path to the spec.json file.
        output_path: Optional absolute path where the .docx should be saved.

    Returns:
        dict with valid, output_path, errors, warnings, tables, images.
    """
    res = await _get_spec_service(ctx).compile(
        spec_path=spec_path,
        output_path=output_path,
        ctx=ctx,
    )
    return {
        "valid": res.valid,
        "output_path": res.output_path,
        "errors": res.errors,
        "warnings": res.warnings,
        "tables": res.tables,
        "images": res.images,
    }
