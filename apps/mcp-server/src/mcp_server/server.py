"""FastMCP server — tools and prompts for the TLGP toolchain.

Exposes two tools (one per underlying package) and one orchestration prompt:
- launch_annotator  → tlgp-annotation-tool
- generate_spec_doc → doc-generator
- spec_doc_workflow → prompt that guides the agent through the full workflow
"""

from __future__ import annotations

import logging

from mcp.server.fastmcp import FastMCP

from mcp_server.tools.launch_annotator import launch_annotator_impl
from mcp_server.tools.generate_spec_doc import generate_spec_doc_impl
from mcp_server.prompts import SPEC_WORKFLOW_PROMPT

logger = logging.getLogger(__name__)

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
def launch_annotator(
    output_dir: str,
    screenshot_path: str | None = None,
    session_path: str | None = None,
) -> dict:
    """Launch the TLGP Annotation Tool GUI.

    Spawns the annotation tool as a subprocess. The tool opens a GUI window
    where the user annotates screenshots with component boxes. The process
    runs in the background — the agent should wait for the user to finish.

    Args:
        output_dir: Directory where the tool will save exported files.
        screenshot_path: Optional screenshot image path to pre-load.
        session_path: Optional previously exported session JSON to re-edit.
            Mutually exclusive with screenshot_path.

    Returns:
        dict with pid.
    """
    return launch_annotator_impl(output_dir, screenshot_path, session_path)


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
