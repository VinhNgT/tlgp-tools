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
    """Orchestrates spec document validation and generation by invoking the doc-gen CLI as a subprocess.

    Communication happens via a structured JSON contract over stdout.
    """

    def __init__(self, client: WorkspaceClient | None = None):
        self._client = client

    async def validate(
        self,
        spec_path: str,
        ctx: Context | None = None,
    ) -> DocGenResult:
        """Validate the specification JSON payload structure and parameters.

        Delegates to the ``doc-gen`` CLI with ``--validate-only --json``.
        """
        if ctx:
            await ctx.report_progress(10, 100, "Loading and validating spec data...")

        cmd = [sys.executable, "-m", "doc_generator", spec_path, "--validate-only", "--json"]
        logger.info("Invoking doc-gen CLI for validation: %s", " ".join(cmd))

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout_bytes, stderr_bytes = await proc.communicate()
        except Exception as e:
            logger.error("Failed to invoke doc-gen validation: %s", e)
            return DocGenResult(
                valid=False,
                errors=[f"Failed to invoke validation: {e}"],
            )

        stdout_text = stdout_bytes.decode("utf-8", errors="replace").strip()
        stderr_text = stderr_bytes.decode("utf-8", errors="replace").strip()

        if stderr_text:
            logger.debug("doc-gen validation stderr: %s", stderr_text)

        try:
            result = DocGenResult.model_validate(json.loads(stdout_text))
        except Exception:
            logger.error(
                "doc-gen validation produced non-JSON stdout (exit code %d): %s",
                proc.returncode,
                stdout_text[:500],
            )
            return DocGenResult(
                valid=False,
                errors=[
                    f"doc-gen validation exited with code {proc.returncode}. "
                    f"stderr: {stderr_text[:500]}"
                ],
            )

        if ctx:
            await ctx.report_progress(100, 100, "Spec validation complete.")

        return result

    async def compile(
        self,
        spec_path: str,
        output_path: str | None = None,
        ctx: Context | None = None,
    ) -> DocGenResult:
        """Compile the specification document (.docx) from the spec JSON.

        Delegates to the ``doc-gen`` CLI with ``--json``.
        """
        if ctx:
            await ctx.report_progress(10, 100, "Initializing document generation...")

        cmd = [sys.executable, "-m", "doc_generator", spec_path, "--json"]
        if output_path:
            cmd.extend(["-o", output_path])

        logger.info("Invoking doc-gen CLI for compilation: %s", " ".join(cmd))

        if ctx:
            await ctx.report_progress(50, 100, "Running document compilation...")

        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout_bytes, stderr_bytes = await proc.communicate()
        except Exception as e:
            logger.error("Failed to invoke doc-gen compilation: %s", e)
            return DocGenResult(
                valid=False,
                errors=[f"Failed to invoke compilation: {e}"],
            )

        stdout_text = stdout_bytes.decode("utf-8", errors="replace").strip()
        stderr_text = stderr_bytes.decode("utf-8", errors="replace").strip()

        if stderr_text:
            logger.debug("doc-gen compilation stderr: %s", stderr_text)

        try:
            result = DocGenResult.model_validate(json.loads(stdout_text))
        except Exception:
            logger.error(
                "doc-gen compilation produced non-JSON stdout (exit code %d): %s",
                proc.returncode,
                stdout_text[:500],
            )
            return DocGenResult(
                valid=False,
                errors=[
                    f"doc-gen compilation exited with code {proc.returncode}. "
                    f"stderr: {stderr_text[:500]}"
                ],
            )

        # On successful generation, export workspace.zip alongside the docx
        if (
            result.valid
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
            await ctx.report_progress(100, 100, "Document generation complete.")

        return result

    async def get_schema(self) -> str:
        """Get the JSON schema of ScreenSpec from the doc-gen CLI."""
        cmd = [sys.executable, "-m", "doc_generator", "--schema"]
        try:
            proc = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            stdout_bytes, _ = await proc.communicate()
            if proc.returncode != 0:
                logger.error("doc-gen --schema failed with code %d", proc.returncode)
                return "{}"
            return stdout_bytes.decode("utf-8", errors="replace").strip()
        except Exception as e:
            logger.error("Failed to invoke doc-gen --schema: %s", e)
            return "{}"
