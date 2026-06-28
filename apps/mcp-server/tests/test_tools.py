"""Tests for redesigned MCP tools, services, and managers."""

from __future__ import annotations

import json
import sys
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from mcp_server.client import WorkspaceClient
from mcp_server.manager import DaemonManager
from mcp_server.server import (
    compile_spec,
    connect_to_annotator,
    launch_annotator,
    scaffold_spec,
    update_spec_node,
    validate_spec,
)
from mcp_server.services import SpecGeneratorService

# ── SpecGeneratorService (decoupled validate & compile CLI subprocess invocation) ──


class TestSpecGeneratorService:
    @pytest.mark.anyio
    async def test_validate_invokes_cli_and_parses_result(self, tmp_path):
        spec_file = tmp_path / "spec.json"
        spec_file.write_text('{"dummy": true}', encoding="utf-8")

        expected_result = {
            "valid": True,
            "components": 5,
            "errors": [],
            "warnings": [],
            "interactions": 3,
            "apis": 1,
            "images": 2,
        }

        mock_proc = AsyncMock()
        mock_proc.communicate.return_value = (
            json.dumps(expected_result).encode(),
            b"",
        )
        mock_proc.returncode = 0

        with patch(
            "mcp_server.services.asyncio.create_subprocess_exec", return_value=mock_proc
        ) as mock_exec:
            service = SpecGeneratorService()
            result = await service.validate(spec_path=str(spec_file))

        assert result.valid is True
        assert result.components == 5

        # Verify CLI was called with --validate-only
        call_args = mock_exec.call_args[0]
        assert call_args[0] == sys.executable
        assert str(spec_file) in call_args
        assert "--validate-only" in call_args
        assert "--json" in call_args

    @pytest.mark.anyio
    async def test_compile_invokes_cli_and_parses_result(self, tmp_path):
        spec_file = tmp_path / "spec.json"
        spec_file.write_text('{"dummy": true}', encoding="utf-8")

        expected_result = {
            "valid": True,
            "output_path": str(tmp_path / "out.docx"),
            "errors": [],
            "warnings": [],
            "tables": 5,
            "images": 2,
        }

        mock_proc = AsyncMock()
        mock_proc.communicate.return_value = (
            json.dumps(expected_result).encode(),
            b"",
        )
        mock_proc.returncode = 0

        with patch(
            "mcp_server.services.asyncio.create_subprocess_exec", return_value=mock_proc
        ) as mock_exec:
            service = SpecGeneratorService()
            result = await service.compile(spec_path=str(spec_file), output_path=str(tmp_path / "out.docx"))

        assert result.valid is True
        assert result.output_path == str(tmp_path / "out.docx")

        # Verify CLI was called with output path flag
        call_args = mock_exec.call_args[0]
        assert "-o" in call_args
        assert str(tmp_path / "out.docx") in call_args

    @pytest.mark.anyio
    async def test_compile_exports_workspace_zip_on_success(self, tmp_path):
        spec_file = tmp_path / "spec.json"
        spec_file.write_text("{}", encoding="utf-8")

        docx_path = tmp_path / "out.docx"
        expected_result = {
            "valid": True,
            "output_path": str(docx_path),
        }

        mock_proc = AsyncMock()
        mock_proc.communicate.return_value = (
            json.dumps(expected_result).encode(),
            b"",
        )
        mock_proc.returncode = 0

        mock_client = MagicMock(spec=WorkspaceClient)
        mock_client.export_workspace = AsyncMock()

        with patch(
            "mcp_server.services.asyncio.create_subprocess_exec", return_value=mock_proc
        ):
            service = SpecGeneratorService(client=mock_client)
            result = await service.compile(spec_path=str(spec_file), output_path=str(docx_path))

        assert result.valid is True
        mock_client.export_workspace.assert_awaited_once_with(
            str(tmp_path / "workspace.zip")
        )


# ── Redesigned MCP Tools ──


class TestRedesignedMcpTools:
    @pytest.mark.anyio
    async def test_launch_annotator_success(self, mcp_ctx, tmp_path):
        mock_client = MagicMock(spec=WorkspaceClient)
        mock_daemon = MagicMock(spec=DaemonManager)
        mock_daemon.launch_annotator = AsyncMock(return_value={
            "annotator_ready": True,
            "annotator_url": "http://127.0.0.1:8000"
        })

        ctx = mcp_ctx(client=mock_client, daemon_manager=mock_daemon)
        res = await launch_annotator(ctx, path=str(tmp_path / "screenshot.png"))
        assert res["annotator_ready"] is True
        assert res["annotator_url"] == "http://127.0.0.1:8000"
        assert mock_client.base_url == "http://127.0.0.1:8000"

    @pytest.mark.anyio
    async def test_connect_to_annotator_success(self, mcp_ctx):
        mock_client = MagicMock(spec=WorkspaceClient)
        mock_client.check_connection = AsyncMock(return_value=True)
        mock_client.get_workspace_state = AsyncMock(
            return_value=MagicMock(
                screen=MagicMock(name="Test"),
                components={},
            )
        )
        mock_daemon = MagicMock(spec=DaemonManager)

        ctx = mcp_ctx(client=mock_client, daemon_manager=mock_daemon)
        res = await connect_to_annotator(ctx, "http://127.0.0.1:9091")
        assert res["status"] == "success"
        assert mock_client.base_url == "http://127.0.0.1:9091"

    @pytest.mark.anyio
    async def test_scaffold_spec_success(self, mcp_ctx, tmp_path):
        mock_client = MagicMock(spec=WorkspaceClient)
        mock_client.export_images = AsyncMock(return_value=MagicMock(
            output_path=str(tmp_path),
            annotated_images=3,
            raw_images=3
        ))
        mock_client.get_workspace_state = AsyncMock()

        ctx = mcp_ctx(client=mock_client)

        scaffold_res = MagicMock(
            spec_path=str(tmp_path / "spec.json"),
            components=2,
            screen_name="Home"
        )

        with patch("mcp_server.server.scaffold_and_save", return_value=scaffold_res):
            res = await scaffold_spec(ctx, output_dir=str(tmp_path))

        assert res["spec_path"] == str(tmp_path / "spec.json")
        assert res["components"] == 2
        assert res["annotated_images"] == 3

    @pytest.mark.anyio
    async def test_update_spec_node_success(self, mcp_ctx, tmp_path):
        ctx = mcp_ctx()
        spec_path = str(tmp_path / "spec.json")

        with patch("mcp_server.server.update_node_in_spec_file") as mock_update:
            res = await update_spec_node(
                ctx,
                spec_path=spec_path,
                node_id=0,
                label="Updated label",
                description="Updated desc"
            )
        assert res["status"] == "success"
        mock_update.assert_called_once_with(
            spec_path=spec_path,
            node_id=0,
            label="Updated label",
            description="Updated desc",
            control_type=None,
            required=None,
            editable=None,
            max_length=None,
            interactions=None,
            apis=None
        )

    @pytest.mark.anyio
    async def test_validate_spec_success(self, mcp_ctx):
        mock_service = MagicMock(spec=SpecGeneratorService)
        mock_service.validate = AsyncMock(return_value=MagicMock(
            valid=True,
            errors=[],
            warnings=[],
            components=5,
            interactions=3,
            apis=1,
            images=6
        ))
        ctx = mcp_ctx(spec_service=mock_service)

        res = await validate_spec(ctx, spec_path="/path/to/spec.json")
        assert res["valid"] is True
        assert res["components"] == 5

    @pytest.mark.anyio
    async def test_compile_spec_success(self, mcp_ctx):
        mock_service = MagicMock(spec=SpecGeneratorService)
        mock_service.compile = AsyncMock(return_value=MagicMock(
            valid=True,
            output_path="/path/to/out.docx",
            errors=[],
            warnings=[],
            tables=10,
            images=5
        ))
        ctx = mcp_ctx(spec_service=mock_service)

        res = await compile_spec(ctx, spec_path="/path/to/spec.json", output_path="/path/to/out.docx")
        assert res["valid"] is True
        assert res["output_path"] == "/path/to/out.docx"
        assert res["tables"] == 10
