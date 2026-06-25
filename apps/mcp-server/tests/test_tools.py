"""Tests for MCP tools, services, and managers."""

from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from mcp_server.client import WorkspaceClient
from mcp_server.manager import DaemonManager
from mcp_server.server import connect_to_annotator
from mcp_server.services import SpecGeneratorService

# ============================================================
# Helpers
# ============================================================


def _make_ctx_with_lifespan(
    client: WorkspaceClient | None = None,
    daemon_manager: DaemonManager | None = None,
    spec_service: SpecGeneratorService | None = None,
) -> MagicMock:
    """Create a mock MCP Context that provides lifespan_context."""
    ctx = MagicMock()
    ctx.report_progress = AsyncMock()
    ctx.log = AsyncMock()
    ctx.request_context.lifespan_context = {
        "client": client or MagicMock(spec=WorkspaceClient),
        "daemon_manager": daemon_manager or MagicMock(spec=DaemonManager),
        "spec_service": spec_service or MagicMock(spec=SpecGeneratorService),
    }
    return ctx


# ── SpecGeneratorService (subprocess invocation) ──────────────


class TestSpecGeneratorService:
    @pytest.mark.anyio
    async def test_generate_invokes_cli_and_parses_result(self, tmp_path):
        """Mocked subprocess returns valid JSON → service returns parsed result."""
        analysis_file = tmp_path / "analysis.json"
        analysis_file.write_text('{"dummy": true}', encoding="utf-8")

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

        with patch("mcp_server.services.asyncio.create_subprocess_exec", return_value=mock_proc) as mock_exec:
            service = SpecGeneratorService(doc_gen_bin="/usr/bin/doc-gen")
            result = await service.generate(analysis_path=str(analysis_file))

        assert result["valid"] is True
        assert result["output_path"] == str(tmp_path / "out.docx")

        # Verify CLI was called with --json
        call_args = mock_exec.call_args[0]
        assert call_args[0] == "/usr/bin/doc-gen"
        assert str(analysis_file) in call_args
        assert "--json" in call_args

    @pytest.mark.anyio
    async def test_generate_validate_only_passes_flag(self, tmp_path):
        analysis_file = tmp_path / "analysis.json"
        analysis_file.write_text('{}', encoding="utf-8")

        mock_proc = AsyncMock()
        mock_proc.communicate.return_value = (
            json.dumps({"valid": True, "warnings": []}).encode(),
            b"",
        )
        mock_proc.returncode = 0

        with patch("mcp_server.services.asyncio.create_subprocess_exec", return_value=mock_proc) as mock_exec:
            service = SpecGeneratorService(doc_gen_bin="/usr/bin/doc-gen")
            result = await service.generate(
                analysis_path=str(analysis_file),
                validate_only=True,
            )

        assert result["valid"] is True
        call_args = mock_exec.call_args[0]
        assert "--validate-only" in call_args

    @pytest.mark.anyio
    async def test_generate_output_path_passes_flag(self, tmp_path):
        analysis_file = tmp_path / "analysis.json"
        analysis_file.write_text('{}', encoding="utf-8")

        mock_proc = AsyncMock()
        mock_proc.communicate.return_value = (
            json.dumps({"valid": True}).encode(),
            b"",
        )
        mock_proc.returncode = 0

        with patch("mcp_server.services.asyncio.create_subprocess_exec", return_value=mock_proc) as mock_exec:
            service = SpecGeneratorService(doc_gen_bin="/usr/bin/doc-gen")
            await service.generate(
                analysis_path=str(analysis_file),
                output_path="/out/spec.docx",
            )

        call_args = mock_exec.call_args[0]
        assert "-o" in call_args
        assert "/out/spec.docx" in call_args

    @pytest.mark.anyio
    async def test_generate_invalid_json_stdout(self, tmp_path):
        analysis_file = tmp_path / "analysis.json"
        analysis_file.write_text('{}', encoding="utf-8")

        mock_proc = AsyncMock()
        mock_proc.communicate.return_value = (b"not json", b"some error")
        mock_proc.returncode = 1

        with patch("mcp_server.services.asyncio.create_subprocess_exec", return_value=mock_proc):
            service = SpecGeneratorService(doc_gen_bin="/usr/bin/doc-gen")
            result = await service.generate(analysis_path=str(analysis_file))

        assert result["valid"] is False
        assert len(result["errors"]) > 0

    @pytest.mark.anyio
    async def test_generate_missing_binary(self, tmp_path):
        analysis_file = tmp_path / "analysis.json"
        analysis_file.write_text('{}', encoding="utf-8")

        with patch("mcp_server.services.shutil.which", return_value=None):
            service = SpecGeneratorService()
            result = await service.generate(analysis_path=str(analysis_file))

        assert result["valid"] is False
        assert "doc-gen binary not found" in result["errors"][0]

    @pytest.mark.anyio
    async def test_generate_exports_workspace_zip_on_success(self, tmp_path):
        analysis_file = tmp_path / "analysis.json"
        analysis_file.write_text('{}', encoding="utf-8")

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

        with patch("mcp_server.services.asyncio.create_subprocess_exec", return_value=mock_proc):
            service = SpecGeneratorService(
                client=mock_client,
                doc_gen_bin="/usr/bin/doc-gen",
            )
            result = await service.generate(analysis_path=str(analysis_file))

        assert result["valid"] is True
        mock_client.export_workspace.assert_awaited_once_with(
            str(tmp_path / "workspace.zip")
        )

    @pytest.mark.anyio
    async def test_generate_with_progress_reporting(self, tmp_path):
        analysis_file = tmp_path / "analysis.json"
        analysis_file.write_text('{}', encoding="utf-8")

        mock_proc = AsyncMock()
        mock_proc.communicate.return_value = (
            json.dumps({"valid": True}).encode(),
            b"",
        )
        mock_proc.returncode = 0

        ctx = MagicMock()
        ctx.report_progress = AsyncMock()
        ctx.log = AsyncMock()

        with patch("mcp_server.services.asyncio.create_subprocess_exec", return_value=mock_proc):
            service = SpecGeneratorService(doc_gen_bin="/usr/bin/doc-gen")
            await service.generate(analysis_path=str(analysis_file), ctx=ctx)

        ctx.report_progress.assert_any_call(
            10, 100, "Loading and validating analysis data..."
        )
        ctx.report_progress.assert_any_call(
            60, 100, "Running document generation..."
        )
        ctx.report_progress.assert_any_call(
            100, 100, "Spec generation complete."
        )


# ── launch_annotator ──────────────────────────────────────────


class TestLaunchAnnotator:
    @pytest.mark.anyio
    async def test_launch_annotator_success(self, tmp_path, monkeypatch):
        mock_popen = MagicMock()
        mock_popen.return_value.pid = 12345
        monkeypatch.setattr(
            "mcp_server.manager.subprocess.Popen",
            mock_popen,
        )
        monkeypatch.setattr(
            "mcp_server.manager.shutil.which",
            lambda name: "/usr/local/bin/uv",
        )

        # Mock httpx.AsyncClient to avoid actual HTTP calls and timeouts
        class MockAsyncClient:
            async def __aenter__(self):
                return self

            async def __aexit__(self, exc_type, exc_val, exc_tb):
                pass

            async def get(self, url, *args, **kwargs):
                mock_res = MagicMock()
                mock_res.status_code = 200
                return mock_res

            async def post(self, url, *args, **kwargs):
                mock_res = MagicMock()
                mock_res.status_code = 200
                return mock_res

        monkeypatch.setattr(
            "mcp_server.manager.httpx.AsyncClient",
            MockAsyncClient,
        )

        # Create dummy screenshot to pass validation
        screenshot = tmp_path / "test.png"
        screenshot.write_bytes(b"dummy")

        manager = DaemonManager()
        result = await manager.launch_annotator(path=str(screenshot))
        assert result["annotator_pid"] == 12345
        assert result["annotator_ready"] is True
        assert mock_popen.call_count == 1

        # Verify uv run is used instead of sys.executable
        for call in mock_popen.call_args_list:
            call_args = call[0][0]
            assert call_args[0] == "/usr/local/bin/uv"
            assert "run" in call_args

    @pytest.mark.anyio
    async def test_raises_when_uv_not_found(self, tmp_path, monkeypatch):
        monkeypatch.setattr(
            "mcp_server.manager.shutil.which",
            lambda name: None,
        )

        manager = DaemonManager()
        with pytest.raises(RuntimeError, match="uv is not installed"):
            await manager.launch_annotator(path=str(tmp_path / "out"))


# ── connect_to_annotator ─────────────────────────────────────


class TestConnectToAnnotator:
    @pytest.mark.anyio
    async def test_connect_success(self):
        mock_client = MagicMock(spec=WorkspaceClient)
        mock_client.check_connection = AsyncMock(return_value=True)
        mock_client.get_workspace_state = AsyncMock(
            return_value=MagicMock(
                screen=MagicMock(name="Test"),
                components={},
            )
        )

        mock_daemon = MagicMock(spec=DaemonManager)

        ctx = _make_ctx_with_lifespan(client=mock_client, daemon_manager=mock_daemon)

        res = await connect_to_annotator(ctx, "http://127.0.0.1:9091")
        assert res["status"] == "success"
        assert "http://127.0.0.1:9091" in res["message"]
        assert mock_client.base_url == "http://127.0.0.1:9091"

    @pytest.mark.anyio
    async def test_connect_failure(self):
        mock_client = MagicMock(spec=WorkspaceClient)
        mock_client.check_connection = AsyncMock(
            side_effect=Exception("Connection refused")
        )

        mock_daemon = MagicMock(spec=DaemonManager)
        ctx = _make_ctx_with_lifespan(client=mock_client, daemon_manager=mock_daemon)

        res = await connect_to_annotator(ctx, "http://localhost:8080")
        assert res["status"] == "error"
        assert "Failed to connect to annotator" in res["message"]
