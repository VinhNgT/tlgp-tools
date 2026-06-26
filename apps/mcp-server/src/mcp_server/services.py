"""Services for managing spec doc generation via the doc-gen CLI subprocess."""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path
from typing import TYPE_CHECKING

from tlgp_contracts import DocGenResult
from tlgp_logger import get_logger

from mcp_server.client import WorkspaceClient

if TYPE_CHECKING:
    from mcp.server.fastmcp import Context

logger = get_logger(__name__)




class SpecGeneratorService:
    """Orchestrates spec document generation by invoking the doc-gen CLI as a subprocess.

    The doc-generator app runs independently — no Python imports between apps.
    Communication happens via a structured JSON contract over stdout.
    """

    def __init__(self, client: WorkspaceClient | None = None):
        self._client = client

    async def generate(
        self,
        analysis_path: str,
        ctx: Context | None = None,
        output_path: str | None = None,
        validate_only: bool = False,
    ) -> DocGenResult:
        """Validate, and optionally generate, the specification document.

        Delegates to the ``doc-gen`` CLI with ``--json`` for structured output.
        """
        if ctx:
            await ctx.report_progress(
                10, 100, "Loading and validating analysis data..."
            )

        # Build CLI command
        cmd = [sys.executable, "-m", "doc_generator", analysis_path, "--json"]
        if validate_only:
            cmd.append("--validate-only")
        if output_path:
            cmd.extend(["-o", output_path])

        logger.info("Invoking doc-gen CLI: %s", " ".join(cmd))

        if ctx:
            await ctx.report_progress(60, 100, "Running document generation...")

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout_bytes, stderr_bytes = await proc.communicate()
        except Exception as e:
            logger.error("Failed to invoke doc-gen subprocess: %s", e)
            return DocGenResult(
                valid=False,
                errors=[f"Failed to invoke doc-gen: {e}"],
            )

        stdout_text = stdout_bytes.decode("utf-8", errors="replace").strip()
        stderr_text = stderr_bytes.decode("utf-8", errors="replace").strip()

        if stderr_text:
            logger.debug("doc-gen stderr: %s", stderr_text)

        try:
            result = DocGenResult.model_validate(json.loads(stdout_text))
        except Exception:
            logger.error(
                "doc-gen produced non-JSON stdout (exit code %d): %s",
                proc.returncode,
                stdout_text[:500],
            )
            return DocGenResult(
                valid=False,
                errors=[
                    f"doc-gen exited with code {proc.returncode}. "
                    f"stderr: {stderr_text[:500]}"
                ],
            )

        # On successful generation, export workspace.zip alongside the docx
        if (
            not validate_only
            and result.valid
            and self._client is not None
            and result.output_path is not None
        ):
            docx_path = Path(result.output_path)
            workspace_zip_path = docx_path.parent / "workspace.zip"
            if ctx:
                await ctx.log(
                    "info", f"Exporting workspace state to {workspace_zip_path}..."
                )
            try:
                await self._client.export_workspace(str(workspace_zip_path))
            except Exception as e:
                logger.error("Failed to export workspace.zip next to docx: %s", e)
                if ctx:
                    await ctx.log(
                        "warning",
                        f"Failed to export workspace.zip next to docx: {e}",
                    )

        if ctx:
            await ctx.report_progress(100, 100, "Spec generation complete.")

        return result
