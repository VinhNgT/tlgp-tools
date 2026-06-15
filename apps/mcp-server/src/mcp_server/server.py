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
async def get_engine_state() -> dict:
    """Fetch the current flat-map JSON WorkspaceState from the running Engine.

    Use this tool to read the latest annotation hierarchy automatically,
    instead of relying on local JSON files.
    """
    try:
        async with httpx.AsyncClient() as client:
            res = await client.get("http://127.0.0.1:8000/state")
            res.raise_for_status()
            return res.json()
    except httpx.HTTPStatusError as e:
        raise ApiClientError(
            message="Failed to fetch engine state",
            status_code=e.response.status_code,
            url=str(e.request.url),
            method=e.request.method,
            backend_detail=e.response.text,
        ) from e
    except httpx.RequestError as e:
        raise ApiClientError(
            message=f"Request to fetch engine state failed: {e}",
            url=str(e.request.url) if hasattr(e, "request") else None,
            method=e.request.method if hasattr(e, "request") else None,
        ) from e


@mcp.tool()
async def download_engine_crops(output_dir: str) -> dict:
    """Download all component crops and the raw image from the Engine.

    Creates a clean directory containing all component crops named as `<uuid>.png`.
    Also downloads the root screenshot as `raw.png`.
    Use this to prepare a local directory before writing analysis.json.

    Args:
        output_dir: The directory to save the images to.

    Returns:
        dict with status and list of downloaded files.
    """

    out_path = os.path.abspath(output_dir)
    os.makedirs(out_path, exist_ok=True)

    downloaded = []
    errors = []

    try:
        async with httpx.AsyncClient() as client:
            state_res = await client.get("http://127.0.0.1:8000/state")
            state_res.raise_for_status()
            state = state_res.json()

            # Download raw image
            raw_res = await client.get("http://127.0.0.1:8000/image/root")
            if raw_res.status_code == 200:
                with open(os.path.join(out_path, "raw.png"), "wb") as f:
                    f.write(raw_res.content)
                downloaded.append("raw.png")

            # Download crops
            for comp_id in state.get("components", {}).keys():
                crop_res = await client.get(f"http://127.0.0.1:8000/image/{comp_id}")
                if crop_res.status_code == 200:
                    filename = f"{comp_id}.png"
                    with open(os.path.join(out_path, filename), "wb") as f:
                        f.write(crop_res.content)
                    downloaded.append(filename)

        return {
            "status": "success",
            "output_dir": out_path,
            "downloaded": len(downloaded),
            "files": downloaded,
            "errors": errors,
        }
    except httpx.HTTPStatusError as e:
        raise ApiClientError(
            message="HTTP error while downloading engine crops",
            status_code=e.response.status_code,
            url=str(e.request.url),
            method=e.request.method,
            backend_detail=e.response.text,
        ) from e
    except httpx.RequestError as e:
        raise ApiClientError(
            message=f"Request failed while downloading engine crops: {e}",
            url=str(e.request.url) if hasattr(e, "request") else None,
            method=e.request.method if hasattr(e, "request") else None,
        ) from e


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
